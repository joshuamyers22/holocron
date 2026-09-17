"""Run every declared case against the live oracle and emit parity evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import cast

from reference.contracts import (
    ROOT,
    JsonValue,
    build_evidence,
    compare_json,
    current_revision,
    discover_case_pairs,
    load_policies,
    output_payload,
    require_object,
    validate_actual_output,
    validate_case_pair,
    working_tree_dirty,
    write_evidence,
)

RUNNER = ROOT / "reference/r/run-oracle.sh"


def run_case(case: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Execute one validated data-only case through the constrained R runner."""
    completed = subprocess.run(
        [str(RUNNER)],
        input=json.dumps(case, allow_nan=False),
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"oracle failed for {case['case_id']} with status "
            f"{completed.returncode}: {completed.stderr.strip()}"
        )
    parsed = cast(JsonValue, json.loads(completed.stdout))
    return require_object(parsed, name=f"oracle output for {case['case_id']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=ROOT / ".work/oracle-evidence",
        help="directory for validated comparison evidence",
    )
    return parser.parse_args()


def main() -> None:
    """Validate, execute, compare, and record every committed oracle case."""
    args = parse_args()
    evidence_dir = args.evidence_dir
    if not evidence_dir.is_absolute():
        evidence_dir = ROOT / evidence_dir
    policies = load_policies()
    revision = current_revision()
    source_is_dirty = working_tree_dirty()
    pairs = discover_case_pairs()
    for case_path, expected_path in pairs:
        case, expected, policy = validate_case_pair(case_path, expected_path, policies)
        actual = run_case(case)
        validate_actual_output(actual, expected)
        report = compare_json(actual, output_payload(expected), policy)
        evidence = build_evidence(
            case_path=case_path,
            expected_path=expected_path,
            case=case,
            expected=expected,
            actual=actual,
            report=report,
            code_revision=revision,
            source_is_dirty=source_is_dirty,
        )
        evidence_path = evidence_dir / f"{case['case_id']}.json"
        digest = write_evidence(evidence_path, evidence)
        report.require_match()
        print(
            f"oracle fixture verified: {case['case_id']} "
            f"({policy.name}, evidence sha256:{digest})"
        )
    print(f"oracle contract verified: {len(pairs)} cases")


if __name__ == "__main__":
    main()
