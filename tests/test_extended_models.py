from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from holocron.exceptions import (
    ConvergenceError,
    InputValidationError,
    UnsupportedFeatureError,
)
from holocron.models import (
    BuckleyJamesResult,
    GeneralizedLeastSquaresResult,
    ProportionalHazardsParametricResult,
    QuantileRegressionResult,
    fit_buckley_james,
    fit_gls,
    fit_ols,
    fit_psm,
    fit_quantile_regression,
    to_proportional_hazards,
)


class ExtendedModelTests(unittest.TestCase):
    features = tuple((float(value),) for value in range(8))
    response = (1.2, 2.8, 5.1, 6.7, 9.3, 10.9, 13.2, 15.1)

    def assert_schema_valid(self, document: object, filename: str) -> None:
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "schemas" / filename).read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(  # pyright: ignore[reportUnknownMemberType]
            document
        )

    def test_gls_identity_matches_ols_and_round_trips(self) -> None:
        result = fit_gls(
            self.response,
            self.features,
            method="reml",
            feature_names=("x",),
        )
        ols = fit_ols(self.response, self.features, feature_names=("x",))

        self.assertEqual(result.coefficient_names, ("Intercept", "x"))
        for actual, expected in zip(result.coefficients, ols.coefficients, strict=True):
            self.assertAlmostEqual(actual, expected, places=12)
        self.assertAlmostEqual(result.residual_scale, ols.residual_scale, places=12)
        self.assertEqual(
            GeneralizedLeastSquaresResult.from_json(result.to_json()), result
        )
        self.assertAlmostEqual(
            result.predict(((8.0,),))[0], 17.107142857142854, places=12
        )
        self.assert_schema_valid(result.to_dict(), "gls-result.schema.json")

    def test_gls_uses_supplied_covariance_and_rejects_invalid_covariance(self) -> None:
        features = ((-2.0,), (-1.0,), (0.0,), (1.0,), (2.0,), (3.0,))
        response = (-2.6, -0.7, 1.2, 2.8, 5.3, 6.5)
        covariance = tuple(
            tuple(0.35 ** abs(row - column) for column in range(6)) for row in range(6)
        )
        result = fit_gls(
            response,
            features,
            observation_covariance=covariance,
            method="ml",
        )

        self.assertAlmostEqual(result.coefficients[0], 1.1407077118375117)
        self.assertAlmostEqual(result.coefficients[1], 1.8446715328467158)
        self.assertAlmostEqual(result.residual_scale, 0.29226973014373614)
        with self.assertRaises(InputValidationError):
            fit_gls(response, features, observation_covariance=((1.0,),))
        with self.assertRaises(InputValidationError):
            fit_gls(
                response,
                features,
                observation_covariance=tuple(
                    tuple(1.0 for _ in range(6)) for _ in range(6)
                ),
            )

    def test_single_quantile_fit_is_deterministic_and_serializable(self) -> None:
        result = fit_quantile_regression(
            self.response,
            self.features,
            quantile=0.5,
            feature_names=("x",),
        )
        repeated = fit_quantile_regression(
            self.response,
            self.features,
            quantile=0.5,
            feature_names=("x",),
        )

        self.assertEqual(result, repeated)
        self.assertAlmostEqual(result.coefficients[0], 1.1, places=5)
        self.assertAlmostEqual(result.coefficients[1], 2.0, places=5)
        self.assertLess(result.objective, 0.651)
        self.assertEqual(QuantileRegressionResult.from_json(result.to_json()), result)
        self.assertAlmostEqual(result.predict(((8.0,),))[0], 17.1, places=5)
        self.assert_schema_valid(
            result.to_dict(), "quantile-regression-result.schema.json"
        )

    def test_quantile_fit_honors_weights_and_fails_closed(self) -> None:
        unweighted = fit_quantile_regression(
            (0.0, 1.0, 2.0, 100.0),
            ((1.0,), (1.0,), (1.0,), (1.0,)),
            include_intercept=False,
        )
        weighted = fit_quantile_regression(
            (0.0, 1.0, 2.0, 100.0),
            ((1.0,), (1.0,), (1.0,), (1.0,)),
            weights=(1.0, 1.0, 1.0, 20.0),
            include_intercept=False,
        )
        self.assertGreater(weighted.coefficients[0], unweighted.coefficients[0])
        with self.assertRaises(InputValidationError):
            fit_quantile_regression(self.response, self.features, quantile=1.0)
        with self.assertRaises(ConvergenceError):
            fit_quantile_regression(
                self.response,
                self.features,
                max_iterations=1,
                tolerance=1e-12,
            )

    def test_buckley_james_log_fit_and_round_trip(self) -> None:
        times = (1.1, 1.7, 2.4, 3.0, 4.8, 5.5, 7.2, 8.0, 9.5, 11.0)
        events = (1, 1, 1, 1, 1, 0, 1, 0, 1, 0)
        features = tuple((float(value),) for value in range(-3, 7))
        result = fit_buckley_james(times, events, features, feature_names=("x",))

        self.assertEqual(result.event_count, 7)
        self.assertAlmostEqual(result.coefficients[0], 1.1047973559629412)
        self.assertAlmostEqual(result.coefficients[1], 0.27929926165475427)
        self.assertTrue(all(value > 0.0 for value in result.predict(((-2.0,), (2.0,)))))
        self.assertEqual(BuckleyJamesResult.from_json(result.to_json()), result)
        self.assert_schema_valid(result.to_dict(), "buckley-james-result.schema.json")
        for index, event in enumerate(events):
            if event:
                self.assertAlmostEqual(
                    result.imputed_response[index], math.log(times[index])
                )

    def test_buckley_james_rejects_unsupported_or_unidentified_fits(self) -> None:
        with self.assertRaises(UnsupportedFeatureError):
            fit_buckley_james(
                (1.0, 2.0, 3.0, 4.0),
                (1, 1, 1, 0),
                ((0.0,), (1.0,), (2.0,), (3.0,)),
                link="sqrt",  # type: ignore[arg-type]
            )
        with self.assertRaises(InputValidationError):
            fit_buckley_james(
                (1.0, 2.0, 3.0, 4.0),
                (1, 1, 1, 1),
                ((0.0,), (1.0,), (2.0,), (3.0,)),
            )

    def test_parametric_ph_conversion_preserves_survival_predictions(self) -> None:
        times = (12, 9, 15, 7, 11, 6, 8, 4, 5, 10, 13, 7, 3, 6, 14, 9, 5, 2)
        events = (1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1)
        x = (
            -2,
            -1.5,
            -1,
            -0.5,
            0,
            0.5,
            1,
            1.5,
            2,
            -1.8,
            -0.8,
            0.2,
            1.2,
            2.2,
            -2.2,
            -1.2,
            0.8,
            1.8,
        )
        features = tuple((float(value),) for value in x)
        fitted = fit_psm(
            times,
            events,
            features,
            distribution="weibull",
            feature_names=("x",),
        )
        converted = to_proportional_hazards(fitted)
        prediction_features = ((-1.0,), (1.0,))
        prediction_times = (2.0, 5.0, 10.0)

        self.assertAlmostEqual(converted.shape, 1.0 / fitted.scales[0])
        for actual_row, expected_row in zip(
            converted.predict_survival(prediction_features, prediction_times),
            fitted.predict_survival(prediction_features, prediction_times),
            strict=True,
        ):
            for actual, expected in zip(actual_row, expected_row, strict=True):
                self.assertAlmostEqual(actual, expected, places=14)
        self.assertEqual(converted.source_fingerprint, fitted.fingerprint)
        self.assertEqual(
            ProportionalHazardsParametricResult.from_json(converted.to_json()),
            converted,
        )
        self.assert_schema_valid(
            converted.to_dict(), "proportional-hazards-result.schema.json"
        )

        stratified = fit_psm(
            times,
            events,
            features,
            distribution="weibull",
            strata=("a",) * 9 + ("b",) * 9,
        )
        with self.assertRaises(UnsupportedFeatureError):
            to_proportional_hazards(stratified)

    def test_result_json_rejects_unknown_duplicate_and_boolean_numeric_fields(
        self,
    ) -> None:
        result = fit_gls(self.response, self.features)
        document = result.to_dict()
        document["unexpected"] = 1
        with self.assertRaises(InputValidationError):
            GeneralizedLeastSquaresResult.from_dict(document)
        with self.assertRaises(InputValidationError):
            GeneralizedLeastSquaresResult.from_json(
                result.to_json()[:-1] + ',"method":"ml"}'
            )
        document = json.loads(result.to_json())
        document["residual_scale"] = True
        with self.assertRaises(InputValidationError):
            GeneralizedLeastSquaresResult.from_dict(document)


if __name__ == "__main__":
    unittest.main()
