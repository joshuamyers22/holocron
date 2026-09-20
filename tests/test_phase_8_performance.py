from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import cast

import numpy as np

from holocron.models import fit_cph
from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)
from tools.run_phase_8_profiles import (
    PLAN,
    PLAN_SCHEMA,
    REPORT_SCHEMA,
    WORKLOADS,
    run,
)


class PhaseEightPerformanceTests(unittest.TestCase):
    def test_locked_plan_is_schema_valid_and_complete(self) -> None:
        raw = load_json(PLAN)
        validate_document(raw, PLAN_SCHEMA)
        plan = require_object(raw, name="performance plan")
        workloads = [
            require_object(value, name="workload")
            for value in require_array(plan["workloads"], name="workloads")
        ]
        identifiers = {cast(str, workload["workload_id"]) for workload in workloads}

        self.assertEqual(identifiers, set(WORKLOADS))
        self.assertEqual(len(workloads), 5)
        self.assertEqual(plan["required_platforms"], ["ubuntu-24.04", "macos-15"])
        self.assertTrue(
            all(
                cast(int, workload["max_primitive_calls"]) > 0 for workload in workloads
            )
        )
        self.assertTrue(
            all(cast(int, workload["max_peak_bytes"]) > 0 for workload in workloads)
        )

    def test_profile_runner_retains_report_and_raw_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "performance-report.json"
            report = run(output)

            validate_document(report, REPORT_SCHEMA)
            self.assertEqual(report["technical_status"], "pass")
            results = cast(list[dict[str, JsonValue]], report["workloads"])
            self.assertEqual(len(results), 5)
            self.assertTrue(
                all(
                    (output.parent / cast(str, result["profile_file"])).is_file()
                    for result in results
                )
            )
            self.assertTrue(all(result["outcome"] == "passed" for result in results))

    def test_sorted_cox_path_matches_general_risk_sets(self) -> None:
        rng = np.random.default_rng(813)
        matrix = rng.normal(size=(120, 2))
        hazard = 0.12 * np.exp(0.45 * matrix[:, 0] - 0.25 * matrix[:, 1])
        event_time = rng.exponential(1.0 / hazard)
        censor_time = rng.exponential(1.0 / 0.05, size=120)
        observed = np.minimum(event_time, censor_time)
        times = tuple(float(value) for value in observed)
        events = tuple(int(value) for value in event_time <= censor_time)
        features = tuple(tuple(float(item) for item in row) for row in matrix)
        optimized = fit_cph(times, events, features)
        smallest_positive = float.fromhex("0x0.0000000000001p-1022")
        general = fit_cph(
            times,
            events,
            features,
            entry_times=(smallest_positive,) * len(times),
        )

        for actual, expected in zip(
            optimized.coefficients, general.coefficients, strict=True
        ):
            self.assertAlmostEqual(actual, expected, places=11)
        for actual, expected in zip(
            optimized.baseline_cumulative_hazard,
            general.baseline_cumulative_hazard,
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected, places=11)
        self.assertEqual(optimized.iterations, general.iterations)

        wide_features = tuple(
            (x1, x2, x1 * x2, x1 * x1, x2 * x2) for x1, x2 in features
        )
        bounded_memory = fit_cph(times, events, wide_features)
        bounded_memory_general = fit_cph(
            times,
            events,
            wide_features,
            entry_times=(smallest_positive,) * len(times),
        )
        for actual, expected in zip(
            bounded_memory.coefficients,
            bounded_memory_general.coefficients,
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected, places=10)
        for actual, expected in zip(
            bounded_memory.baseline_cumulative_hazard,
            bounded_memory_general.baseline_cumulative_hazard,
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected, places=10)


if __name__ == "__main__":
    unittest.main()
