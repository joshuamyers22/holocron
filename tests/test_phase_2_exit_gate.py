from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from reference.contracts import (
    PHASE_2_EXIT_EVIDENCE_SCHEMA,
    JsonValue,
    load_json,
    validate_document,
)
from tools.run_phase_2_exit_gate import run_phase_2_exit_gate


class PhaseTwoExitGateTests(unittest.TestCase):
    def test_emits_complete_schema_valid_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "phase-2-exit.json"
            result = run_phase_2_exit_gate(
                path,
                code_revision="c" * 40,
                source_is_dirty=False,
                evaluated_at=datetime(2026, 9, 18, 18, 0, tzinfo=UTC),
            )
            evidence = cast(dict[str, JsonValue], load_json(path))

        scope = cast(dict[str, JsonValue], evidence["scope"])
        summary = cast(dict[str, JsonValue], evidence["comparison_summary"])
        reconstruction = cast(
            dict[str, JsonValue], evidence["prediction_reconstruction"]
        )
        promotion = cast(dict[str, JsonValue], evidence["estimator_promotion"])
        self.assertEqual(result.case_count, 18)
        self.assertEqual(scope["case_count"], 18)
        self.assertEqual(scope["operations"], ["datadist", "design", "rcs"])
        self.assertEqual(summary["outcome"], "passed")
        self.assertGreater(cast(int, summary["exact_comparisons"]), 0)
        self.assertGreater(cast(int, summary["numeric_comparisons"]), 0)
        self.assertEqual(summary["failed_cases"], [])
        self.assertEqual(reconstruction["maximum_absolute_difference"], 0.0)
        self.assertEqual(promotion["promoted_estimators"], ["export:Glm", "export:lrm"])
        self.assertEqual(
            promotion["promotion_evidence"],
            ["governance/PHASE_3_CORE_ESTIMATORS.md"],
        )
        self.assertEqual(len(result.evidence_sha256), 64)
        validate_document(evidence, PHASE_2_EXIT_EVIDENCE_SCHEMA)

    def test_clean_acceptance_rejects_dirty_provenance(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaisesRegex(ValueError, "clean source checkout"),
        ):
            run_phase_2_exit_gate(
                Path(temporary) / "evidence.json",
                require_clean=True,
                code_revision="c" * 40,
                source_is_dirty=True,
            )

    def test_clean_acceptance_requires_a_revision(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaisesRegex(ValueError, "known source revision"),
        ):
            run_phase_2_exit_gate(
                Path(temporary) / "evidence.json",
                require_clean=True,
                code_revision="unknown",
                source_is_dirty=False,
            )


if __name__ == "__main__":
    unittest.main()
