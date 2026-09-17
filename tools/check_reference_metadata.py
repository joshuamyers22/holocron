"""Validate committed Phase 0 reference and compatibility metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "reference/manifests/rms-8.2-0-inventory.json"
CHECKSUM_PATH = ROOT / "reference/manifests/rms-8.2-0-files.sha256"
COMPATIBILITY_PATH = ROOT / "compatibility/rms-8.2.0.yaml"
VALID_STATUSES = {"experimental", "implemented", "mapped", "unsupported", "deferred"}


def load_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return cast(dict[str, object], value)


def require_list(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{name} must be a list")
    return cast(list[object], value)


def main() -> None:
    inventory = load_object(INVENTORY_PATH)
    compatibility = load_object(COMPATIBILITY_PATH)
    checksum_bytes = CHECKSUM_PATH.read_bytes()
    checksum_lines = checksum_bytes.decode().splitlines()
    expected_digest = hashlib.sha256(checksum_bytes).hexdigest()
    if inventory["file_manifest_sha256"] != expected_digest:
        raise ValueError("file manifest digest does not match the inventory")
    if inventory["file_count"] != len(checksum_lines):
        raise ValueError("file manifest count does not match the inventory")
    if len(set(checksum_lines)) != len(checksum_lines):
        raise ValueError("file manifest contains duplicate entries")

    exports = {
        str(value) for value in require_list(inventory["exports"], name="exports")
    }
    methods = {
        str(value) for value in require_list(inventory["s3_methods"], name="s3_methods")
    }
    registered_fortran = inventory["registered_fortran"]
    if not isinstance(registered_fortran, dict) or not registered_fortran:
        raise ValueError("native routine inventory is missing")
    registered_fortran_map = cast(dict[str, object], registered_fortran)
    environment = load_object(ROOT / "reference/expected/oracle-environment.json")
    response = environment["response"]
    if not isinstance(response, dict):
        raise TypeError("oracle environment response must be an object")
    response_map = cast(dict[str, object], response)
    if response_map.get("registered_fortran") != registered_fortran_map:
        raise ValueError("source and executable native routine inventories differ")
    expected_ids = {
        *(f"export:{name}" for name in exports),
        *(f"s3_method:{name}" for name in methods),
    }
    capabilities = require_list(compatibility["capabilities"], name="capabilities")
    actual_ids: set[str] = set()
    for index, raw_capability in enumerate(capabilities):
        if not isinstance(raw_capability, dict):
            raise TypeError(f"capabilities[{index}] must be an object")
        capability = cast(dict[str, object], raw_capability)
        identifier = str(capability["id"])
        if identifier in actual_ids:
            raise ValueError(f"duplicate compatibility identifier: {identifier}")
        actual_ids.add(identifier)
        if capability["status"] not in VALID_STATUSES:
            raise ValueError(f"invalid status for {identifier}")
        if not capability["owner"]:
            raise ValueError(f"missing owner for {identifier}")
        if capability["status"] in {"experimental", "implemented"}:
            if (
                not capability["python_entry_point"]
                or not capability["tolerance_profile"]
            ):
                raise ValueError(f"incomplete evidence metadata for {identifier}")
            cases = require_list(capability["oracle_cases"], name=f"{identifier}.cases")
            if not cases:
                raise ValueError(f"missing oracle cases for {identifier}")
            for case in cases:
                case_name = str(case)
                if not (ROOT / f"reference/cases/{case_name}.json").is_file():
                    raise ValueError(
                        f"missing oracle input for {identifier}: {case_name}"
                    )
                if not (ROOT / f"reference/expected/{case_name}.json").is_file():
                    raise ValueError(
                        f"missing oracle output for {identifier}: {case_name}"
                    )
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise ValueError(
            f"compatibility coverage mismatch; missing={missing}, extra={extra}"
        )
    if compatibility["capability_count"] != len(capabilities):
        raise ValueError("capability count does not match entries")

    print(
        "reference metadata verified: "
        f"{len(checksum_lines)} files, {len(exports)} exports, "
        f"{len(methods)} S3 methods, {len(registered_fortran_map)} Fortran routines"
    )


if __name__ == "__main__":
    main()
