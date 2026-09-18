"""Measure implemented Python parity against named policies on this platform."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import numpy as np

from reference.contracts import (
    CASES,
    EXPECTED,
    POLICY_PATH,
    ROOT,
    TOLERANCE_PILOT_SCHEMA,
    JsonValue,
    compare_json,
    current_revision,
    load_json,
    output_payload,
    require_object,
    sha256_file,
    validate_case_pair,
    validate_document,
    working_tree_dirty,
)
from reference.python_parity import build_python_output

ACCEPTED_PROFILES = (
    "data-distribution-v1",
    "deterministic-transform-v1",
    "well-conditioned-ols-v1",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".work/tolerance-pilot.json",
        help="path for the schema-validated report",
    )
    return parser.parse_args()


def _numerical_library(name: str) -> str:
    configuration = cast(dict[str, object], np.show_config(mode="dicts"))
    dependencies = cast(dict[str, object], configuration.get("Build Dependencies", {}))
    dependency = cast(dict[str, object], dependencies.get(name, {}))
    library = str(dependency.get("name", "unknown"))
    version = str(dependency.get("version", "unknown"))
    return f"{library} {version}"


def build_report() -> dict[str, JsonValue]:
    results: list[dict[str, JsonValue]] = []
    oracle: dict[str, JsonValue] | None = None
    for case_path in sorted(CASES.glob("*.json")):
        raw_case = require_object(load_json(case_path), name=str(case_path))
        if raw_case.get("qualification_stage") != "python-parity":
            continue
        expected_path = EXPECTED / str(raw_case["expected_output"])
        case, expected, policy = validate_case_pair(case_path, expected_path)
        if policy.name not in ACCEPTED_PROFILES:
            raise ValueError(f"unaccepted pilot profile: {policy.name}")
        reference = require_object(expected["reference"], name="expected.reference")
        if oracle is None:
            oracle = dict(reference)
        elif oracle != reference:
            raise ValueError("pilot cases do not share one oracle identity")
        actual = build_python_output(case)
        comparison = compare_json(actual, output_payload(expected), policy)
        results.append(
            {
                "case_id": str(case["case_id"]),
                "profile": policy.name,
                "outcome": "passed" if comparison.passed else "failed",
                "exact_comparisons": comparison.exact_comparisons,
                "numeric_comparisons": comparison.numeric_comparisons,
                "maximum_absolute_error": comparison.maximum_absolute_error,
                "maximum_relative_error": comparison.maximum_relative_error,
                "mismatches": list(comparison.mismatches),
            }
        )
    if oracle is None or not results:
        raise ValueError("no Python parity cases were discovered")
    failed = sum(result["outcome"] == "failed" for result in results)
    report: dict[str, JsonValue] = {
        "schema_version": "holocron-tolerance-pilot/v1",
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "source_revision": current_revision(),
        "source_is_dirty": working_tree_dirty(),
        "environment": {
            "operating_system": platform.system(),
            "operating_system_release": platform.release(),
            "machine": platform.machine(),
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "blas": _numerical_library("blas"),
            "lapack": _numerical_library("lapack"),
        },
        "oracle": oracle,
        "policy": {
            "path": POLICY_PATH.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(POLICY_PATH),
            "accepted_profiles": list(ACCEPTED_PROFILES),
        },
        "cases": cast(JsonValue, results),
        "summary": {
            "outcome": "passed" if failed == 0 else "failed",
            "case_count": len(results),
            "failed_case_count": failed,
            "maximum_absolute_error": max(
                cast(float, result["maximum_absolute_error"]) for result in results
            ),
            "maximum_relative_error": max(
                cast(float, result["maximum_relative_error"]) for result in results
            ),
        },
    }
    validate_document(report, TOLERANCE_PILOT_SCHEMA)
    return report


def main() -> None:
    args = parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report = build_report()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    compact = json.dumps(report, separators=(",", ":"), sort_keys=True)
    print(f"TOLERANCE_PILOT_REPORT={compact}")
    summary = require_object(report["summary"], name="report.summary")
    if summary["outcome"] != "passed":
        raise SystemExit("tolerance pilot failed")


if __name__ == "__main__":
    main()
