"""Run the evidence-emitting Phase 2 design-system exit gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from holocron import __version__
from holocron.design import DesignMatrix, DesignSpec
from holocron.models import OlsResult, fit_ols
from reference.contracts import (
    PHASE_2_EXIT_EVIDENCE_SCHEMA,
    ROOT,
    ComparisonReport,
    JsonValue,
    compare_json,
    current_revision,
    discover_case_pairs,
    load_json,
    output_payload,
    require_array,
    require_object,
    sha256_file,
    sha256_json,
    validate_actual_output,
    validate_case_pair,
    validate_document,
    working_tree_dirty,
)
from reference.python_parity import build_python_output

DESIGN_OPERATIONS = frozenset({"datadist", "design", "rcs"})
MINIMUM_CASE_COUNTS = {"datadist": 4, "design": 8, "rcs": 6}
ADVERSARIAL_CASE_ID = "design-adversarial-names"
PHASE_2_ESTIMATOR_BASELINE = {
    "export:ols": "experimental",
    "export:Glm": "deferred",
    "export:lrm": "deferred",
}
COMPATIBILITY_MANIFEST = ROOT / "compatibility/rms-8.2.0.yaml"
PHASE_3_ESTIMATOR_ACCEPTANCE = ROOT / "governance/PHASE_3_CORE_ESTIMATORS.md"


@dataclass(frozen=True, slots=True)
class PhaseTwoRun:
    """Result and retained evidence identity for one Phase 2 gate run."""

    evidence_path: Path
    evidence_sha256: str
    evidence: dict[str, JsonValue]
    case_count: int
    exact_comparisons: int
    numeric_comparisons: int


def _timestamp(value: datetime | None) -> str:
    timestamp = value or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("evidence timestamp must be timezone-aware")
    return (
        timestamp.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _case_result(
    case_path: Path,
    expected_path: Path,
    case: dict[str, JsonValue],
    actual: dict[str, JsonValue],
    report: ComparisonReport,
) -> dict[str, JsonValue]:
    return {
        "case_id": str(case["case_id"]),
        "operation": str(case["operation"]),
        "case_sha256": sha256_file(case_path),
        "expected_output_sha256": sha256_file(expected_path),
        "actual_output_sha256": sha256_json(actual),
        "profile": report.profile,
        "outcome": "passed" if report.passed else "failed",
        "exact_comparisons": report.exact_comparisons,
        "numeric_comparisons": report.numeric_comparisons,
        "maximum_absolute_error": report.maximum_absolute_error,
        "maximum_relative_error": report.maximum_relative_error,
        "mismatches": list(report.mismatches),
    }


def _design_case_data(case: dict[str, JsonValue]) -> dict[str, list[object]]:
    variables = require_array(case["variables"], name="case.variables")
    data: dict[str, list[object]] = {}
    for value in variables:
        variable = require_object(value, name="case.variables item")
        name = variable["name"]
        values = variable["values"]
        if not isinstance(name, str) or not isinstance(values, list):
            raise ValueError("adversarial design case variables are malformed")
        data[name] = cast(list[object], values)
    return data


def _prediction_reconstruction(
    case_by_id: dict[str, dict[str, JsonValue]],
) -> dict[str, JsonValue]:
    case = case_by_id[ADVERSARIAL_CASE_ID]
    formula = case["formula"]
    if not isinstance(formula, str):
        raise ValueError("adversarial design case formula is malformed")
    specification = DesignSpec.from_formula(formula)
    restored_specification = DesignSpec.from_json(specification.to_json())
    training_matrix = specification.transform(_design_case_data(case))
    restored_training_matrix = DesignMatrix.from_json(training_matrix.to_json())
    if restored_training_matrix != training_matrix:
        raise AssertionError("serialized training matrix did not reconstruct exactly")

    result = fit_ols((3.0, 2.0, 5.0, 11.0), training_matrix)
    restored_result = OlsResult.from_json(result.to_json())
    prediction_data: dict[str, list[object]] = {
        "blood pressure": [102.0, 132.0, 151.0],
        "x + code()": [-1.0, 2.0, 4.0],
    }
    original_predictions = result.predict(specification.transform(prediction_data))
    restored_predictions = restored_result.predict(
        restored_specification.transform(prediction_data)
    )
    differences = tuple(
        abs(left - right)
        for left, right in zip(original_predictions, restored_predictions, strict=True)
    )
    maximum_difference = max(differences, default=0.0)
    if maximum_difference != 0.0:
        raise AssertionError("serialized prediction reconstruction was not exact")
    if restored_result.design_fingerprint != restored_specification.fingerprint:
        raise AssertionError("reconstructed result lost its design identity")

    spec_document = specification.to_dict()
    matrix_document = training_matrix.to_dict()
    result_document = result.to_dict()
    return {
        "source_case_id": ADVERSARIAL_CASE_ID,
        "design_spec_schema_version": cast(str, spec_document["schema_version"]),
        "design_matrix_schema_version": cast(str, matrix_document["schema_version"]),
        "result_schema_version": cast(str, result_document["schema_version"]),
        "design_spec_fingerprint": specification.fingerprint,
        "training_matrix_fingerprint": training_matrix.fingerprint,
        "result_fingerprint": result.fingerprint,
        "training_rows": training_matrix.shape[0],
        "prediction_rows": len(original_predictions),
        "maximum_absolute_difference": maximum_difference,
        "outcome": "passed",
    }


def _estimator_promotion() -> dict[str, JsonValue]:
    manifest = require_object(
        load_json(COMPATIBILITY_MANIFEST), name=str(COMPATIBILITY_MANIFEST)
    )
    capabilities = require_array(manifest["capabilities"], name="capabilities")
    statuses: dict[str, str] = {}
    for value in capabilities:
        capability = require_object(value, name="capability")
        capability_id = capability.get("id")
        if capability_id in PHASE_2_ESTIMATOR_BASELINE:
            status = capability.get("status")
            if not isinstance(status, str):
                raise ValueError("estimator capability status is malformed")
            statuses[capability_id] = status
    if statuses.get("export:ols") != "experimental" or any(
        statuses.get(capability_id) not in {"deferred", "experimental"}
        for capability_id in ("export:Glm", "export:lrm")
    ):
        raise AssertionError(
            "Phase 2 estimator dispositions changed outside the accepted progression: "
            f"received {statuses}"
        )
    promoted = sorted(
        capability_id
        for capability_id, baseline in PHASE_2_ESTIMATOR_BASELINE.items()
        if baseline == "deferred" and statuses.get(capability_id) == "experimental"
    )
    if promoted and not PHASE_3_ESTIMATOR_ACCEPTANCE.is_file():
        raise AssertionError(
            "later estimator promotion requires the Phase 3 acceptance record"
        )
    return {
        "statuses": cast(dict[str, JsonValue], statuses),
        "promoted_estimators": cast(list[JsonValue], promoted),
        "promotion_evidence": (
            [PHASE_3_ESTIMATOR_ACCEPTANCE.relative_to(ROOT).as_posix()]
            if promoted
            else []
        ),
        "outcome": "passed",
    }


def _write_evidence(path: Path, evidence: dict[str, JsonValue]) -> str:
    validate_document(evidence, PHASE_2_EXIT_EVIDENCE_SCHEMA)
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


def run_phase_2_exit_gate(
    evidence_path: Path,
    *,
    require_clean: bool = False,
    code_revision: str | None = None,
    source_is_dirty: bool | None = None,
    evaluated_at: datetime | None = None,
) -> PhaseTwoRun:
    """Run every accepted design case and the reconstruction/promotion checks."""
    dirty = working_tree_dirty() if source_is_dirty is None else source_is_dirty
    if require_clean and dirty:
        raise ValueError("Phase 2 exit evidence requires a clean source checkout")
    revision = code_revision or current_revision()
    if require_clean and revision == "unknown":
        raise ValueError("Phase 2 exit evidence requires a known source revision")

    case_results: list[dict[str, JsonValue]] = []
    reports: list[ComparisonReport] = []
    case_by_id: dict[str, dict[str, JsonValue]] = {}
    references: list[dict[str, JsonValue]] = []
    operation_counts: Counter[str] = Counter()
    for case_path, expected_path in discover_case_pairs():
        case, expected, policy = validate_case_pair(case_path, expected_path)
        operation = case["operation"]
        if (
            case["qualification_stage"] != "python-parity"
            or operation not in DESIGN_OPERATIONS
        ):
            continue
        actual = build_python_output(case)
        validate_actual_output(actual, expected)
        report = compare_json(actual, output_payload(expected), policy)
        case_results.append(
            _case_result(case_path, expected_path, case, actual, report)
        )
        reports.append(report)
        case_id = str(case["case_id"])
        case_by_id[case_id] = case
        operation_counts[str(operation)] += 1
        references.append(
            require_object(expected["reference"], name="expected.reference")
        )

    for operation, minimum in MINIMUM_CASE_COUNTS.items():
        if operation_counts[operation] < minimum:
            raise AssertionError(
                f"Phase 2 requires at least {minimum} {operation} cases; "
                f"found {operation_counts[operation]}"
            )
    if ADVERSARIAL_CASE_ID not in case_by_id:
        raise AssertionError("Phase 2 adversarial-name case is missing")
    if not references or any(reference != references[0] for reference in references):
        raise AssertionError("Phase 2 cases do not share one pinned R reference")
    for report in reports:
        report.require_match()

    exact_comparisons = sum(report.exact_comparisons for report in reports)
    numeric_comparisons = sum(report.numeric_comparisons for report in reports)
    failed_cases = [
        str(result["case_id"])
        for result in case_results
        if result["outcome"] != "passed"
    ]
    comparison_summary: dict[str, JsonValue] = {
        "outcome": "passed",
        "exact_comparisons": exact_comparisons,
        "numeric_comparisons": numeric_comparisons,
        "maximum_absolute_error": max(
            (report.maximum_absolute_error for report in reports), default=0.0
        ),
        "maximum_relative_error": max(
            (report.maximum_relative_error for report in reports), default=0.0
        ),
        "profiles": cast(
            list[JsonValue], sorted({report.profile for report in reports})
        ),
        "failed_cases": cast(list[JsonValue], failed_cases),
    }
    evidence: dict[str, JsonValue] = {
        "schema_version": "holocron-phase-2-exit-evidence/v1",
        "evidence_id": "0" * 64,
        "evaluated_at_utc": _timestamp(evaluated_at),
        "source": {
            "code_revision": revision,
            "working_tree_dirty": dirty,
        },
        "oracle": references[0],
        "implementation": {
            "package": "holocron-rms",
            "version": __version__,
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "scope": {
            "qualification_stage": "python-parity",
            "operations": ["datadist", "design", "rcs"],
            "case_count": len(case_results),
        },
        "cases": cast(list[JsonValue], case_results),
        "comparison_summary": comparison_summary,
        "adversarial_naming": {
            "case_id": ADVERSARIAL_CASE_ID,
            "outcome": "passed",
        },
        "prediction_reconstruction": _prediction_reconstruction(case_by_id),
        "estimator_promotion": _estimator_promotion(),
        "outcome": "passed",
    }
    evidence["evidence_id"] = sha256_json(evidence)
    evidence_sha256 = _write_evidence(evidence_path, evidence)
    return PhaseTwoRun(
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
        evidence=evidence,
        case_count=len(case_results),
        exact_comparisons=exact_comparisons,
        numeric_comparisons=numeric_comparisons,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / ".work/phase-2-evidence/phase-2-exit.json",
        help="path for the schema-validated Phase 2 evidence",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="reject a dirty checkout before producing acceptance evidence",
    )
    args = parser.parse_args()
    result = run_phase_2_exit_gate(
        args.evidence.resolve(), require_clean=args.require_clean
    )
    try:
        displayed_path = result.evidence_path.relative_to(ROOT)
    except ValueError:
        displayed_path = result.evidence_path
    print(
        "Phase 2 exit gate passed: "
        f"cases={result.case_count}, exact={result.exact_comparisons}, "
        f"numeric={result.numeric_comparisons}, evidence={displayed_path}, "
        f"sha256={result.evidence_sha256}"
    )


if __name__ == "__main__":
    main()
