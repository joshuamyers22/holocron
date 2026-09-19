from __future__ import annotations

import unittest

from holocron.exceptions import (
    InputValidationError,
    NumericalError,
    UnsupportedFeatureError,
)
from holocron.models import fit_lrm, fit_ols, fit_ordinal_lrm
from holocron.validation import (
    BinaryValidationIndices,
    ModelCalibrationResult,
    ModelValidationResult,
    OlsValidationIndices,
    ResamplePlan,
    calibrate_model,
    validate_model,
)


class ModelValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x = tuple(float(index) for index in range(20))
        self.features = tuple((value,) for value in self.x)
        self.ols_response = tuple(
            1.0 + 0.5 * value + 0.2 * ((index % 3) - 1)
            for index, value in enumerate(self.x)
        )
        self.binary_response = tuple(float(index % 4 in (0, 1)) for index in range(20))
        self.balanced_plan = ResamplePlan.exact(
            20,
            (
                (tuple(range(0, 20, 2)), tuple(range(1, 20, 2))),
                (tuple(range(1, 20, 2)), tuple(range(0, 20, 2))),
            ),
            plan_id="balanced-exact",
            row_ids=tuple(f"row-{index}" for index in range(20)),
        )

    def test_ols_validation_refits_and_retains_each_pair(self) -> None:
        fitted = fit_ols(
            self.ols_response,
            self.features,
            feature_names=("x",),
        )

        result = validate_model(
            fitted,
            self.ols_response,
            self.features,
            self.balanced_plan,
            row_ids=self.balanced_plan.row_ids,
        )

        self.assertIsInstance(result, ModelValidationResult)
        self.assertIsInstance(result.apparent, OlsValidationIndices)
        assert isinstance(result.apparent, OlsValidationIndices)
        self.assertEqual(result.model_family, "ols")
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.failure_rate, 0.0)
        self.assertEqual(
            result.resamples.plan_fingerprint,
            self.balanced_plan.fingerprint,
        )
        self.assertEqual(len(result.resamples.successes), 2)
        self.assertAlmostEqual(result.apparent.calibration_intercept, 0.0, places=12)
        self.assertAlmostEqual(result.apparent.calibration_slope, 1.0, places=12)
        self.assertGreater(result.apparent.r_squared or 0.0, 0.99)
        first = result.resamples.successes[0].value.assessment
        second = result.resamples.successes[1].value.assessment
        assert isinstance(first, OlsValidationIndices)
        assert isinstance(second, OlsValidationIndices)
        self.assertNotEqual(first.mean_squared_error, second.mean_squared_error)

    def test_binary_validation_uses_dxy_brier_and_logit_calibration(self) -> None:
        fitted = fit_lrm(
            self.binary_response,
            self.features,
            feature_names=("x",),
        )

        result = validate_model(
            fitted,
            self.binary_response,
            self.features,
            self.balanced_plan,
        )

        self.assertIsInstance(result.apparent, BinaryValidationIndices)
        assert isinstance(result.apparent, BinaryValidationIndices)
        self.assertEqual(result.model_family, "binary-logistic")
        self.assertEqual(result.status, "complete")
        self.assertAlmostEqual(result.apparent.dxy or 0.0, 0.2)
        self.assertAlmostEqual(result.apparent.calibration_intercept, 0.0, places=10)
        self.assertAlmostEqual(result.apparent.calibration_slope, 1.0, places=10)
        self.assertGreater(result.apparent.brier_score, 0.0)
        self.assertLess(result.apparent.brier_score, 0.25)

    def test_calibration_returns_family_specific_curve_and_resample_fits(self) -> None:
        ols = fit_ols(self.ols_response, self.features, feature_names=("x",))
        binary = fit_lrm(
            self.binary_response,
            self.features,
            feature_names=("x",),
        )

        continuous = calibrate_model(
            ols,
            self.ols_response,
            self.features,
            self.balanced_plan,
            prediction_grid=(2.0, 5.0, 8.0),
        )
        probability = calibrate_model(
            binary,
            self.binary_response,
            self.features,
            self.balanced_plan,
            prediction_grid=(0.25, 0.5, 0.75),
        )

        self.assertIsInstance(continuous, ModelCalibrationResult)
        self.assertEqual(continuous.scale, "response")
        self.assertEqual(continuous.status, "complete")
        for actual, expected in zip(
            continuous.apparent_curve,
            continuous.prediction_grid,
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected, places=12)
        self.assertEqual(probability.scale, "probability")
        self.assertEqual(probability.status, "complete")
        for actual, expected in zip(
            probability.apparent_curve,
            probability.prediction_grid,
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected, places=10)
        self.assertEqual(len(probability.resamples.successes), 2)

    def test_partial_refit_failures_and_strict_policy_are_explicit(self) -> None:
        response = tuple(1.0 + value for value in self.x)
        fitted = fit_ols(response, self.features, feature_names=("x",))
        plan = ResamplePlan.exact(
            20,
            (
                ((0, 0, 0, 0), tuple(range(4, 20))),
                (tuple(range(10)), tuple(range(10, 20))),
            ),
        )

        recorded = validate_model(
            fitted,
            response,
            self.features,
            plan,
            failure_policy="record",
        )
        self.assertEqual(recorded.status, "partial")
        self.assertEqual(recorded.failure_rate, 0.5)
        self.assertEqual(len(recorded.resamples.failures), 1)
        self.assertEqual(
            recorded.resamples.failures[0].exception_type,
            "RankDeficiencyError",
        )
        with self.assertRaisesRegex(NumericalError, "exact-1"):
            validate_model(fitted, response, self.features, plan)

    def test_alignment_grid_and_unsupported_models_fail_closed(self) -> None:
        fitted = fit_ols(
            self.ols_response,
            self.features,
            feature_names=("x",),
        )
        with self.assertRaisesRegex(InputValidationError, "row identity"):
            validate_model(
                fitted,
                self.ols_response,
                self.features,
                self.balanced_plan,
                row_ids=tuple(reversed(self.balanced_plan.row_ids)),
            )
        with self.assertRaisesRegex(InputValidationError, "strictly increasing"):
            calibrate_model(
                fitted,
                self.ols_response,
                self.features,
                self.balanced_plan,
                prediction_grid=(1.0, 1.0),
            )
        ordinal = fit_ordinal_lrm(
            (0, 1, 2, 0, 1, 2),
            ((0.0,), (0.2,), (0.4,), (0.6,), (0.8,), (1.0,)),
        )
        with self.assertRaisesRegex(UnsupportedFeatureError, "OLS and binary"):
            validate_model(
                ordinal,
                (0, 1, 2, 0, 1, 2),
                ((0.0,), (0.2,), (0.4,), (0.6,), (0.8,), (1.0,)),
                ResamplePlan.k_fold(6, folds=2),
            )


if __name__ == "__main__":
    unittest.main()
