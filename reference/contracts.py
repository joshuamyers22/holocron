"""Versioned parity-laboratory contracts and field-aware comparison policies."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NoReturn, TypeAlias, TypeGuard, cast

from jsonschema import Draft202012Validator

from holocron import __version__

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
RuleMode: TypeAlias = Literal["exact", "numeric"]

ROOT = Path(__file__).resolve().parents[1]
CASE_SCHEMA = ROOT / "schemas/oracle-case.schema.json"
OUTPUT_SCHEMA = ROOT / "schemas/oracle-output.schema.json"
EVIDENCE_SCHEMA = ROOT / "schemas/parity-evidence.schema.json"
POLICY_SCHEMA = ROOT / "schemas/tolerance-policy.schema.json"
POLICY_PATH = ROOT / "reference/tolerances.json"
CASES = ROOT / "reference/cases"
EXPECTED = ROOT / "reference/expected"
FIXTURE_METADATA = frozenset({"schema_version", "case_id", "reference"})
MAX_MISMATCHES = 50


class ContractValidationError(ValueError):
    """A schema, fixture, or cross-document contract is invalid."""


@dataclass(frozen=True, slots=True)
class ComparisonRule:
    """One exact or approximate leaf-comparison rule."""

    mode: RuleMode
    absolute: float = 0.0
    relative: float = 0.0


@dataclass(frozen=True, slots=True)
class PathRule:
    """A comparison rule selected by a JSON Pointer-like glob."""

    path: tuple[str, ...]
    rule: ComparisonRule


@dataclass(frozen=True, slots=True)
class ComparisonPolicy:
    """A named default policy plus field-specific overrides."""

    name: str
    description: str
    default: ComparisonRule
    rules: tuple[PathRule, ...]

    def rule_for(self, path: tuple[str, ...]) -> ComparisonRule:
        matches = [
            path_rule
            for path_rule in self.rules
            if len(path_rule.path) == len(path)
            and all(
                expected == "*" or expected == actual
                for expected, actual in zip(path_rule.path, path, strict=True)
            )
        ]
        if not matches:
            return self.default
        ranked = sorted(
            matches,
            key=lambda item: sum(segment != "*" for segment in item.path),
            reverse=True,
        )
        if len(ranked) > 1 and sum(segment != "*" for segment in ranked[0].path) == sum(
            segment != "*" for segment in ranked[1].path
        ):
            raise ContractValidationError(
                f"ambiguous comparison rules for {_format_path(path)}"
            )
        return ranked[0].rule


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """Structured result of one complete JSON comparison."""

    profile: str
    exact_comparisons: int
    numeric_comparisons: int
    maximum_absolute_error: float
    maximum_relative_error: float
    mismatches: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.mismatches

    def require_match(self) -> None:
        if self.mismatches:
            details = "\n".join(f"- {message}" for message in self.mismatches)
            raise AssertionError(
                f"comparison profile {self.profile!r} found mismatches:\n{details}"
            )


@dataclass(slots=True)
class _ComparisonState:
    exact_comparisons: int = 0
    numeric_comparisons: int = 0
    maximum_absolute_error: float = 0.0
    maximum_relative_error: float = 0.0
    mismatches: list[str] | None = None

    def __post_init__(self) -> None:
        if self.mismatches is None:
            self.mismatches = []

    def mismatch(self, message: str) -> None:
        assert self.mismatches is not None
        if len(self.mismatches) < MAX_MISMATCHES:
            self.mismatches.append(message)


def _reject_json_constant(value: str) -> NoReturn:
    raise ContractValidationError(f"non-standard JSON numeric constant: {value}")


def load_json(path: Path) -> JsonValue:
    """Load strict JSON, rejecting NaN and infinite numeric extensions."""
    try:
        value: object = json.loads(
            path.read_text(), parse_constant=_reject_json_constant
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContractValidationError(f"invalid JSON in {path}: {error}") from error
    return cast(JsonValue, value)


def require_object(value: JsonValue, *, name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ContractValidationError(f"{name} must be a JSON object")
    return value


def require_array(value: JsonValue, *, name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{name} must be a JSON array")
    return value


def validate_document(document: JsonValue, schema_path: Path) -> None:
    """Validate a document with a checked JSON Schema Draft 2020-12 schema."""
    schema = require_object(load_json(schema_path), name=str(schema_path))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),  # pyright: ignore[reportUnknownMemberType]
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = _format_path(tuple(str(part) for part in error.absolute_path))
        raise ContractValidationError(f"{schema_path.name} {location}: {error.message}")


def _pointer_segments(pointer: str) -> tuple[str, ...]:
    if not pointer.startswith("/"):
        raise ContractValidationError(f"comparison path must start with '/': {pointer}")
    return tuple(
        segment.replace("~1", "/").replace("~0", "~")
        for segment in pointer[1:].split("/")
    )


def _parse_rule(value: JsonValue, *, name: str) -> ComparisonRule:
    rule = require_object(value, name=name)
    mode = rule.get("mode")
    if mode == "exact":
        return ComparisonRule("exact")
    if mode != "numeric":
        raise ContractValidationError(f"{name}.mode is invalid")
    absolute = rule.get("absolute")
    relative = rule.get("relative")
    if not isinstance(absolute, (int, float)) or isinstance(absolute, bool):
        raise ContractValidationError(f"{name}.absolute must be numeric")
    if not isinstance(relative, (int, float)) or isinstance(relative, bool):
        raise ContractValidationError(f"{name}.relative must be numeric")
    return ComparisonRule("numeric", float(absolute), float(relative))


def load_policies() -> dict[str, ComparisonPolicy]:
    """Load and semantically validate every named comparison profile."""
    document = require_object(load_json(POLICY_PATH), name=str(POLICY_PATH))
    validate_document(document, POLICY_SCHEMA)
    raw_profiles = require_object(document["profiles"], name="profiles")
    policies: dict[str, ComparisonPolicy] = {}
    for profile_name, raw_profile in raw_profiles.items():
        profile = require_object(raw_profile, name=f"profiles.{profile_name}")
        description = profile["description"]
        if not isinstance(description, str):
            raise ContractValidationError(
                f"profiles.{profile_name}.description must be a string"
            )
        raw_rules = require_array(
            profile["rules"], name=f"profiles.{profile_name}.rules"
        )
        path_rules: list[PathRule] = []
        seen_paths: set[tuple[str, ...]] = set()
        for index, raw_path_rule in enumerate(raw_rules):
            path_rule = require_object(
                raw_path_rule, name=f"profiles.{profile_name}.rules[{index}]"
            )
            raw_path = path_rule["path"]
            if not isinstance(raw_path, str):
                raise ContractValidationError("comparison path must be a string")
            path = _pointer_segments(raw_path)
            if path in seen_paths:
                raise ContractValidationError(
                    f"duplicate comparison path in {profile_name}: {raw_path}"
                )
            seen_paths.add(path)
            path_rules.append(
                PathRule(
                    path,
                    _parse_rule(
                        path_rule["rule"],
                        name=f"profiles.{profile_name}.rules[{index}].rule",
                    ),
                )
            )
        policies[profile_name] = ComparisonPolicy(
            name=profile_name,
            description=description,
            default=_parse_rule(
                profile["default"], name=f"profiles.{profile_name}.default"
            ),
            rules=tuple(path_rules),
        )
    return policies


def _format_path(path: tuple[str, ...]) -> str:
    if not path:
        return "/"
    escaped = (segment.replace("~", "~0").replace("/", "~1") for segment in path)
    return "/" + "/".join(escaped)


def _is_number(value: JsonValue) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare(
    actual: JsonValue,
    expected: JsonValue,
    *,
    path: tuple[str, ...],
    policy: ComparisonPolicy,
    state: _ComparisonState,
) -> None:
    location = _format_path(path)
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            state.mismatch(
                f"{location}: expected object, received {type(actual).__name__}"
            )
            return
        expected_keys = set(expected)
        actual_keys = set(actual)
        if expected_keys != actual_keys:
            state.mismatch(
                f"{location}: object keys differ; "
                f"missing={sorted(expected_keys - actual_keys)}, "
                f"extra={sorted(actual_keys - expected_keys)}"
            )
        for key in sorted(expected_keys & actual_keys):
            _compare(
                actual[key],
                expected[key],
                path=(*path, key),
                policy=policy,
                state=state,
            )
        return
    if isinstance(expected, list):
        if not isinstance(actual, list):
            state.mismatch(
                f"{location}: expected array, received {type(actual).__name__}"
            )
            return
        if len(actual) != len(expected):
            state.mismatch(
                f"{location}: array length differs; "
                f"expected={len(expected)}, actual={len(actual)}"
            )
        for index, (actual_item, expected_item) in enumerate(
            zip(actual, expected, strict=False)
        ):
            _compare(
                actual_item,
                expected_item,
                path=(*path, str(index)),
                policy=policy,
                state=state,
            )
        return

    rule = policy.rule_for(path)
    if rule.mode == "numeric" and _is_number(expected) and _is_number(actual):
        state.numeric_comparisons += 1
        actual_number = float(actual)
        expected_number = float(expected)
        if not math.isfinite(actual_number) or not math.isfinite(expected_number):
            state.mismatch(f"{location}: numeric values must be finite")
            return
        absolute_error = abs(actual_number - expected_number)
        scale = max(abs(actual_number), abs(expected_number))
        relative_error = absolute_error / scale if scale else 0.0
        state.maximum_absolute_error = max(state.maximum_absolute_error, absolute_error)
        state.maximum_relative_error = max(state.maximum_relative_error, relative_error)
        if not math.isclose(
            actual_number,
            expected_number,
            abs_tol=rule.absolute,
            rel_tol=rule.relative,
        ):
            state.mismatch(
                f"{location}: {actual_number!r} != {expected_number!r} "
                f"(absolute={rule.absolute}, relative={rule.relative})"
            )
        return

    state.exact_comparisons += 1
    if actual != expected or isinstance(actual, bool) != isinstance(expected, bool):
        state.mismatch(f"{location}: {actual!r} != {expected!r} (exact)")


def compare_json(
    actual: JsonValue, expected: JsonValue, policy: ComparisonPolicy
) -> ComparisonReport:
    """Compare two JSON values using exact structure and field-aware leaf rules."""
    state = _ComparisonState()
    _compare(actual, expected, path=(), policy=policy, state=state)
    assert state.mismatches is not None
    return ComparisonReport(
        profile=policy.name,
        exact_comparisons=state.exact_comparisons,
        numeric_comparisons=state.numeric_comparisons,
        maximum_absolute_error=state.maximum_absolute_error,
        maximum_relative_error=state.maximum_relative_error,
        mismatches=tuple(state.mismatches),
    )


def _leaf_paths(value: JsonValue, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    if isinstance(value, dict):
        return [
            leaf
            for key, item in value.items()
            for leaf in _leaf_paths(item, (*path, key))
        ]
    if isinstance(value, list):
        return [
            leaf
            for index, item in enumerate(value)
            for leaf in _leaf_paths(item, (*path, str(index)))
        ]
    return [path]


def output_payload(output: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Return the raw oracle response represented by a committed fixture."""
    response = output.get("response")
    if response is not None:
        return require_object(response, name="output.response")
    return {key: value for key, value in output.items() if key not in FIXTURE_METADATA}


