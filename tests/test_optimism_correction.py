from __future__ import annotations

import unittest

from holocron.exceptions import InputValidationError, NumericalError
from holocron.models import fit_lrm, fit_ols
from holocron.validation import (
    BinaryValidationIndices,
    ModelValidationResult,
    ModelValidationSplit,
    OlsValidationIndices,
    OptimismCorrectedCalibrationResult,
    OptimismCorrectedValidationResult,
    ResampleExecution,
    ResampleFailure,
    ResamplePlan,
    ResampleSuccess,
    calibrate_model,
    optimism_correct_calibration,
    optimism_correct_validation,
    validate_model,
)


class OptimismCorrectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x = tuple(float(index) for index in range(20))
        self.features = tuple((value,) for value in self.x)
        self.ols_response = tuple(
            1.0 + 0.5 * value + 0.2 * ((index % 3) - 1)
            for index, value in enumerate(self.x)
        )
        self.plan = ResamplePlan.k_fold(20, folds=4, repeats=2, seed=19)

    def test_validation_correction_uses_mean_paired_optimism(self) -> None:
        fitted = fit_ols(self.ols_response, self.features, feature_names=("x",))
        validation = validate_model(
            fitted,
            self.ols_response,
            self.features,
            self.plan,
        )

        corrected = optimism_correct_validation(validation)

        self.assertIsInstance(corrected, OptimismCorrectedValidationResult)
        self.assertEqual(corrected.status, "complete")
        self.assertEqual(corrected.successful_resamples, 8)
        self.assertEqual(
            tuple(metric.name for metric in corrected.metrics),
            (
                "r_squared",
                "mean_squared_error",
                "calibration_intercept",
                "calibration_slope",
            ),
        )
        mse = corrected.metric("mean_squared_error")
        assert isinstance(validation.apparent, OlsValidationIndices)
        split_values = tuple(
            success.value for success in validation.resamples.successes
        )
        self.assertTrue(
            all(
                isinstance(value.training, OlsValidationIndices)
                and isinstance(value.assessment, OlsValidationIndices)
                for value in split_values
            )
        )
        training = tuple(
            value.training.mean_squared_error
            for value in split_values
            if isinstance(value.training, OlsValidationIndices)
        )
        assessment = tuple(
            value.assessment.mean_squared_error
            for value in split_values
            if isinstance(value.assessment, OlsValidationIndices)
        )
        expected_optimism = sum(training) / 8 - sum(assessment) / 8
        self.assertAlmostEqual(mse.optimism or 0.0, expected_optimism)
        self.assertAlmostEqual(
            mse.corrected or 0.0,
            validation.apparent.mean_squared_error - expected_optimism,
        )
        self.assertEqual(mse.contributing_resamples, 8)

    def test_binary_validation_correction_preserves_family_metrics(self) -> None:
        response = tuple(float(index % 4 in (0, 1)) for index in range(20))
        fitted = fit_lrm(response, self.features, feature_names=("x",))
        binary_plan = ResamplePlan.exact(
            20,
            (
                (tuple(range(0, 20, 2)), tuple(range(1, 20, 2))),
                (tuple(range(1, 20, 2)), tuple(range(0, 20, 2))),
            ),
        )
        validation = validate_model(fitted, response, self.features, binary_plan)
        calibration = calibrate_model(
            fitted,
            response,
            self.features,
            binary_plan,
            prediction_grid=(0.25, 0.5, 0.75),
        )

        corrected = optimism_correct_validation(validation)
        corrected_calibration = optimism_correct_calibration(calibration)

        self.assertEqual(corrected.model_family, "binary-logistic")
        self.assertEqual(
            tuple(metric.name for metric in corrected.metrics),
            (
                "dxy",
                "brier_score",
                "calibration_intercept",
                "calibration_slope",
            ),
        )
        self.assertIsInstance(validation.apparent, BinaryValidationIndices)
        self.assertEqual(corrected.metric("brier_score").contributing_resamples, 2)
        self.assertEqual(corrected_calibration.scale, "probability")
        self.assertEqual(corrected_calibration.contributing_resamples, 2)
        self.assertTrue(
            all(
                0.0 <= value <= 1.0
                for value in corrected_calibration.mean_assessment_curve
            )
        )
        with self.assertRaisesRegex(InputValidationError, "unavailable"):
            corrected.metric("mean_squared_error")

    def test_undefined_metrics_use_explicit_pairwise_counts(self) -> None:
        fingerprint = "0" * 64
        execution = ResampleExecution(
            plan_fingerprint=fingerprint,
            planned_count=2,
            successes=(
                ResampleSuccess(
                    "exact-1",
                    ModelValidationSplit(
                        training=OlsValidationIndices(0.8, 1.0, 0.0, 1.0),
                        assessment=OlsValidationIndices(0.5, 2.0, 0.2, 0.8),
                    ),
                ),
                ResampleSuccess(
                    "exact-2",
                    ModelValidationSplit(
                        training=OlsValidationIndices(None, 1.5, 0.1, 0.9),
                        assessment=OlsValidationIndices(0.4, 2.5, 0.3, 0.7),
                    ),
                ),
            ),
            failures=(),
        )
        source = ModelValidationResult(
            model_family="ols",
            apparent=OlsValidationIndices(0.7, 1.2, 0.0, 1.0),
            resamples=execution,
        )

        corrected = optimism_correct_validation(source)

        r_squared = corrected.metric("r_squared")
        self.assertEqual(r_squared.contributing_resamples, 1)
        self.assertAlmostEqual(r_squared.optimism or 0.0, 0.3)
        self.assertAlmostEqual(r_squared.corrected or 0.0, 0.4)
        mse = corrected.metric("mean_squared_error")
        self.assertEqual(mse.contributing_resamples, 2)
        self.assertAlmostEqual(mse.mean_training or 0.0, 1.25)
        self.assertAlmostEqual(mse.mean_assessment or 0.0, 2.25)
        self.assertAlmostEqual(mse.corrected or 0.0, 2.2)

    def test_calibration_correction_is_pointwise_on_declared_grid(self) -> None:
        fitted = fit_ols(self.ols_response, self.features, feature_names=("x",))
        calibration = calibrate_model(
            fitted,
            self.ols_response,
            self.features,
            self.plan,
            prediction_grid=(2.0, 5.0, 8.0),
        )

        corrected = optimism_correct_calibration(calibration)

        self.assertIsInstance(corrected, OptimismCorrectedCalibrationResult)
        self.assertEqual(corrected.contributing_resamples, 8)
        self.assertEqual(corrected.prediction_grid, (2.0, 5.0, 8.0))
        for index in range(3):
            expected_training = (
                sum(
                    success.value.training.predict(
                        calibration.prediction_grid,
                        scale=calibration.scale,
                    )[index]
                    for success in calibration.resamples.successes
                )
                / 8
            )
            expected_assessment = (
                sum(
                    success.value.assessment.predict(
                        calibration.prediction_grid,
                        scale=calibration.scale,
                    )[index]
                    for success in calibration.resamples.successes
                )
                / 8
            )
            self.assertAlmostEqual(
                corrected.mean_training_curve[index], expected_training
            )
            self.assertAlmostEqual(
                corrected.mean_assessment_curve[index], expected_assessment
            )
            self.assertAlmostEqual(
                corrected.corrected_curve[index],
                calibration.apparent_curve[index]
                - (expected_training - expected_assessment),
            )

    def test_partial_and_failed_executions_fail_closed_by_default(self) -> None:
        response = tuple(1.0 + value for value in self.x)
        fitted = fit_ols(response, self.features, feature_names=("x",))
        plan = ResamplePlan.exact(
            20,
            (
                ((0, 0, 0, 0), tuple(range(4, 20))),
                (tuple(range(10)), tuple(range(10, 20))),
            ),
        )
        validation = validate_model(
            fitted,
            response,
            self.features,
            plan,
            failure_policy="record",
        )

        with self.assertRaisesRegex(InputValidationError, "allow_partial"):
            optimism_correct_validation(validation)
        partial = optimism_correct_validation(validation, allow_partial=True)
        self.assertEqual(partial.status, "partial")
        self.assertEqual(partial.successful_resamples, 1)
        self.assertEqual(partial.failure_rate, 0.5)

        failed_execution = ResampleExecution[ModelValidationSplit](
            plan_fingerprint="1" * 64,
            planned_count=1,
            successes=(),
            failures=(ResampleFailure("exact-1", "NumericalError", "failed"),),
        )
        failed = ModelValidationResult(
            "ols",
            OlsValidationIndices(0.7, 1.0, 0.0, 1.0),
            failed_execution,
        )
        with self.assertRaisesRegex(NumericalError, "successful resample"):
            optimism_correct_validation(failed, allow_partial=True)


if __name__ == "__main__":
    unittest.main()
