from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import cast

from reference.contracts import (
    load_json,
    require_array,
    require_object,
    validate_document,
)
from tools.run_phase_3_evidence import (
    CORPUS,
    CORPUS_SCHEMA,
    PLAN,
    PLAN_SCHEMA,
    run_edge_corpus,
)


class PhaseThreeEvidenceTests(unittest.TestCase):
    def test_locked_plan_is_schema_valid_and_complete(self) -> None:
        raw = load_json(PLAN)
        validate_document(raw, PLAN_SCHEMA)
        plan = require_object(raw, name="plan")
        scenarios = [
            require_object(value, name="scenario")
            for value in require_array(plan["scenarios"], name="scenarios")
        ]
        self.assertEqual(len(scenarios), 7)
        self.assertEqual(
            len({cast(str, scenario["scenario_id"]) for scenario in scenarios}), 7
        )
        self.assertEqual(
            len({cast(int, scenario["seed"]) for scenario in scenarios}), 7
        )
        self.assertEqual(
            sum(cast(int, scenario["replications"]) for scenario in scenarios), 2620
        )

    def test_edge_corpus_is_unique_and_covers_failure_classes(self) -> None:
        raw = load_json(CORPUS)
        validate_document(raw, CORPUS_SCHEMA)
        corpus = require_object(raw, name="corpus")
        cases = [
            require_object(value, name="case")
            for value in require_array(corpus["cases"], name="cases")
        ]
        self.assertEqual(len(cases), 16)
        self.assertEqual(
            len({cast(str, case["case_id"]) for case in cases}), len(cases)
        )
        self.assertEqual(
            {cast(str, case["category"]) for case in cases},
            {
                "bootstrap",
                "conditioning",
                "convergence",
                "degrees-of-freedom",
                "penalty",
                "rank",
                "response",
                "robust-covariance",
                "separation",
            },
        )

    def test_edge_corpus_executes_with_declared_outcomes(self) -> None:
        report = run_edge_corpus(
            revision="0" * 40,
            dirty=False,
            evaluated_at=datetime(2026, 9, 18, tzinfo=UTC),
        )
        summary = require_object(report["summary"], name="summary")
        self.assertEqual(summary["case_count"], 16)
        self.assertEqual(summary["failed_cases"], [])
        self.assertEqual(report["outcome"], "passed")


if __name__ == "__main__":
    unittest.main()
