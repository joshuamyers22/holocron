"""Typed planning support for migration from the pinned R ``rms`` namespace."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Literal, TypeAlias, cast

from holocron._serialization import canonical_json, parse_json_object, validate_sha256
from holocron.exceptions import InputValidationError

MigrationDisposition: TypeAlias = Literal[
    "implemented", "experimental", "mapped", "unsupported"
]
MigrationKind: TypeAlias = Literal["export", "s3_method"]
DeprecationStatus: TypeAlias = Literal["active", "removed"]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

PLAN_SCHEMA_VERSION = "holocron-rms-migration-plan/v1"
CATALOG_SCHEMA_VERSION = "holocron-migration-catalog/v1"
MAX_REQUESTED_SYMBOLS = 1_000
EXPECTED_CATALOG_ENTRIES = 281
_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[A-Za-z0-9.+-]*)?$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class HolocronDeprecationWarning(FutureWarning):
    """Visible warning category for registered public-API deprecations."""


def _text(value: object, *, name: str, maximum: int = 8_192) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise InputValidationError(
            f"{name} must be non-empty text of at most {maximum} characters"
        )
    return value


def _optional_text(value: object, *, name: str) -> str | None:
    return None if value is None else _text(value, name=name)


def _object(value: object, *, name: str, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InputValidationError(f"{name} fields differ")
    document = cast(dict[str, object], value)
    if set(document) != fields:
        raise InputValidationError(f"{name} fields differ")
    return document


def _array(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise InputValidationError(f"{name} must be an array")
    return cast(list[object], value)


def _integer(value: object, *, name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InputValidationError(f"{name} must be an integer of at least {minimum}")
    return value


def _required_true(value: object, *, name: str) -> bool:
    if value is not True:
        raise InputValidationError(f"{name} must remain enabled")
    return True


@dataclass(frozen=True, slots=True)
class MigrationEntry:
    """One reviewed disposition from the pinned R namespace."""

    identifier: str
    r_symbol: str
    kind: MigrationKind
    disposition: MigrationDisposition
    python_entry_point: str | None
    guidance: str

    def __post_init__(self) -> None:
        identifier = _text(self.identifier, name="identifier", maximum=512)
        symbol = _text(self.r_symbol, name="r_symbol", maximum=256)
        if self.kind not in {"export", "s3_method"}:
            raise InputValidationError("migration kind is unsupported")
        if identifier != f"{self.kind}:{symbol}":
            raise InputValidationError("migration identifier does not match its symbol")
        if self.disposition not in {
            "implemented",
            "experimental",
            "mapped",
            "unsupported",
        }:
            raise InputValidationError("migration disposition is unsupported")
        path = _optional_text(self.python_entry_point, name="python_entry_point")
        if self.disposition == "unsupported" and path is not None:
            raise InputValidationError(
                "unsupported migration entries cannot declare a Python path"
            )
        if self.disposition != "unsupported" and path is None:
            raise InputValidationError(
                "supported migration entries require a Python path"
            )
        guidance = _text(self.guidance, name="guidance", maximum=32_768)
        if len(guidance) < 40:
            raise InputValidationError("migration guidance is incomplete")
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "r_symbol", symbol)
        object.__setattr__(self, "python_entry_point", path)
        object.__setattr__(self, "guidance", guidance)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the data-only migration entry."""
        return {
            "identifier": self.identifier,
            "r_symbol": self.r_symbol,
            "kind": self.kind,
            "disposition": self.disposition,
            "python_entry_point": self.python_entry_point,
            "guidance": self.guidance,
        }

    @classmethod
    def from_dict(cls, value: object) -> MigrationEntry:
        """Reconstruct and validate one migration entry."""
        document = _object(
            value,
            name="migration entry",
            fields={
                "identifier",
                "r_symbol",
                "kind",
                "disposition",
                "python_entry_point",
                "guidance",
            },
        )
        return cls(
            identifier=cast(str, document["identifier"]),
            r_symbol=cast(str, document["r_symbol"]),
            kind=cast(MigrationKind, document["kind"]),
            disposition=cast(MigrationDisposition, document["disposition"]),
            python_entry_point=cast(str | None, document["python_entry_point"]),
            guidance=cast(str, document["guidance"]),
        )


