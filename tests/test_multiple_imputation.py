from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from holocron.exceptions import InputValidationError
from holocron.models import fit_lrm, fit_ols
from holocron.reporting import TableSpec, render_latex
from holocron.validation import (
    LikelihoodRatioAnova,
    LikelihoodRatioTest,
    MultipleImputationAnovaResult,
    OptimismCorrectedCalibrationResult,
    OptimismCorrectedValidationResult,
    PooledCalibrationResult,
    PooledModelResult,
    PooledValidationResult,
    ResamplePlan,
    calibrate_model,
    imputation_information_table,
    optimism_correct_calibration,
    optimism_correct_validation,
    pool_imputation_calibration,
    pool_imputation_likelihood_ratio,
    pool_imputation_models,
    pool_imputation_validation,
    process_multiple_imputation,
    validate_model,
)


class MultipleImputationTests(unittest.TestCase):
    features = tuple((float(index), float((index % 3) - 1)) for index in range(18))
    response_one = tuple(
        1.0 + 0.4 * first - 0.2 * second + 0.1 * ((index % 4) - 1.5)
        for index, (first, second) in enumerate(features)
    )
    response_two = tuple(
        value + 0.08 * ((index % 5) - 2) for index, value in enumerate(response_one)
    )

    def assert_schema_valid(self, document: object, filename: str) -> None:
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "schemas" / filename).read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(  # pyright: ignore[reportUnknownMemberType]
            document
        )

    def test_rubin_pooling_matches_manual_components_and_round_trips(self) -> None:
        fits = (
            fit_ols(self.response_one, self.features, feature_names=("x", "z")),
            fit_ols(self.response_two, self.features, feature_names=("x", "z")),
        )
        pooled = pool_imputation_models(fits)

        for index in range(len(pooled.coefficients)):
            expected_mean = sum(fit.coefficients[index] for fit in fits) / 2.0
            expected_within = sum(fit.covariance[index][index] for fit in fits) / 2.0
            expected_between = sum(
                (fit.coefficients[index] - expected_mean) ** 2 for fit in fits
            )
            expected_total = expected_within + 1.5 * expected_between
            self.assertAlmostEqual(pooled.coefficients[index], expected_mean)
            self.assertAlmostEqual(
                pooled.within_covariance[index][index], expected_within
            )
            self.assertAlmostEqual(
                pooled.between_covariance[index][index], expected_between
            )
            self.assertAlmostEqual(
                pooled.total_covariance[index][index], expected_total
            )
            self.assertAlmostEqual(
                pooled.standard_errors[index], math.sqrt(expected_total)
            )
        self.assertEqual(pooled.n_imputations, 2)
        self.assertTrue(all(value > 0.0 for value in pooled.degrees_of_freedom))
        self.assertEqual(PooledModelResult.from_json(pooled.to_json()), pooled)
        self.assert_schema_valid(pooled.to_dict(), "pooled-model-result.schema.json")

    def test_binary_pooling_predicts_probabilities_and_rejects_mismatch(self) -> None:
        outcome_one = tuple(int(index % 4 in {2, 3}) for index in range(18))
        outcome_two = tuple(int(index % 5 in {2, 3, 4}) for index in range(18))
        fit_one = fit_lrm(outcome_one, self.features, feature_names=("x", "z"))
        fit_two = fit_lrm(outcome_two, self.features, feature_names=("x", "z"))
        pooled = process_multiple_imputation((fit_one, fit_two))

        self.assertIsInstance(pooled, PooledModelResult)
        assert isinstance(pooled, PooledModelResult)
        self.assertEqual(pooled.model_family, "lrm-binary")
        probabilities = pooled.predict_response(((2.0, 0.0), (10.0, 1.0)))
        self.assertTrue(all(0.0 < value < 1.0 for value in probabilities))
        mismatched = fit_lrm(
            outcome_two, self.features, feature_names=("different", "z")
        )
        with self.assertRaises(InputValidationError):
            pool_imputation_models((fit_one, mismatched))

    def _corrected_results(
        self,
    ) -> tuple[
        OptimismCorrectedValidationResult,
        OptimismCorrectedValidationResult,
        OptimismCorrectedCalibrationResult,
        OptimismCorrectedCalibrationResult,
    ]:
        plan = ResamplePlan.bootstrap(18, replicates=5, seed=5)
        models = (
            fit_ols(self.response_one, self.features),
            fit_ols(self.response_two, self.features),
        )
        validation = tuple(
            optimism_correct_validation(
                validate_model(model, response, self.features, plan)
            )
            for model, response in zip(
                models, (self.response_one, self.response_two), strict=True
            )
        )
        calibration = tuple(
            optimism_correct_calibration(
                calibrate_model(
                    model,
                    response,
                    self.features,
                    plan,
                    grid_points=7 + 2 * index,
                )
            )
            for index, (model, response) in enumerate(
                zip(models, (self.response_one, self.response_two), strict=True)
            )
        )
        return validation[0], validation[1], calibration[0], calibration[1]

    def test_validation_pooling_averages_metrics_and_sums_contributors(self) -> None:
        validation_one, validation_two, _, _ = self._corrected_results()
        pooled = pool_imputation_validation((validation_one, validation_two))

        self.assertEqual(pooled.n_imputations, 2)
        self.assertEqual(pooled.source_statuses, ("complete", "complete"))
        metric = pooled.metric("mean_squared_error")
        source_metrics = (
            validation_one.metric("mean_squared_error"),
            validation_two.metric("mean_squared_error"),
        )
        self.assertIsNotNone(metric.corrected)
        assert metric.corrected is not None
        self.assertAlmostEqual(
            metric.corrected,
            sum(
                value.corrected
                for value in source_metrics
                if value.corrected is not None
            )
            / 2.0,
        )
        self.assertEqual(
            metric.contributing_resamples,
            sum(value.contributing_resamples for value in source_metrics),
        )
        self.assertEqual(PooledValidationResult.from_json(pooled.to_json()), pooled)
        self.assert_schema_valid(
            pooled.to_dict(), "pooled-validation-result.schema.json"
        )

    def test_calibration_pooling_interpolates_common_grid(self) -> None:
        _, _, calibration_one, calibration_two = self._corrected_results()
        pooled = pool_imputation_calibration(
            (calibration_one, calibration_two),
            grid_points=11,
        )

        self.assertEqual(len(pooled.prediction_grid), 11)
        self.assertEqual(pooled.contributing_resamples, 10)
        for index in range(11):
            self.assertAlmostEqual(
                pooled.optimism_curve[index],
                pooled.mean_training_curve[index] - pooled.mean_assessment_curve[index],
            )
            self.assertAlmostEqual(
                pooled.corrected_curve[index],
                pooled.apparent_curve[index] - pooled.optimism_curve[index],
            )
        self.assertEqual(PooledCalibrationResult.from_json(pooled.to_json()), pooled)
        self.assert_schema_valid(
            pooled.to_dict(), "pooled-calibration-result.schema.json"
        )

    def test_chan_meng_adjustment_and_information_table(self) -> None:
        imputation_one = LikelihoodRatioAnova(
            (LikelihoodRatioTest("x", ("x",), 8.0, 1),)
        )
        imputation_two = LikelihoodRatioAnova(
            (LikelihoodRatioTest("x", ("x",), 10.0, 1),)
        )
        stacked = LikelihoodRatioAnova((LikelihoodRatioTest("x", ("x",), 15.0, 1),))
        result = pool_imputation_likelihood_ratio(
            (imputation_one, imputation_two), stacked=stacked
        )
        test = result.tests[0]

        self.assertAlmostEqual(test.mean_imputation_chi_square, 9.0)
        self.assertAlmostEqual(test.stacked_chi_square, 7.5)
        self.assertAlmostEqual(test.missing_information_fraction, 9.0 / 11.0)
        self.assertAlmostEqual(test.chi_square_discount, 2.0 / 11.0)
        self.assertAlmostEqual(test.adjusted_chi_square, 15.0 / 11.0)
        self.assertEqual(
            MultipleImputationAnovaResult.from_json(result.to_json()), result
        )
        table = imputation_information_table(result)
        self.assertIsInstance(table, TableSpec)
        self.assertIn("Imputation penalties", render_latex(table))
        self.assert_schema_valid(result.to_dict(), "pooled-anova-result.schema.json")

    def test_dispatch_and_strict_failure_boundaries(self) -> None:
        fit = fit_ols(self.response_one, self.features)
        with self.assertRaises(InputValidationError):
            process_multiple_imputation((fit,))
        with self.assertRaises(InputValidationError):
            process_multiple_imputation((object(), object()))  # pyright: ignore[reportCallIssue, reportArgumentType]
        result = pool_imputation_models(
            (fit, fit_ols(self.response_two, self.features))
        )
        document = result.to_dict()
        document["unexpected"] = True
        with self.assertRaises(InputValidationError):
            PooledModelResult.from_dict(document)
        with self.assertRaises(InputValidationError):
            PooledModelResult.from_json(result.to_json()[:-1] + ',"n_imputations":3}')


if __name__ == "__main__":
    unittest.main()
