from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import cast

from reference.contracts import JsonValue, load_json, require_object, validate_document
from tools.check_phase_9_build_matrix import (
    EVIDENCE_SCHEMA,
    EXPECTED_CELLS,
    PLAN,
    PLAN_SCHEMA,
    ROOT,
    aggregate_evidence,
    check_topology,
    load_plan,
)


def _report(matrix_id: str, revision: str = "a" * 40) -> dict[str, JsonValue]:
    runner, python, system, os_version, machine = EXPECTED_CELLS[matrix_id]
    del runner
    plan_digest = hashlib.sha256(PLAN.read_bytes()).hexdigest()
    return {
        "schema_version": "holocron-phase-9-build-evidence/v1",
        "generated_at_utc": "2026-09-20T12:00:00Z",
        "plan_id": "phase-9-installability-matrix-v1",
        "plan_sha256": plan_digest,
        "matrix_id": matrix_id,
        "source": {"revision": revision, "clean": True},
        "environment": {
            "system": system,
            "os_version": os_version,
            "release": "example",
            "machine": machine,
            "python_implementation": "CPython",
            "python_version": f"{python}.10",
            "numpy_version": "2.5.3" if python == "3.12" else "2.4.6",
            "uv_version": "uv 0.12.7",
        },
        "project_version": "0.1.0",
        "artifacts": [
            {
                "kind": "wheel",
                "filename": "holocron_rms-0.1.0-py3-none-any.whl",
                "sha256": "b" * 64,
                "size_bytes": 100,
            },
            {
                "kind": "sdist",
                "filename": "holocron_rms-0.1.0.tar.gz",
                "sha256": "c" * 64,
                "size_bytes": 200,
            },
        ],
        "checks": {
            "clean-source-checkout": "passed",
            "wheel-build-and-inspection": "passed",
            "sdist-build-and-inspection": "passed",
            "wheel-isolated-install": "passed",
            "sdist-isolated-install": "passed",
            "dependency-consistency": "passed",
            "public-api-smoke": "passed",
        },
        "outcome": "passed",
    }


def _write_reports(directory: Path, reports: list[dict[str, JsonValue]]) -> None:
    for report in reports:
        matrix_id = cast(str, report["matrix_id"])
        (directory / f"{matrix_id}.json").write_text(
            json.dumps(report), encoding="utf-8"
        )


class PhaseNineBuildMatrixTests(unittest.TestCase):
    def test_committed_plan_and_workflow_define_exact_full_matrix(self) -> None:
        plan = check_topology()

        validate_document(plan, PLAN_SCHEMA)
        cells = cast(list[dict[str, JsonValue]], plan["cells"])
        self.assertEqual(
            {cast(str, cell["matrix_id"]) for cell in cells}, set(EXPECTED_CELLS)
        )
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("artifact-matrix:", workflow)
        self.assertIn("python-version: ${{ matrix.python }}", workflow)
        self.assertIn("retention-days: 90", workflow)

    def test_complete_evidence_requires_all_cells_on_one_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _write_reports(
                directory, [_report(matrix_id) for matrix_id in EXPECTED_CELLS]
            )

            summary = aggregate_evidence(directory)

        self.assertEqual(summary.source_revision, "a" * 40)
        self.assertEqual(summary.artifact_count, 8)
        self.assertEqual(set(summary.matrix_ids), set(EXPECTED_CELLS))

    def test_missing_cell_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _write_reports(directory, [_report(next(iter(EXPECTED_CELLS)))])

            with self.assertRaisesRegex(ValueError, "missing matrix evidence"):
                aggregate_evidence(directory)

    def test_reports_from_different_revisions_are_rejected(self) -> None:
        reports = [_report(matrix_id) for matrix_id in EXPECTED_CELLS]
        source = require_object(reports[-1]["source"], name="source")
        source["revision"] = "d" * 40
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _write_reports(directory, reports)

            with self.assertRaisesRegex(ValueError, "one source revision"):
                aggregate_evidence(directory)

    def test_plan_digest_tampering_is_rejected(self) -> None:
        reports = [_report(matrix_id) for matrix_id in EXPECTED_CELLS]
        reports[0]["plan_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            _write_reports(directory, reports)

            with self.assertRaisesRegex(ValueError, "plan digest differs"):
                aggregate_evidence(directory)

    def test_evidence_schema_rejects_a_dirty_source_claim(self) -> None:
        report = copy.deepcopy(_report(next(iter(EXPECTED_CELLS))))
        source = require_object(report["source"], name="source")
        source["clean"] = False

        with self.assertRaisesRegex(ValueError, "True was expected"):
            validate_document(report, EVIDENCE_SCHEMA)

    def test_matrix_plan_rejects_an_unapproved_fifth_cell(self) -> None:
        plan = require_object(load_json(PLAN), name="plan")
        cells = cast(list[JsonValue], plan["cells"])
        cells.append(copy.deepcopy(cells[0]))

        with self.assertRaises(ValueError):
            validate_document(plan, PLAN_SCHEMA)

    def test_load_plan_rejects_semantically_changed_cell(self) -> None:
        plan = require_object(load_json(PLAN), name="plan")
        cells = cast(list[dict[str, JsonValue]], plan["cells"])
        cells[0]["machine"] = "arm64"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "declared full matrix"):
                load_plan(path)


if __name__ == "__main__":
    unittest.main()