@dataclass(frozen=True, slots=True)
class MigrationMatch:
    """A requested name and one matching reviewed namespace entry."""

    query: str
    entry: MigrationEntry

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _text(self.query, name="query", maximum=512))
        if not isinstance(cast(object, self.entry), MigrationEntry):
            raise InputValidationError("migration match requires a MigrationEntry")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the match with its originating query retained."""
        return {"query": self.query, "entry": self.entry.to_dict()}

    @classmethod
    def from_dict(cls, value: object) -> MigrationMatch:
        """Reconstruct and validate one migration match."""
        document = _object(value, name="migration match", fields={"query", "entry"})
        return cls(
            query=cast(str, document["query"]),
            entry=MigrationEntry.from_dict(document["entry"]),
        )


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """Immutable, serializable assessment of requested R ``rms`` names."""

    reference_package: str
    reference_version: str
    reference_commit: str
    catalog_sha256: str
    requested_symbols: tuple[str, ...]
    matches: tuple[MigrationMatch, ...]
    unknown_symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if _text(self.reference_package, name="reference_package") != "rms":
            raise InputValidationError("migration reference package must be rms")
        _text(self.reference_version, name="reference_version")
        if _COMMIT_PATTERN.fullmatch(self.reference_commit) is None:
            raise InputValidationError("reference_commit must be a lowercase commit ID")
        validate_sha256(self.catalog_sha256, role="migration catalog")
        requested = tuple(
            _text(value, name="requested symbol", maximum=512)
            for value in self.requested_symbols
        )
        if not 1 <= len(requested) <= MAX_REQUESTED_SYMBOLS:
            raise InputValidationError(
                f"requested_symbols must contain 1-{MAX_REQUESTED_SYMBOLS} names"
            )
        if len(set(requested)) != len(requested):
            raise InputValidationError("requested_symbols must be unique")
        if not isinstance(cast(object, self.matches), tuple) or any(
            not isinstance(cast(object, value), MigrationMatch)
            for value in self.matches
        ):
            raise InputValidationError("matches must contain MigrationMatch values")
        unknown = tuple(
            _text(value, name="unknown symbol", maximum=512)
            for value in self.unknown_symbols
        )
        if len(set(unknown)) != len(unknown) or any(
            value not in requested for value in unknown
        ):
            raise InputValidationError("unknown_symbols do not match the request")
        matched_queries = {match.query for match in self.matches}
        if any(match.query not in requested for match in self.matches):
            raise InputValidationError("migration match query was not requested")
        if matched_queries & set(unknown) or matched_queries | set(unknown) != set(
            requested
        ):
            raise InputValidationError(
                "every requested symbol must be matched or explicitly unknown"
            )
        if len(
            {(match.query, match.entry.identifier) for match in self.matches}
        ) != len(self.matches):
            raise InputValidationError("migration matches must be unique")
        object.__setattr__(self, "requested_symbols", requested)
        object.__setattr__(self, "unknown_symbols", unknown)

    @property
    def disposition_counts(self) -> dict[MigrationDisposition, int]:
        """Return counts across matched capabilities, including zero values."""
        counts = Counter(match.entry.disposition for match in self.matches)
        return {
            "implemented": counts["implemented"],
            "experimental": counts["experimental"],
            "mapped": counts["mapped"],
            "unsupported": counts["unsupported"],
        }

    @property
    def ready(self) -> bool:
        """Return whether every query is known and has a Python migration path."""
        return not self.unknown_symbols and all(
            match.entry.python_entry_point is not None for match in self.matches
        )

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the versioned data-only migration plan."""
        counts = self.disposition_counts
        return {
            "schema_version": PLAN_SCHEMA_VERSION,
            "reference": {
                "package": self.reference_package,
                "version": self.reference_version,
                "commit": self.reference_commit,
            },
            "catalog_sha256": self.catalog_sha256,
            "requested_symbols": list(self.requested_symbols),
            "matches": [match.to_dict() for match in self.matches],
            "unknown_symbols": list(self.unknown_symbols),
            "summary": {
                "implemented": counts["implemented"],
                "experimental": counts["experimental"],
                "mapped": counts["mapped"],
                "unsupported": counts["unsupported"],
                "unknown": len(self.unknown_symbols),
                "ready": self.ready,
            },
        }

    def to_json(self) -> str:
        """Serialize the migration plan as strict canonical JSON."""
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: object) -> MigrationPlan:
        """Reconstruct and validate a migration plan document."""
        document = _object(
            value,
            name="migration plan",
            fields={
                "schema_version",
                "reference",
                "catalog_sha256",
                "requested_symbols",
                "matches",
                "unknown_symbols",
                "summary",
            },
        )
        if document["schema_version"] != PLAN_SCHEMA_VERSION:
            raise InputValidationError("unsupported migration plan schema version")
        reference = _object(
            document["reference"],
            name="migration reference",
            fields={"package", "version", "commit"},
        )
        requested = tuple(
            cast(str, item)
            for item in _array(document["requested_symbols"], name="requested_symbols")
        )
        matches = tuple(
            MigrationMatch.from_dict(item)
            for item in _array(document["matches"], name="matches")
        )
        unknown = tuple(
            cast(str, item)
            for item in _array(document["unknown_symbols"], name="unknown_symbols")
        )
        result = cls(
            reference_package=cast(str, reference["package"]),
            reference_version=cast(str, reference["version"]),
            reference_commit=cast(str, reference["commit"]),
            catalog_sha256=cast(str, document["catalog_sha256"]),
            requested_symbols=requested,
            matches=matches,
            unknown_symbols=unknown,
        )
        summary = _object(
            document["summary"],
            name="migration summary",
            fields={
                "implemented",
                "experimental",
                "mapped",
                "unsupported",
                "unknown",
                "ready",
            },
        )
        expected_summary = cast(dict[str, object], result.to_dict()["summary"])
        if summary != expected_summary:
            raise InputValidationError("migration summary is inconsistent")
        return result

    @classmethod
    def from_json(cls, value: str) -> MigrationPlan:
        """Reconstruct a migration plan from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="migration plan"))


@dataclass(frozen=True, slots=True)
class DeprecationPolicy:
    """The installed minimum warning window for documented public APIs."""

    minimum_minor_releases: int
    minimum_days: int
    runtime_warning_required: bool
    changelog_required: bool
    migration_replacement_required: bool
    pre_1_0_rule: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.minimum_minor_releases, bool)
            or self.minimum_minor_releases < 2
            or isinstance(self.minimum_days, bool)
            or self.minimum_days < 90
        ):
            raise InputValidationError("deprecation windows are below policy minimums")
        if not (
            self.runtime_warning_required
            and self.changelog_required
            and self.migration_replacement_required
        ):
            raise InputValidationError("deprecation safeguards must remain enabled")
        if len(_text(self.pre_1_0_rule, name="pre_1_0_rule")) < 80:
            raise InputValidationError("pre_1_0_rule is incomplete")


@dataclass(frozen=True, slots=True)
class DeprecationNotice:
    """One registered public-API deprecation and its replacement window."""

    api: str
    deprecated_in: str
    removal_not_before_version: str
    deprecated_on: str
    removal_not_before_date: str
    replacement: str
    rationale: str
    status: DeprecationStatus

    def __post_init__(self) -> None:
        _text(self.api, name="deprecated api", maximum=512)
        _text(self.replacement, name="deprecation replacement", maximum=512)
        if _VERSION_PATTERN.fullmatch(self.deprecated_in) is None or (
            _VERSION_PATTERN.fullmatch(self.removal_not_before_version) is None
        ):
            raise InputValidationError("deprecation notice versions are invalid")
        if _DATE_PATTERN.fullmatch(self.deprecated_on) is None or (
            _DATE_PATTERN.fullmatch(self.removal_not_before_date) is None
        ):
            raise InputValidationError("deprecation notice dates are invalid")
        if len(_text(self.rationale, name="deprecation rationale")) < 40:
            raise InputValidationError("deprecation rationale is incomplete")
        if self.status not in {"active", "removed"}:
            raise InputValidationError("deprecation notice status is unsupported")


@dataclass(frozen=True, slots=True)
class _Catalog:
    reference_package: str
    reference_version: str
    reference_commit: str
    sha256: str
    entries: tuple[MigrationEntry, ...]
    policy: DeprecationPolicy
    notices: tuple[DeprecationNotice, ...]


@cache
def _catalog() -> _Catalog:
    resource = files("holocron.migration").joinpath("_catalog.json")
    encoded = resource.read_bytes()
    try:
        raw: object = json.loads(encoded)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InputValidationError("installed migration catalog is invalid") from error
    document = _object(
        raw,
        name="migration catalog",
        fields={
            "schema_version",
            "reference",
            "source_sha256",
            "entries",
            "deprecation_policy",
            "deprecation_notices",
        },
    )
    if document["schema_version"] != CATALOG_SCHEMA_VERSION:
        raise InputValidationError("installed migration catalog version is unsupported")
    reference = _object(
        document["reference"],
        name="migration catalog reference",
        fields={"package", "version", "commit", "namespace_sha256"},
    )
    if reference["package"] != "rms":
        raise InputValidationError("migration catalog reference package must be rms")
    _text(reference["version"], name="migration catalog reference version")
    reference_commit = _text(
        reference["commit"], name="migration catalog reference commit"
    )
    if _COMMIT_PATTERN.fullmatch(reference_commit) is None:
        raise InputValidationError("migration catalog reference commit is invalid")
    validate_sha256(reference["namespace_sha256"], role="namespace identity")
    sources = _object(
        document["source_sha256"],
        name="migration catalog sources",
        fields={"compatibility_manifest", "deprecation_policy"},
    )
    validate_sha256(sources["compatibility_manifest"], role="compatibility manifest")
    validate_sha256(sources["deprecation_policy"], role="deprecation policy")
    entries = tuple(
        MigrationEntry.from_dict(value)
        for value in _array(document["entries"], name="migration catalog entries")
    )
    if len(entries) != EXPECTED_CATALOG_ENTRIES or len(
        {entry.identifier for entry in entries}
    ) != len(entries):
        raise InputValidationError("installed migration catalog coverage differs")
    policy_document = _object(
        document["deprecation_policy"],
        name="deprecation policy",
        fields={
            "minimum_minor_releases",
            "minimum_days",
            "runtime_warning_required",
            "changelog_required",
            "migration_replacement_required",
            "pre_1_0_rule",
        },
    )
    policy = DeprecationPolicy(
        minimum_minor_releases=_integer(
            policy_document["minimum_minor_releases"],
            name="minimum_minor_releases",
            minimum=2,
        ),
        minimum_days=_integer(
            policy_document["minimum_days"], name="minimum_days", minimum=90
        ),
        runtime_warning_required=_required_true(
            policy_document["runtime_warning_required"],
            name="runtime_warning_required",
        ),
        changelog_required=_required_true(
            policy_document["changelog_required"], name="changelog_required"
        ),
        migration_replacement_required=_required_true(
            policy_document["migration_replacement_required"],
            name="migration_replacement_required",
        ),
        pre_1_0_rule=_text(policy_document["pre_1_0_rule"], name="pre_1_0_rule"),
    )
    notices: list[DeprecationNotice] = []
    for value in _array(document["deprecation_notices"], name="deprecation notices"):
        notice = _object(
            value,
            name="deprecation notice",
            fields={
                "api",
                "deprecated_in",
                "removal_not_before_version",
                "deprecated_on",
                "removal_not_before_date",
                "replacement",
                "rationale",
                "status",
            },
        )
        notices.append(
            DeprecationNotice(
                api=cast(str, notice["api"]),
                deprecated_in=cast(str, notice["deprecated_in"]),
                removal_not_before_version=cast(
                    str, notice["removal_not_before_version"]
                ),
                deprecated_on=cast(str, notice["deprecated_on"]),
                removal_not_before_date=cast(str, notice["removal_not_before_date"]),
                replacement=cast(str, notice["replacement"]),
                rationale=cast(str, notice["rationale"]),
                status=cast(DeprecationStatus, notice["status"]),
            )
        )
    return _Catalog(
        reference_package=cast(str, reference["package"]),
        reference_version=cast(str, reference["version"]),
        reference_commit=cast(str, reference["commit"]),
        sha256=hashlib.sha256(encoded).hexdigest(),
        entries=entries,
        policy=policy,
        notices=tuple(notices),
    )


def migration_catalog() -> tuple[MigrationEntry, ...]:
    """Return all reviewed namespace dispositions in identifier order."""
    return _catalog().entries


def lookup_rms_capability(identifier: str) -> MigrationEntry:
    """Return one exact ``export:`` or ``s3_method:`` capability entry."""
    normalized = _text(identifier, name="identifier", maximum=512)
    for entry in _catalog().entries:
        if entry.identifier == normalized:
            return entry
    raise InputValidationError(f"unknown rms capability identifier: {normalized}")


def plan_rms_migration(symbols: Iterable[str]) -> MigrationPlan:
    """Assess exact capability IDs or raw R symbols against the pinned catalog.

    Raw symbols may match more than one namespace entry; every match is retained.
    Unknown names and unsupported dispositions remain explicit, so ``ready`` is
    true only when every request has a reviewed Python path.
    """
    try:
        requested = tuple(
            _text(value, name="requested symbol", maximum=512) for value in symbols
        )
    except TypeError as error:
        raise InputValidationError("symbols must be an iterable of names") from error
    if not 1 <= len(requested) <= MAX_REQUESTED_SYMBOLS:
        raise InputValidationError(
            f"symbols must contain 1-{MAX_REQUESTED_SYMBOLS} names"
        )
    if len(set(requested)) != len(requested):
        raise InputValidationError("symbols must be unique")
    catalog = _catalog()
    by_identifier = {entry.identifier: entry for entry in catalog.entries}
    by_symbol: dict[str, list[MigrationEntry]] = {}
    for entry in catalog.entries:
        by_symbol.setdefault(entry.r_symbol, []).append(entry)
    matches: list[MigrationMatch] = []
    unknown: list[str] = []
    for query in requested:
        selected = (
            (by_identifier[query],)
            if query in by_identifier
            else tuple(by_symbol.get(query, ()))
        )
        if not selected:
            unknown.append(query)
            continue
        matches.extend(
            MigrationMatch(query, entry)
            for entry in sorted(selected, key=lambda value: value.identifier)
        )
    return MigrationPlan(
        reference_package=catalog.reference_package,
        reference_version=catalog.reference_version,
        reference_commit=catalog.reference_commit,
        catalog_sha256=catalog.sha256,
        requested_symbols=requested,
        matches=tuple(matches),
        unknown_symbols=tuple(unknown),
    )


def deprecation_policy() -> DeprecationPolicy:
    """Return the installed deprecation-window policy."""
    return _catalog().policy


def deprecation_notices() -> tuple[DeprecationNotice, ...]:
    """Return registered current and historical public-API deprecations."""
    return _catalog().notices


__all__ = [
    "DeprecationNotice",
    "DeprecationPolicy",
    "HolocronDeprecationWarning",
    "MigrationEntry",
    "MigrationMatch",
    "MigrationPlan",
    "deprecation_notices",
    "deprecation_policy",
    "lookup_rms_capability",
    "migration_catalog",
    "plan_rms_migration",
]
