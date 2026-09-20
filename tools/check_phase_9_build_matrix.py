"""Validate the Phase 9 artifact matrix and aggregate retained CI evidence."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "governance/phase-9-build-matrix.json"
PLAN_SCHEMA = ROOT / "schemas/phase-9-build-matrix.schema.json"
EVIDENCE_SCHEMA = ROOT / "schemas/phase-9-build-evidence.schema.json"
WORKFLOW = ROOT / ".github/workflows/ci.yml"

EXPECTED_CELLS = {
    "ubuntu-24.04-python-3.11": (
        "ubuntu-24.04",
        "3.11",
        "Linux",
        "24.04",
        "x86_64",
    ),
    "ubuntu-24.04-python-3.12": (
        "ubuntu-24.04",
        "3.12",
        "Linux",
        "24.04",
        "x86_64",
    ),
    "macos-15-python-3.11": ("macos-15", "3.11", "Darwin", "15", "arm64"),
    "macos-15-python-3.12": ("macos-15", "3.12", "Darwin", "15", "arm64"),
}


@dataclass(frozen=True, slots=True)
class MatrixEvidenceSummary:
    """Completion result for one retained full-matrix run."""

    source_revision: str
    matrix_ids: tuple[str, ...]
    artifact_count: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cells(plan: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    return [
        require_object(item, name=f"cells[{index}]")
        for index, item in enumerate(require_array(plan["cells"], name="cells"))
    ]


def load_plan(path: Path = PLAN) -> dict[str, JsonValue]:
    value = load_json(path)
    validate_document(value, PLAN_SCHEMA)
    plan = require_object(value, name="Phase 9 build matrix")
    cells = _cells(plan)
    actual: dict[str, tuple[str, str, str, str, str]] = {}
    for cell in cells:
        matrix_id = cast(str, cell["matrix_id"])
        if matrix_id in actual:
            raise ValueError(f"duplicate build matrix ID: {matrix_id}")
        actual[matrix_id] = (
            cast(str, cell["runner"]),
            cast(str, cell["python"]),
            cast(str, cell["system"]),
            cast(str, cell["os_version"]),
            cast(str, cell["machine"]),
        )
    if actual != EXPECTED_CELLS:
        raise ValueError("Phase 9 build plan differs from the declared full matrix")
    return plan


def check_workflow(path: Path = WORKFLOW) -> None:
    """Bind the declared matrix to the checked-in CI implementation."""
    workflow = path.read_text(encoding="utf-8")
    try:
        job = workflow.split("  artifact-matrix:\n", 1)[1].split(
            "\n  tolerance-pilot:", 1
        )[0]
    except IndexError as error:
        raise ValueError("CI artifact matrix job is missing") from error
    workflow_ids = re.findall(r'^\s+- id: "([^"]+)"$', job, flags=re.MULTILINE)
    if len(workflow_ids) != len(set(workflow_ids)) or set(workflow_ids) != set(
        EXPECTED_CELLS
    ):
        raise ValueError("CI artifact matrix IDs differ from the declared plan")
    required_fragments = [
        "python-version: ${{ matrix.python }}",
        "--require-clean",
        '--matrix-id "${{ matrix.id }}"',
        '--evidence-output ".work/phase-9-build/${{ matrix.id }}.json"',
        "retention-days: 90",
    ]
    for matrix_id, (runner, python, _, _, _) in EXPECTED_CELLS.items():
        required_fragments.append(
            f'- id: "{matrix_id}"\n'
            f'            os: "{runner}"\n'
            f'            python: "{python}"'
        )
    missing = [fragment for fragment in required_fragments if fragment not in job]
    if missing:
        raise ValueError("CI artifact matrix is missing: " + ", ".join(missing))


def check_topology() -> dict[str, JsonValue]:
    plan = load_plan()
    check_workflow()
    return plan


def aggregate_evidence(
    evidence_directory: Path, *, plan_path: Path = PLAN
) -> MatrixEvidenceSummary:
    """Require one valid successful report per cell from one clean revision."""
    plan = load_plan(plan_path)
    expected_plan_digest = _sha256(plan_path)
    reports: dict[str, dict[str, JsonValue]] = {}
    for path in sorted(evidence_directory.rglob("*.json")):
        value = load_json(path)
        validate_document(value, EVIDENCE_SCHEMA)
        report = require_object(value, name=str(path))
        matrix_id = cast(str, report["matrix_id"])
        if matrix_id in reports:
            raise ValueError(f"duplicate evidence for matrix cell: {matrix_id}")
        if matrix_id not in EXPECTED_CELLS:
            raise ValueError(f"evidence names unknown matrix cell: {matrix_id}")
        reports[matrix_id] = report
    missing = sorted(set(EXPECTED_CELLS) - set(reports))
    if missing:
        raise ValueError("missing matrix evidence: " + ", ".join(missing))
    if len(reports) != len(EXPECTED_CELLS):
        raise ValueError("unexpected extra matrix evidence")

    revisions: set[str] = set()
    artifact_count = 0
    cells_by_id = {cast(str, cell["matrix_id"]): cell for cell in _cells(plan)}
    required_checks = {
        cast(str, item)
        for item in require_array(plan["required_checks"], name="required_checks")
    }
    for matrix_id, report in reports.items():
        if report["plan_id"] != plan["plan_id"]:
            raise ValueError(f"{matrix_id} uses a different matrix plan")
        if report["plan_sha256"] != expected_plan_digest:
            raise ValueError(f"{matrix_id} matrix-plan digest differs")
        source = require_object(report["source"], name=f"{matrix_id}.source")
        revisions.add(cast(str, source["revision"]))
        environment = require_object(
            report["environment"], name=f"{matrix_id}.environment"
        )
        cell = cells_by_id[matrix_id]
        observed_python = ".".join(
            cast(str, environment["python_version"]).split(".")[:2]
        )
        observed = (
            cast(str, environment["system"]),
            cast(str, environment["os_version"]),
            cast(str, environment["machine"]),
            observed_python,
        )
        expected = (
            cast(str, cell["system"]),
            cast(str, cell["os_version"]),
            cast(str, cell["machine"]),
            cast(str, cell["python"]),
        )
        if observed != expected:
            raise ValueError(f"{matrix_id} environment differs from its plan")
        checks = require_object(report["checks"], name=f"{matrix_id}.checks")
        if set(checks) != required_checks or set(checks.values()) != {"passed"}:
            raise ValueError(f"{matrix_id} does not pass every required check")
        artifacts = require_array(report["artifacts"], name=f"{matrix_id}.artifacts")
        kinds = {
            cast(str, require_object(item, name="artifact")["kind"])
            for item in artifacts
        }
        if kinds != {"wheel", "sdist"}:
            raise ValueError(f"{matrix_id} lacks wheel or sdist evidence")
        artifact_count += len(artifacts)
    if len(revisions) != 1:
        raise ValueError("matrix evidence does not share one source revision")
    return MatrixEvidenceSummary(
        source_revision=revisions.pop(),
        matrix_ids=tuple(sorted(reports)),
        artifact_count=artifact_count,
    )


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--evidence-directory", type=Path)
    return command


def main() -> int:
    args = parser().parse_args()
    plan = check_topology()
    print(
        "Phase 9 build matrix verified: "
        f"plan={plan['plan_id']}, cells={len(_cells(plan))}"
    )
    if args.evidence_directory is not None:
        summary = aggregate_evidence(args.evidence_directory)
        print(
            "Phase 9 full-matrix evidence complete: "
            f"revision={summary.source_revision}, cells={len(summary.matrix_ids)}, "
            f"artifacts={summary.artifact_count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
