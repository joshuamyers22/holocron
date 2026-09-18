from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from reference.contracts import JsonValue, load_json, validate_document
from tools.run_phase_1_vertical_slice import CASE_ID, run_vertical_slice


class PhaseOneVerticalSliceTests(unittest.TestCase):
    def test_emits_passing_schema_valid_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_vertical_slice(
                Path(temporary),
                code_revision="b" * 40,
                source_is_dirty=False,
                evaluated_at=datetime(2026, 9, 17, 21, 0, tzinfo=UTC),
            )
            written = load_json(result.evidence_path)

        evidence = cast(dict[str, JsonValue], written)
        source = cast(dict[str, JsonValue], evidence["source"])
        comparison = cast(dict[str, JsonValue], evidence["comparison"])
        artifacts = cast(dict[str, JsonValue], evidence["artifacts"])

        self.assertEqual(evidence["case_id"], CASE_ID)
        self.assertEqual(source["code_revision"], "b" * 40)
        self.assertIs(source["working_tree_dirty"], False)
        self.assertEqual(comparison["outcome"], "passed")
        self.assertGreater(cast(int, comparison["numeric_comparisons"]), 0)
        self.assertGreater(cast(int, comparison["exact_comparisons"]), 0)
        self.assertEqual(comparison["mismatches"], [])
        self.assertEqual(len(cast(str, artifacts["actual_output_sha256"])), 64)
        self.assertEqual(len(result.evidence_sha256), 64)
        validate_document(
            evidence, Path("schemas/parity-evidence.schema.json").resolve()
        )

    def test_clean_acceptance_rejects_dirty_provenance(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaisesRegex(ValueError, "clean source checkout"),
        ):
            run_vertical_slice(
                Path(temporary),
                require_clean=True,
                code_revision="b" * 40,
                source_is_dirty=True,
            )

    def test_clean_acceptance_requires_a_revision(self) -> None:
        with (
            tempfile.TemporaryDirectory() as temporary,
            self.assertRaisesRegex(ValueError, "known source revision"),
        ):
            run_vertical_slice(
                Path(temporary),
                require_clean=True,
                code_revision="unknown",
                source_is_dirty=False,
            )


if __name__ == "__main__":
    unittest.main()
