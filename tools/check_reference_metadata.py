"""Validate committed Phase 0 reference and compatibility metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from reference.contracts import (
    CASES,
    TOLERANCE_PILOT_SCHEMA,
    load_json,
    require_array,
    require_object,
    validate_document,
    validate_repository_contracts,
)

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "reference/manifests/rms-8.2-0-inventory.json"
CHECKSUM_PATH = ROOT / "reference/manifests/rms-8.2-0-files.sha256"
COMPATIBILITY_PATH = ROOT / "compatibility/rms-8.2.0.yaml"
VALID_STATUSES = {"experimental", "implemented", "mapped", "unsupported", "deferred"}
TOLERANCE_EVIDENCE = ROOT / "governance/evidence/tolerance-pilot"
PHASE_ONE_POLICY_SHA256 = (
    "6809ba3f7ac364ec378eaff42c51a80aeae883ab3e7cf2f6933e7653c65fc6d8"
)


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
    parity_case_count = validate_repository_contracts()
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
    linked_cases: set[str] = set()
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
        cases = require_list(capability["oracle_cases"], name=f"{identifier}.cases")
        if capability["status"] in {"experimental", "implemented"}:
            if (
                not capability["python_entry_point"]
                or not capability["tolerance_profile"]
            ):
                raise ValueError(f"incomplete evidence metadata for {identifier}")
            if not cases:
                raise ValueError(f"missing oracle cases for {identifier}")
        if cases:
            if not capability["tolerance_profile"]:
                raise ValueError(f"missing oracle profile for {identifier}")
            for case in cases:
                case_name = str(case)
                if case_name in linked_cases:
                    raise ValueError(f"oracle case linked more than once: {case_name}")
                linked_cases.add(case_name)
                case_path = ROOT / f"reference/cases/{case_name}.json"
                if not case_path.is_file():
                    raise ValueError(
                        f"missing oracle input for {identifier}: {case_name}"
                    )
                if not (ROOT / f"reference/expected/{case_name}.json").is_file():
                    raise ValueError(
                        f"missing oracle output for {identifier}: {case_name}"
                    )
                case_document = load_object(case_path)
                if (
                    case_document["comparison_profile"]
                    != capability["tolerance_profile"]
                ):
                    raise ValueError(f"compatibility profile differs from {case_name}")
    if actual_ids != expected_ids:
        missing = sorted(expected_ids - actual_ids)
        extra = sorted(actual_ids - expected_ids)
        raise ValueError(
            f"compatibility coverage mismatch; missing={missing}, extra={extra}"
        )
    statistical_cases = {path.stem for path in CASES.glob("*.json")} - {"health"}
    if linked_cases != statistical_cases:
        missing = sorted(statistical_cases - linked_cases)
        extra = sorted(linked_cases - statistical_cases)
        raise ValueError(
            f"compatibility case coverage mismatch; missing={missing}, extra={extra}"
        )
    if compatibility["capability_count"] != len(capabilities):
        raise ValueError("capability count does not match entries")

    expected_pilot_cases = {
        path.stem
        for path in CASES.glob("*.json")
        if load_object(path).get("operation") in {"rcs", "ols_rcs"}
    }
    expected_reports = {
        "macos-15-arm64.json": ("Darwin", "arm64", "accelerate unknown"),
        "ubuntu-24.04-x86_64.json": (
            "Linux",
            "x86_64",
            "scipy-openblas 0.3.34.106.0",
        ),
    }
    actual_reports = {path.name for path in TOLERANCE_EVIDENCE.glob("*.json")}
    if actual_reports != set(expected_reports):
        raise ValueError("tolerance pilot platform evidence is incomplete")
    pilot_revision: object | None = None
    for filename, expected_environment in expected_reports.items():
        report_path = TOLERANCE_EVIDENCE / filename
        report = require_object(load_json(report_path), name=str(report_path))
        validate_document(report, TOLERANCE_PILOT_SCHEMA)
        if report["source_is_dirty"] is not False:
            raise ValueError(f"dirty tolerance pilot evidence: {filename}")
        if pilot_revision is None:
            pilot_revision = report["source_revision"]
        elif report["source_revision"] != pilot_revision:
            raise ValueError("tolerance pilot reports use different revisions")
        environment = require_object(
            report["environment"], name=f"{filename}.environment"
        )
        identity = (
            environment["operating_system"],
            environment["machine"],
            environment["blas"],
        )
        if identity != expected_environment:
            raise ValueError(f"unexpected tolerance pilot environment: {filename}")
        policy = require_object(report["policy"], name=f"{filename}.policy")
        if policy["sha256"] != PHASE_ONE_POLICY_SHA256:
            raise ValueError(f"unexpected Phase 1 tolerance policy: {filename}")
        summary = require_object(report["summary"], name=f"{filename}.summary")
        if summary["outcome"] != "passed" or summary["case_count"] != len(
            expected_pilot_cases
        ):
            raise ValueError(f"failed or incomplete tolerance pilot: {filename}")
        results = require_array(report["cases"], name=f"{filename}.cases")
        reported_cases = {
            str(require_object(result, name=f"{filename}.case")["case_id"])
            for result in results
        }
        if reported_cases != expected_pilot_cases:
            raise ValueError(f"tolerance pilot case coverage differs: {filename}")

    print(
        "reference metadata verified: "
        f"{len(checksum_lines)} files, {len(exports)} exports, "
        f"{len(methods)} S3 methods, {len(registered_fortran_map)} Fortran routines, "
        f"{parity_case_count} parity contracts"
    )


if __name__ == "__main__":
    main()