def validate_actual_output(
    actual: dict[str, JsonValue], expected: dict[str, JsonValue]
) -> None:
    """Validate a raw oracle response by attaching its committed fixture metadata."""
    if expected.get("operation") == "health" or "response" in expected:
        fixture = {key: value for key, value in expected.items() if key != "response"}
        fixture["response"] = actual
    else:
        fixture = {key: expected[key] for key in FIXTURE_METADATA}
        fixture.update(actual)
    validate_document(fixture, OUTPUT_SCHEMA)


def validate_case_pair(
    case_path: Path,
    expected_path: Path,
    policies: dict[str, ComparisonPolicy] | None = None,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue], ComparisonPolicy]:
    """Validate one case, its expected output, and all cross-document links."""
    case = require_object(load_json(case_path), name=str(case_path))
    output = require_object(load_json(expected_path), name=str(expected_path))
    validate_document(case, CASE_SCHEMA)
    validate_document(output, OUTPUT_SCHEMA)
    if case["case_id"] != case_path.stem:
        raise ContractValidationError(f"{case_path}: case_id must match the file stem")
    if case["case_id"] != output["case_id"]:
        raise ContractValidationError(f"{case_path}: output case_id does not match")
    if case["expected_output"] != expected_path.name:
        raise ContractValidationError(
            f"{case_path}: expected_output link does not match"
        )
    payload = output_payload(output)
    if case["operation"] != payload.get("operation"):
        raise ContractValidationError(f"{case_path}: operation does not match output")
    reference = require_object(output["reference"], name="output.reference")
    if reference["protocol_version"] != payload.get("protocol_version"):
        raise ContractValidationError(f"{case_path}: protocol versions do not match")
    if case["operation"] == "ols_rcs":
        x = require_array(case["x"], name="case.x")
        y = require_array(case["y"], name="case.y")
        if len(x) != len(y):
            raise ContractValidationError(f"{case_path}: x and y lengths differ")
    if "knots" in case:
        knots = require_array(case["knots"], name="case.knots")
        numeric_knots = [float(cast(int | float, knot)) for knot in knots]
        if any(
            left >= right
            for left, right in zip(numeric_knots, numeric_knots[1:], strict=False)
        ):
            raise ContractValidationError(
                f"{case_path}: knots are not strictly increasing"
            )
    available = policies or load_policies()
    profile_name = case["comparison_profile"]
    if not isinstance(profile_name, str) or profile_name not in available:
        raise ContractValidationError(
            f"{case_path}: unknown comparison profile {profile_name!r}"
        )
    policy = available[profile_name]
    leaf_paths = _leaf_paths(payload)
    for path_rule in policy.rules:
        if not any(
            len(path_rule.path) == len(leaf_path)
            and all(
                expected == "*" or expected == actual
                for expected, actual in zip(path_rule.path, leaf_path, strict=True)
            )
            for leaf_path in leaf_paths
        ):
            raise ContractValidationError(
                f"{case_path}: comparison path matches no output field: "
                f"{_format_path(path_rule.path)}"
            )
    return case, output, policy


