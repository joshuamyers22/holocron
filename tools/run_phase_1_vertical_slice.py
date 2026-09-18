"""Run the evidence-emitting Phase 1 design-to-prediction exit gate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from reference.contracts import (
    EXPECTED,
    ROOT,
    ComparisonReport,
    JsonValue,
    build_evidence,
    compare_json,
    current_revision,
    output_payload,
    validate_actual_output,
    validate_case_pair,
    working_tree_dirty,
    write_evidence,
)
from reference.python_parity import build_python_output

CASE_ID = "ols-rcs-explicit"
POLICY_NAME = "well-conditioned-ols-v1"
CASE_PATH = ROOT / f"reference/cases/{CASE_ID}.json"


@dataclass(frozen=True, slots=True)
class PhaseOneRun:
    """Result and retained evidence identity for one vertical-slice run."""

    evidence_path: Path
    evidence_sha256: str
    evidence: dict[str, JsonValue]
    comparison: ComparisonReport


def run_vertical_slice(
    evidence_directory: Path,
    *,
    require_clean: bool = False,
    code_revision: str | None = None,
    source_is_dirty: bool | None = None,
    evaluated_at: datetime | None = None,
) -> PhaseOneRun:
    """Generate a design, fit, predict, compare to R, and retain evidence."""
    dirty = working_tree_dirty() if source_is_dirty is None else source_is_dirty
    if require_clean and dirty:
        raise ValueError("Phase 1 exit evidence requires a clean source checkout")

    revision = code_revision or current_revision()
    if require_clean and revision == "unknown":
        raise ValueError("Phase 1 exit evidence requires a known source revision")

    expected_path = EXPECTED / f"{CASE_ID}.json"
    case, expected, policy = validate_case_pair(CASE_PATH, expected_path)
    if case["qualification_stage"] != "python-parity":
        raise ValueError("Phase 1 exit case must be qualified for Python parity")
    if case["operation"] != "ols_rcs":
        raise ValueError("Phase 1 exit case must exercise the RCS-to-OLS path")
    if policy.name != POLICY_NAME:
        raise ValueError(f"Phase 1 exit case must use {POLICY_NAME}")

    actual = build_python_output(case)
    validate_actual_output(actual, expected)
    comparison = compare_json(actual, output_payload(expected), policy)
    evidence = build_evidence(
        case_path=CASE_PATH,
        expected_path=expected_path,
        case=case,
        expected=expected,
        actual=actual,
        report=comparison,
        code_revision=revision,
        source_is_dirty=dirty,
        evaluated_at=evaluated_at,
    )
    evidence_path = evidence_directory / f"{CASE_ID}.json"
    evidence_sha256 = write_evidence(evidence_path, evidence)
    comparison.require_match()
    return PhaseOneRun(
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
        evidence=evidence,
        comparison=comparison,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        default=ROOT / ".work/phase-1-evidence",
        help="directory for the schema-validated parity evidence",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="reject a dirty checkout before producing acceptance evidence",
    )
    args = parser.parse_args()
    evidence_directory = args.evidence_dir.resolve()
    result = run_vertical_slice(
        evidence_directory,
        require_clean=args.require_clean,
    )
    try:
        displayed_path = result.evidence_path.relative_to(ROOT)
    except ValueError:
        displayed_path = result.evidence_path
    print(
        "Phase 1 vertical slice passed: "
        f"{CASE_ID}, profile={result.comparison.profile}, "
        f"exact={result.comparison.exact_comparisons}, "
        f"numeric={result.comparison.numeric_comparisons}, "
        f"evidence={displayed_path}, "
        f"sha256={result.evidence_sha256}"
    )


if __name__ == "__main__":
    main()
