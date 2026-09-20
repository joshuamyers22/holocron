from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from typing import cast

from reference.contracts import (
    JsonValue,
    load_json,
    require_object,
    validate_document,
)
from tools.check_phase_9_release_candidates import (
    PLAN,
    PLAN_SCHEMA,
    PROGRAM_SCHEMA,
    ROOT,
    check,
    evaluate_program,
    require_releasable_candidate,
    validate_candidate_artifacts,
    validate_releasable_candidate,
)


def _candidate(ordinal: int, *, status: str) -> dict[str, JsonValue]:
    version = f"1.0.0rc{ordinal}"
    return {
        "candidate_id": f"holocron-{version}",
        "ordinal": ordinal,
        "version": version,
        "tag": f"v{version}",
        "source_revision": str(ordinal) * 40,
        "built_on": "2026-09-19",
        "artifact_sha256": {"wheel": "a" * 64, "sdist": "b" * 64},
        "checks": ["make-check", "make-audit", "clean-artifact-smoke"],
        "status": status,
    }


def _approval(candidate: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "candidate_id": candidate["candidate_id"],
        "reviewer_id": "license-reviewer-qualified-1",
        "role": "qualified-license-provenance-reviewer",
        "approved_on": "2026-09-19",
        "approved_source_revision": candidate["source_revision"],
        "license_approved": True,
        "provenance_approved": True,
        "package_name_approved": True,
        "notices_approved": True,
        "external_beta_authorized": True,
        "record": "governance/phase-9-distribution-approvals/example.md",
    }


def _feedback(
    ordinal: int, reviewer: int, workflows: list[str]
) -> dict[str, JsonValue]:
    return {
        "feedback_id": f"feedback-{ordinal}-{reviewer}",
        "candidate_id": f"holocron-1.0.0rc{ordinal}",
        "reviewer_id": f"external-beta-{reviewer}",
        "independence_attested": True,
        "retention_consent": True,
        "received_on": "2026-09-19",
        "environment": {
            "operating_system": "Example OS",
            "python": "3.12.14",
            "install_source": "wheel",
        },
        "workflows": cast(JsonValue, workflows),
        "outcome": "completed",
        "ratings": {
            "usability": 4,
            "documentation": 4,
            "statistical_clarity": 4,
        },
        "summary": "Synthetic validator fixture; not external beta evidence.",
        "findings": [],
    }


def _complete_program() -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    plan = require_object(load_json(PLAN), name="plan")
    first = _candidate(1, status="superseded")
    second = _candidate(2, status="accepted")
    program: dict[str, JsonValue] = {
        "schema_version": "holocron-phase-9-beta-program/v1",
        "plan_id": "phase-9-private-beta-v1",
        "status": "complete",
        "blockers": [],
        "distribution_approvals": [_approval(first), _approval(second)],
        "candidates": [first, second],
        "feedback": [
            _feedback(1, 1, ["design-and-core-modeling", "survival"]),
            _feedback(
                2,
                2,
                ["validation-and-calibration", "graphics-and-reporting"],
            ),
            _feedback(2, 3, ["migration"]),
        ],
    }
    return plan, program


class PhaseNineReleaseCandidateTests(unittest.TestCase):
    def test_committed_program_is_valid_and_explicitly_blocked(self) -> None:
        summary = check()

        self.assertEqual(summary.status, "blocked")
        self.assertEqual(summary.candidate_count, 0)
        self.assertEqual(summary.reviewer_count, 0)
        self.assertEqual(summary.blocker_count, 3)
        self.assertFalse(summary.complete)
        self.assertIn("need 2 more candidates", summary.incomplete_reasons)
        self.assertIn("need 3 more external reviewers", summary.incomplete_reasons)

    def test_complete_series_requires_candidates_approvals_and_feedback(self) -> None:
        plan, program = _complete_program()

        validate_document(plan, PLAN_SCHEMA)
        validate_document(program, PROGRAM_SCHEMA)
        summary = evaluate_program(plan, program, current_version="0.1.0")

        self.assertTrue(summary.complete)
        self.assertEqual(summary.candidate_count, 2)
        self.assertEqual(summary.reviewer_count, 3)
        self.assertEqual(summary.covered_workflow_count, 5)

    def test_feedback_without_exact_candidate_approval_is_rejected(self) -> None:
        plan, program = _complete_program()
        approvals = cast(list[JsonValue], program["distribution_approvals"])
        approvals.pop()

        with self.assertRaisesRegex(ValueError, "feedback exists without approval"):
            evaluate_program(plan, program, current_version="0.1.0")

    def test_completion_claim_fails_with_unresolved_high_finding(self) -> None:
        plan, program = _complete_program()
        feedback = cast(list[dict[str, JsonValue]], program["feedback"])
        feedback[-1]["findings"] = [
            {
                "finding_id": "unsafe-claim",
                "severity": "high",
                "summary": "Documentation overstates the supported evidence boundary.",
                "disposition": "open",
                "resolution": None,
            }
        ]

        with self.assertRaisesRegex(ValueError, "claims completion"):
            evaluate_program(plan, program, current_version="0.1.0")

    def test_feedback_schema_rejects_personal_identity_fields(self) -> None:
        _, program = _complete_program()
        mutated = copy.deepcopy(program)
        feedback = cast(list[dict[str, JsonValue]], mutated["feedback"])
        feedback[0]["reviewer_email"] = "not-retained@example.invalid"

        with self.assertRaisesRegex(ValueError, "Additional properties"):
            validate_document(mutated, PROGRAM_SCHEMA)

    def test_release_tag_requires_an_active_recorded_candidate(self) -> None:
        with self.assertRaisesRegex(ValueError, "not active"):
            require_releasable_candidate("v1.0.0rc1")

        plan, program = _complete_program()
        validate_releasable_candidate(
            plan, program, "v1.0.0rc2", current_version="0.1.0"
        )
        with self.assertRaisesRegex(ValueError, "not distributable"):
            validate_releasable_candidate(
                plan, program, "v1.0.0rc1", current_version="0.1.0"
            )

    def test_candidate_artifact_hashes_bind_exact_built_bytes(self) -> None:
        _, program = _complete_program()
        wheel = b"example wheel"
        sdist = b"example sdist"
        candidates = cast(list[dict[str, JsonValue]], program["candidates"])
        candidates[-1]["artifact_sha256"] = {
            "wheel": hashlib.sha256(wheel).hexdigest(),
            "sdist": hashlib.sha256(sdist).hexdigest(),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "holocron_rms-1.0.0rc2-py3-none-any.whl").write_bytes(wheel)
            (root / "holocron_rms-1.0.0rc2.tar.gz").write_bytes(sdist)

            validate_candidate_artifacts(program, "v1.0.0rc2", root)
            (root / "holocron_rms-1.0.0rc2.tar.gz").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "digest differs"):
                validate_candidate_artifacts(program, "v1.0.0rc2", root)

    def test_release_workflow_binds_approval_commit_and_artifact_hashes(self) -> None:
        workflow = (ROOT / ".github/workflows/release.yml").read_text()

        self.assertIn("EXTERNAL_DISTRIBUTION_APPROVED_SHA", workflow)
        self.assertIn('!= "$GITHUB_SHA"', workflow)
        self.assertIn("EXTERNAL_DISTRIBUTION_APPROVAL_RECORD", workflow)
        self.assertIn("--release-tag", workflow)
        self.assertIn("--artifact-directory dist", workflow)


if __name__ == "__main__":
    unittest.main()