def discover_case_pairs() -> list[tuple[Path, Path]]:
    """Discover all committed cases and resolve their declared expected outputs."""
    pairs: list[tuple[Path, Path]] = []
    expected_names: set[str] = set()
    for case_path in sorted(CASES.glob("*.json")):
        case = require_object(load_json(case_path), name=str(case_path))
        expected_name = case.get("expected_output")
        if not isinstance(expected_name, str):
            raise ContractValidationError(f"{case_path}: expected_output is missing")
        if expected_name in expected_names:
            raise ContractValidationError(
                f"multiple cases reference expected output {expected_name}"
            )
        expected_names.add(expected_name)
        expected_path = EXPECTED / expected_name
        if not expected_path.is_file():
            raise ContractValidationError(
                f"{case_path}: missing expected output {expected_name}"
            )
        pairs.append((case_path, expected_path))
    orphaned = sorted(
        path.name for path in EXPECTED.glob("*.json") if path.name not in expected_names
    )
    if orphaned:
        raise ContractValidationError(f"orphaned expected outputs: {orphaned}")
    return pairs


def validate_repository_contracts() -> int:
    """Validate all schemas, policies, fixtures, and cross-document references."""
    for schema_path in (CASE_SCHEMA, OUTPUT_SCHEMA, EVIDENCE_SCHEMA, POLICY_SCHEMA):
        schema = require_object(load_json(schema_path), name=str(schema_path))
        Draft202012Validator.check_schema(schema)
    policies = load_policies()
    pairs = discover_case_pairs()
    used_profiles: set[str] = set()
    for case_path, expected_path in pairs:
        _, _, policy = validate_case_pair(case_path, expected_path, policies)
        used_profiles.add(policy.name)
    unused_profiles = sorted(policies.keys() - used_profiles)
    if unused_profiles:
        raise ContractValidationError(f"unused comparison profiles: {unused_profiles}")
    return len(pairs)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(value: JsonValue) -> str:
    content = json.dumps(
        value, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(content).hexdigest()


def current_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    revision = completed.stdout.strip()
    if completed.returncode == 0 and len(revision) == 40:
        return revision
    return "unknown"


def working_tree_dirty() -> bool:
    """Return a conservative dirty-tree marker for local evidence provenance."""
    completed = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.returncode != 0 or bool(completed.stdout.strip())


def build_evidence(
    *,
    case_path: Path,
    expected_path: Path,
    case: dict[str, JsonValue],
    expected: dict[str, JsonValue],
    actual: dict[str, JsonValue],
    report: ComparisonReport,
    code_revision: str | None = None,
    source_is_dirty: bool | None = None,
    evaluated_at: datetime | None = None,
) -> dict[str, JsonValue]:
    """Build and validate an auditable comparison evidence document."""
    timestamp = evaluated_at or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("evidence timestamp must be timezone-aware")
    timestamp = timestamp.astimezone(UTC)
    timestamp_text = timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
    revision = code_revision or current_revision()
    case_id = str(case["case_id"])
    actual_digest = sha256_json(actual)
    evidence_seed = f"{case_id}\0{revision}\0{timestamp_text}\0{actual_digest}"
    evidence_id = hashlib.sha256(evidence_seed.encode()).hexdigest()
    reference = require_object(expected["reference"], name="expected.reference")
    evidence: dict[str, JsonValue] = {
        "schema_version": "holocron-parity-evidence/v1",
        "evidence_id": evidence_id,
        "case_id": case_id,
        "evaluated_at_utc": timestamp_text,
        "source": {
            "code_revision": revision,
            "working_tree_dirty": (
                working_tree_dirty() if source_is_dirty is None else source_is_dirty
            ),
        },
        "oracle": dict(reference),
        "implementation": {
            "package": "holocron-rms",
            "version": __version__,
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "artifacts": {
            "case_path": case_path.relative_to(ROOT).as_posix(),
            "case_sha256": sha256_file(case_path),
            "expected_output_path": expected_path.relative_to(ROOT).as_posix(),
            "expected_output_sha256": sha256_file(expected_path),
            "actual_output_sha256": actual_digest,
        },
        "comparison": {
            "profile": report.profile,
            "outcome": "passed" if report.passed else "failed",
            "exact_comparisons": report.exact_comparisons,
            "numeric_comparisons": report.numeric_comparisons,
            "maximum_absolute_error": report.maximum_absolute_error,
            "maximum_relative_error": report.maximum_relative_error,
            "mismatches": list(report.mismatches),
        },
    }
    validate_document(evidence, EVIDENCE_SCHEMA)
    return evidence


def write_evidence(path: Path, evidence: dict[str, JsonValue]) -> str:
    """Validate and atomically write evidence, returning its content digest."""
    validate_document(evidence, EVIDENCE_SCHEMA)
    content = (
        json.dumps(evidence, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary.write(content)
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return hashlib.sha256(content).hexdigest()
