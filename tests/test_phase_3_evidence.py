from __future__ import annotations

import hashlib
import unittest
from datetime import UTC, datetime
from pathlib import Path
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
    EDGE_REPORT_SCHEMA,
    PLAN,
    PLAN_SCHEMA,
    SIMULATION_REPORT_SCHEMA,
    run_edge_corpus,
)

ROOT = PLAN.parents[1]
SIMULATION_REPORT = ROOT / "governance/evidence/phase-3/simulation-report.json"
EDGE_REPORT = ROOT / "governance/evidence/phase-3/numerical-edge-report.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    def test_committed_reports_validate_and_bind_their_inputs(self) -> None:
        simulation = require_object(
            load_json(SIMULATION_REPORT), name="simulation report"
        )
        edge = require_object(load_json(EDGE_REPORT), name="edge report")
        validate_document(simulation, SIMULATION_REPORT_SCHEMA)
        validate_document(edge, EDGE_REPORT_SCHEMA)

        self.assertEqual(simulation["plan_sha256"], sha256(PLAN))
        self.assertEqual(edge["corpus_sha256"], sha256(CORPUS))
        self.assertEqual(simulation["outcome"], "passed")
        self.assertEqual(edge["outcome"], "passed")
        for report in (simulation, edge):
            source = require_object(report["source"], name="report.source")
            self.assertFalse(source["working_tree_dirty"])


if __name__ == "__main__":
    unittest.main()
