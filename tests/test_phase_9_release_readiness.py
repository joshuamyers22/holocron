from __future__ import annotations

import copy
import unittest
from typing import cast

from reference.contracts import JsonValue, load_json, require_object, validate_document
from tools.check_phase_9_release_readiness import (
    ASSESSMENT,
    CONTROL_IDS,
    ROOT,
    SCHEMA,
    check,
    check_checklist_document,
    evaluate_assessment,
)


def _assessment() -> dict[str, JsonValue]:
    return require_object(load_json(ASSESSMENT), name="assessment")


def _items(assessment: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    return cast(list[dict[str, JsonValue]], assessment["items"])


def _ready_assessment() -> dict[str, JsonValue]:
    assessment = copy.deepcopy(_assessment())
    items = _items(assessment)
    for item in items:
        if item["disposition"] == "blocked":
            item["disposition"] = "passed"
            item["resolution_condition"] = None
    assessment["summary"] = {
        "total": 20,
        "passed": 16,
        "blocked": 0,
        "not_applicable": 4,
        "blocking_control_ids": [],
    }
    assessment["release_ready"] = True
    assessment["assessment_status"] = "ready"
    return assessment


class PhaseNineReleaseReadinessTests(unittest.TestCase):
    def test_committed_checklist_is_complete_but_release_is_blocked(self) -> None:
        summary = check()

        self.assertEqual(summary.status, "blocked")
        self.assertEqual(summary.passed, 10)
        self.assertEqual(summary.blocked, 6)
        self.assertEqual(summary.not_applicable, 4)
        self.assertFalse(summary.release_ready)
        self.assertEqual(
            summary.blockers,
            (
                "stable-release-scope",
                "candidate-beta",
                "version-tag-identity",
                "artifact-matrix",
                "artifact-sbom-provenance",
                "response-procedures",
            ),
        )

    def test_all_twenty_controls_have_one_human_disposition(self) -> None:
        assessment = _assessment()
        control_ids = tuple(
            cast(str, item["control_id"]) for item in _items(assessment)
        )

        self.assertEqual(control_ids, CONTROL_IDS)
        check_checklist_document()

    def test_schema_and_semantics_accept_a_fully_ready_future_state(self) -> None:
        assessment = _ready_assessment()

        validate_document(assessment, SCHEMA)
        summary = evaluate_assessment(assessment)

        self.assertTrue(summary.release_ready)
        self.assertEqual(summary.status, "ready")
        self.assertEqual(summary.blocked, 0)

    def test_release_ready_claim_with_blockers_is_rejected(self) -> None:
        assessment = _assessment()
        assessment["release_ready"] = True

        with self.assertRaisesRegex(ValueError, "release_ready differs"):
            evaluate_assessment(assessment)

    def test_stale_summary_is_rejected(self) -> None:
        assessment = _assessment()
        summary = require_object(assessment["summary"], name="summary")
        summary["passed"] = 11

        with self.assertRaisesRegex(ValueError, "summary passed differs"):
            evaluate_assessment(assessment)

    def test_blocked_control_requires_a_resolution_condition(self) -> None:
        assessment = _assessment()
        blocked = next(
            item for item in _items(assessment) if item["disposition"] == "blocked"
        )
        blocked["resolution_condition"] = None

        with self.assertRaisesRegex(ValueError, "lacks a resolution"):
            evaluate_assessment(assessment)

    def test_not_applicable_control_cannot_be_marked_applicable(self) -> None:
        assessment = _assessment()
        item = next(
            item
            for item in _items(assessment)
            if item["disposition"] == "not-applicable"
        )
        item["applicable"] = True

        with self.assertRaisesRegex(ValueError, "inconsistent state"):
            evaluate_assessment(assessment)

    def test_missing_or_unsafe_evidence_is_rejected(self) -> None:
        assessment = _assessment()
        _items(assessment)[0]["evidence"] = ["../outside"]

        with self.assertRaisesRegex(ValueError, "unsafe evidence path"):
            evaluate_assessment(assessment)

    def test_release_workflow_structural_and_final_gates_are_fail_closed(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIn("make phase-9-readiness-check", workflow)
        self.assertIn("make phase-9-rc-exit-gate phase-9-readiness-exit-gate", workflow)


if __name__ == "__main__":
    unittest.main()
