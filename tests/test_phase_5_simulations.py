from __future__ import annotations

import unittest
from typing import cast

from reference.contracts import (
    load_json,
    require_array,
    require_object,
    validate_document,
)
from tools.run_phase_5_simulations import PLAN, PLAN_SCHEMA, SCENARIO_RUNNERS


class PhaseFiveSimulationTests(unittest.TestCase):
    def test_locked_plan_is_schema_valid_and_complete(self) -> None:
        raw = load_json(PLAN)
        validate_document(raw, PLAN_SCHEMA)
        plan = require_object(raw, name="plan")
        scenarios = [
            require_object(value, name="scenario")
            for value in require_array(plan["scenarios"], name="scenarios")
        ]
        scenario_ids = {cast(str, scenario["scenario_id"]) for scenario in scenarios}
        seeds = {cast(int, scenario["seed"]) for scenario in scenarios}

        self.assertEqual(scenario_ids, set(SCENARIO_RUNNERS))
        self.assertEqual(len(scenarios), 7)
        self.assertEqual(len(seeds), 7)
        self.assertEqual(
            sum(cast(int, scenario["replications"]) for scenario in scenarios),
            1280,
        )
        self.assertEqual(plan["required_platforms"], ["ubuntu-24.04", "macos-15"])
        review = require_object(plan["independent_review"], name="independent_review")
        self.assertTrue(review["required"])
        self.assertEqual(review["status"], "approved")
        self.assertEqual(review["reviewer"], "Ron Mexico")
        self.assertEqual(review["approved_at"], "2026-09-18")


if __name__ == "__main__":
    unittest.main()
