"""Validate migration-catalog generation and the deprecation lifecycle."""

from __future__ import annotations

import hashlib
import importlib
import json
import re
import tomllib
from collections import Counter
from datetime import date
from pathlib import Path
from typing import cast

from holocron.migration import deprecation_notices, migration_catalog
from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)
from tools.generate_migration_catalog import (
    COMPATIBILITY,
    DEPRECATIONS,
    OUTPUT,
    render,
)

ROOT = Path(__file__).resolve().parents[1]
DEPRECATION_SCHEMA = ROOT / "schemas/deprecation-policy.schema.json"
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(value: object) -> tuple[int, int, int]:
    match = VERSION_PATTERN.match(str(value))
    if match is None:
        raise ValueError(f"invalid package version: {value}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _resolve(path: object) -> object:
    if not isinstance(path, str) or not path.startswith("holocron."):
        raise ValueError(f"invalid public Python path: {path}")
    parts = path.split(".")
    if len(parts) < 3:
        raise ValueError(f"public Python path lacks a domain: {path}")
    resolved: object = importlib.import_module(".".join(parts[:2]))
    for part in parts[2:]:
        resolved = getattr(resolved, part)
    return resolved


def validate_notice(
    notice: dict[str, JsonValue], *, minimum_releases: int, minimum_days: int
) -> None:
    """Validate one notice against the repository deprecation policy."""
    deprecated = _version(notice["deprecated_in"])
    removal = _version(notice["removal_not_before_version"])
    version_window_met = removal[0] > deprecated[0] or (
        removal[0] == deprecated[0] and removal[1] >= deprecated[1] + minimum_releases
    )
    if not version_window_met:
        raise ValueError(f"deprecation version window is too short: {notice['api']}")
    deprecated_on = date.fromisoformat(cast(str, notice["deprecated_on"]))
    removal_on = date.fromisoformat(cast(str, notice["removal_not_before_date"]))
    if (removal_on - deprecated_on).days < minimum_days:
        raise ValueError(f"deprecation date window is too short: {notice['api']}")
    _resolve(notice["replacement"])
    if notice["status"] == "active":
        _resolve(notice["api"])


def main() -> None:
    raw_policy = load_json(DEPRECATIONS)
    validate_document(raw_policy, DEPRECATION_SCHEMA)
    policy = require_object(raw_policy, name="deprecation policy")
    pyproject = cast(
        dict[str, object], tomllib.loads((ROOT / "pyproject.toml").read_text())
    )
    project = cast(dict[str, object], pyproject["project"])
    if policy["package_version"] != project["version"]:
        raise ValueError("deprecation policy package version is stale")
    policy_rules = require_object(policy["policy"], name="deprecation rules")
    minimum_releases = cast(int, policy_rules["minimum_minor_releases"])
    minimum_days = cast(int, policy_rules["minimum_days"])
    notices = [
        require_object(value, name="deprecation notice")
        for value in require_array(policy["notices"], name="deprecation notices")
    ]
    apis = [str(notice["api"]) for notice in notices]
    if len(set(apis)) != len(apis):
        raise ValueError("deprecation registry contains duplicate APIs")
    for notice in notices:
        validate_notice(
            notice, minimum_releases=minimum_releases, minimum_days=minimum_days
        )

    expected_catalog = render()
    if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected_catalog:
        raise ValueError("installed migration catalog is stale")
    catalog_document = cast(JsonValue, json.loads(expected_catalog))
    catalog = require_object(catalog_document, name="migration catalog")
    sources = require_object(catalog["source_sha256"], name="catalog sources")
    if sources != {
        "compatibility_manifest": _sha256(COMPATIBILITY),
        "deprecation_policy": _sha256(DEPRECATIONS),
    }:
        raise ValueError("migration catalog source hashes differ")
    entries = migration_catalog()
    counts = Counter(entry.disposition for entry in entries)
    if counts != {"experimental": 50, "mapped": 125, "unsupported": 106}:
        raise ValueError("migration catalog dispositions differ")
    for entry in entries:
        if entry.python_entry_point is not None:
            _resolve(entry.python_entry_point)
    if len(deprecation_notices()) != len(notices):
        raise ValueError("installed deprecation notices differ")
    print(
        "migration policy verified: "
        f"{len(entries)} entries, {len(notices)} active/historical deprecations"
    )


if __name__ == "__main__":
    main()
