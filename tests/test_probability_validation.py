from __future__ import annotations

import unittest
from pathlib import Path

from holocron.exceptions import InputValidationError
from holocron.validation import (
    ProbabilityThresholdMetrics,
    ProbabilityValidationResult,
    validate_probabilities,
)
from reference.contracts import (
    EXPECTED,
    compare_json,
    output_payload,
    validate_case_pair,
)
from reference.python_parity import build_python_output


class ProbabilityValidationTests(unittest.TestCase):
    outcomes = (0, 1, 0, 1, 0, 1, 1, 0)
    probabilities = (0.1, 0.7, 0.4, 0.6, 0.55, 0.8, 0.35, 0.45)

    def test_matches_probability_validation_oracle_fixture(self) -> None:
        case, expected, policy = validate_case_pair(
            Path("reference/cases/probability-validation-overall.json"),
            EXPECTED / "probability-validation-overall.json",
        )
        report = compare_json(
            build_python_output(case), output_payload(expected), policy
        )
        report.require_match()
        self.assertGreaterEqual(report.numeric_comparisons, 21)

    def test_broader_probability_metrics_have_declared_values(self) -> None:
        result = validate_probabilities(
            self.outcomes,
            self.probabilities,
            calibration_groups=4,
            thresholds=(0.4, 0.5, 0.6),
        )

        self.assertIsInstance(result, ProbabilityValidationResult)
        self.assertAlmostEqual(result.auc, 0.8125)
        self.assertAlmostEqual(result.dxy, 0.625)
        self.assertAlmostEqual(result.brier_score, 0.1734375)
        self.assertAlmostEqual(result.scaled_brier_score, 0.30625)
        self.assertAlmostEqual(result.log_loss, 0.5191246349893525)
        self.assertAlmostEqual(result.prevalence, 0.5)
        self.assertAlmostEqual(result.mean_prediction, 0.49375)
        self.assertAlmostEqual(result.calibration_in_the_large, 0.00625)
        self.assertAlmostEqual(result.calibration_intercept or 0.0, -0.0147003171)
        self.assertAlmostEqual(result.calibration_slope or 0.0, 1.9311250222)
        self.assertEqual(len(result.calibration_groups), 4)
        self.assertEqual(len(result.threshold_metrics), 3)
        middle = result.threshold_metrics[1]
        self.assertIsInstance(middle, ProbabilityThresholdMetrics)
        self.assertEqual(middle.threshold, 0.5)
        self.assertAlmostEqual(middle.sensitivity, 0.75)
        self.assertAlmostEqual(middle.specificity, 0.75)
        self.assertAlmostEqual(middle.accuracy, 0.75)

    def test_frequency_weights_match_row_replication(self) -> None:
        weights = (1, 2, 1, 1, 3, 1, 2, 1)
        weighted = validate_probabilities(
            self.outcomes,
            self.probabilities,
            weights=weights,
            calibration_groups=4,
            thresholds=(0.4, 0.5, 0.6),
        )
        expanded_outcomes = tuple(
            outcome
            for outcome, weight in zip(self.outcomes, weights, strict=True)
            for _ in range(weight)
        )
        expanded_probabilities = tuple(
            probability
            for probability, weight in zip(self.probabilities, weights, strict=True)
            for _ in range(weight)
        )
        replicated = validate_probabilities(
            expanded_outcomes,
            expanded_probabilities,
            calibration_groups=4,
            thresholds=(0.4, 0.5, 0.6),
        )

        for name in (
            "auc",
            "dxy",
            "brier_score",
            "scaled_brier_score",
            "log_loss",
            "nagelkerke_r_squared",
            "calibration_intercept",
            "calibration_slope",
            "spiegelhalter_z",
        ):
            actual = getattr(weighted, name)
            expected = getattr(replicated, name)
            assert actual is not None and expected is not None
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(
            len(weighted.calibration_groups), len(replicated.calibration_groups)
        )
        for actual, expected in zip(
            weighted.calibration_groups,
            replicated.calibration_groups,
            strict=True,
        ):
            self.assertAlmostEqual(actual.total_weight, expected.total_weight)
            self.assertAlmostEqual(actual.mean_prediction, expected.mean_prediction)
            self.assertAlmostEqual(
                actual.observed_frequency, expected.observed_frequency
            )
        for actual, expected in zip(
            weighted.threshold_metrics,
            replicated.threshold_metrics,
            strict=True,
        ):
            self.assertAlmostEqual(actual.accuracy, expected.accuracy)
            self.assertEqual(actual.sensitivity, expected.sensitivity)
            self.assertEqual(actual.specificity, expected.specificity)

    def test_separated_recalibration_is_explicitly_undefined(self) -> None:
        result = validate_probabilities(
            (0, 0, 1, 1),
            (0.1, 0.4, 0.6, 0.9),
            calibration_groups=2,
        )

        self.assertEqual(result.auc, 1.0)
        self.assertIsNone(result.calibration_intercept)
        self.assertIsNone(result.calibration_slope)
        self.assertIsNone(result.unreliability_chi_square)
        self.assertIsNone(result.mean_absolute_calibration_error)

    def test_invalid_probability_inputs_fail_closed(self) -> None:
        invalid_calls = (
            lambda: validate_probabilities((0, 1), (0.0, 0.8)),
            lambda: validate_probabilities((0, 0), (0.2, 0.8)),
            lambda: validate_probabilities((0, 1), (0.2, 0.8), weights=(1, 0)),
            lambda: validate_probabilities((0, 1), (0.2, 0.8), thresholds=(0.7, 0.3)),
            lambda: validate_probabilities((0, 1), (0.2, 0.8), calibration_groups=0),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(InputValidationError):
                call()


if __name__ == "__main__":
    unittest.main()
