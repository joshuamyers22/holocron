from __future__ import annotations

import math
import unittest
from pathlib import Path

from holocron.exceptions import InputValidationError
from holocron.models import SurvivalValidationResult, validate_survival_predictions
from reference.contracts import (
    EXPECTED,
    compare_json,
    output_payload,
    validate_case_pair,
)
from reference.python_parity import build_python_output


class SurvivalValidationTests(unittest.TestCase):
    def test_matches_survival_validation_oracle_fixtures(self) -> None:
        exact_comparisons = 0
        numeric_comparisons = 0
        for name in (
            "survival-validation-horizons",
            "survival-validation-weighted",
        ):
            case, expected, policy = validate_case_pair(
                Path("reference/cases") / f"{name}.json",
                EXPECTED / f"{name}.json",
            )
            report = compare_json(
                build_python_output(case), output_payload(expected), policy
            )
            report.require_match()
            exact_comparisons += report.exact_comparisons
            numeric_comparisons += report.numeric_comparisons
        self.assertEqual(exact_comparisons, 20)
        self.assertEqual(numeric_comparisons, 52)

    def test_fixed_horizon_metrics_and_tied_predictions(self) -> None:
        result = validate_survival_predictions(
            (1, 2, 3, 4),
            (1, 1, 1, 1),
            ((0.2,), (0.5,), (0.5,), (0.8,)),
            (2.5,),
        )

        self.assertIsInstance(result, SurvivalValidationResult)
        self.assertEqual(result.case_counts, (2,))
        self.assertEqual(result.control_counts, (2,))
        self.assertEqual(result.censoring_survival, (1.0,))
        self.assertAlmostEqual(result.brier_scores[0], 0.145)
        self.assertAlmostEqual(result.aucs[0] or 0.0, 0.875)
        self.assertAlmostEqual(result.dxy[0] or 0.0, 0.75)
        self.assertAlmostEqual(result.observed_survival[0], 0.5)
        self.assertAlmostEqual(result.mean_predicted_survival[0], 0.5)
        self.assertAlmostEqual(result.calibration_errors[0], 0.0)
        self.assertIsNone(result.integrated_brier_score)
        self.assertIsNone(result.integrated_auc)
        self.assertIsNone(result.integrated_absolute_calibration_error)
        self.assertEqual(len(result.calibration_groups), 1)
        self.assertEqual(len(result.calibration_groups[0]), 3)
        self.assertEqual(len(result.threshold_metrics), 1)
        self.assertAlmostEqual(result.threshold_metrics[0].sensitivity or 0.0, 1.0)
        self.assertAlmostEqual(result.threshold_metrics[0].specificity or 0.0, 0.5)

    def test_ipcw_metrics_and_integrated_brier(self) -> None:
        result = validate_survival_predictions(
            (1, 2, 3, 4, 5, 6),
            (1, 0, 1, 0, 1, 1),
            (
                (0.75, 0.50, 0.25),
                (0.80, 0.58, 0.32),
                (0.70, 0.45, 0.20),
                (0.85, 0.65, 0.40),
                (0.90, 0.72, 0.48),
                (0.92, 0.78, 0.55),
            ),
            (2.5, 4.5, 5.5),
        )

        self.assertEqual(result.case_counts, (1, 2, 3))
        self.assertEqual(result.control_counts, (4, 2, 1))
        self.assertTrue(all(value > 0.0 for value in result.brier_scores))
        self.assertTrue(all(value < 1.0 for value in result.censoring_survival))
        self.assertIsNotNone(result.integrated_brier_score)
        self.assertIsNotNone(result.integrated_auc)
        self.assertIsNotNone(result.integrated_absolute_calibration_error)
        assert result.integrated_brier_score is not None
        assert result.integrated_auc is not None
        assert result.integrated_absolute_calibration_error is not None
        expected = (
            2.0 * (result.brier_scores[0] + result.brier_scores[1]) / 2.0
            + (result.brier_scores[1] + result.brier_scores[2]) / 2.0
        ) / 3.0
        self.assertAlmostEqual(result.integrated_brier_score, expected)
        expected_auc = (
            2.0 * ((result.aucs[0] or 0.0) + (result.aucs[1] or 0.0)) / 2.0
            + ((result.aucs[1] or 0.0) + (result.aucs[2] or 0.0)) / 2.0
        ) / 3.0
        self.assertAlmostEqual(result.integrated_auc, expected_auc)
        expected_calibration = (
            2.0
            * (abs(result.calibration_errors[0]) + abs(result.calibration_errors[1]))
            / 2.0
            + (abs(result.calibration_errors[1]) + abs(result.calibration_errors[2]))
            / 2.0
        ) / 3.0
        self.assertAlmostEqual(
            result.integrated_absolute_calibration_error,
            expected_calibration,
        )

    def test_frequency_weights_match_row_replication(self) -> None:
        times = (1, 2, 3, 4)
        events = (1, 0, 1, 1)
        predictions = ((0.4, 0.2), (0.7, 0.5), (0.6, 0.3), (0.8, 0.6))
        weights = (1, 2, 1, 3)
        weighted = validate_survival_predictions(
            times, events, predictions, (2.5, 3.5), weights=weights
        )
        expanded_times = tuple(
            time
            for time, weight in zip(times, weights, strict=True)
            for _ in range(weight)
        )
        expanded_events = tuple(
            event
            for event, weight in zip(events, weights, strict=True)
            for _ in range(weight)
        )
        expanded_predictions = tuple(
            row
            for row, weight in zip(predictions, weights, strict=True)
            for _ in range(weight)
        )
        replicated = validate_survival_predictions(
            expanded_times,
            expanded_events,
            expanded_predictions,
            (2.5, 3.5),
        )

        for actual_values, expected_values in (
            (weighted.brier_scores, replicated.brier_scores),
            (weighted.aucs, replicated.aucs),
            (weighted.observed_survival, replicated.observed_survival),
            (
                weighted.mean_predicted_survival,
                replicated.mean_predicted_survival,
            ),
        ):
            for actual, expected in zip(actual_values, expected_values, strict=True):
                assert actual is not None and expected is not None
                self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(
            weighted.threshold_metrics,
            replicated.threshold_metrics,
            strict=True,
        ):
            self.assertEqual(actual.sensitivity, expected.sensitivity)
            self.assertEqual(actual.specificity, expected.specificity)
            self.assertAlmostEqual(actual.accuracy, expected.accuracy)
        for actual_horizon, expected_horizon in zip(
            weighted.calibration_groups,
            replicated.calibration_groups,
            strict=True,
        ):
            self.assertEqual(len(actual_horizon), len(expected_horizon))
            for actual, expected in zip(actual_horizon, expected_horizon, strict=True):
                self.assertAlmostEqual(
                    actual.mean_predicted_survival,
                    expected.mean_predicted_survival,
                )
                self.assertAlmostEqual(
                    actual.observed_survival,
                    expected.observed_survival,
                )

    def test_undefined_discrimination_and_invalid_inputs(self) -> None:
        no_cases = validate_survival_predictions(
            (2, 3, 4),
            (0, 1, 1),
            ((0.9,), (0.8,), (0.7,)),
            (1.0,),
        )
        self.assertEqual(no_cases.aucs, (None,))
        self.assertEqual(no_cases.dxy, (None,))

        invalid_calls = (
            lambda: validate_survival_predictions(
                (1, 2), (1,), ((0.8,), (0.7,)), (1.5,)
            ),
            lambda: validate_survival_predictions(
                (1, 2), (1, 0), ((0.8, 0.9), (0.7, 0.6)), (1.0, 2.0)
            ),
            lambda: validate_survival_predictions(
                (1, 2), (1, 0), ((0.8,), (math.nan,)), (1.5,)
            ),
            lambda: validate_survival_predictions(
                (1, 2), (1, 0), ((0.8,), (0.7,)), (1.5,), weights=(1, 0)
            ),
            lambda: validate_survival_predictions(
                (1, 2),
                (1, 0),
                ((0.8,), (0.7,)),
                (1.5,),
                calibration_groups=0,
            ),
            lambda: validate_survival_predictions(
                (1, 2),
                (1, 0),
                ((0.8,), (0.7,)),
                (1.5,),
                risk_thresholds=(0.7, 0.3),
            ),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(InputValidationError):
                call()


if __name__ == "__main__":
    unittest.main()
