from __future__ import annotations

import math
import unittest

import numpy as np

from holocron.exceptions import InputValidationError, UnsupportedFeatureError
from holocron.models import (
    BackwardSelectionResult,
    InfluenceResult,
    PenaltyTraceResult,
    backward_select,
    fit_glm,
    fit_lrm,
    fit_ols,
    influence_diagnostics,
    robust_covariance,
    robustness_diagnostics,
    trace_penalty,
    variance_inflation_factors,
)


class DiagnosticsSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x = tuple(float(index - 10) for index in range(20))
        self.z = tuple(float((index * 7) % 11 - 5) for index in range(20))
        self.features = tuple(zip(self.x, self.z, strict=True))
        self.response = tuple(
            2.0 + 1.5 * x + 0.1 * ((index % 5) - 2) for index, x in enumerate(self.x)
        )
        self.ols = fit_ols(
            self.response,
            self.features,
            feature_names=("x", "z"),
        )
        self.binary_response = tuple(
            float(value) for value in (0, 0, 0, 1, 0, 1, 0, 1, 1, 1) * 2
        )
        self.binary_features = tuple(
            (float(index % 10 - 5), float((index * 3) % 7 - 3)) for index in range(20)
        )
        self.binary = fit_lrm(
            self.binary_response,
            self.binary_features,
            feature_names=("x", "z"),
        )

    def test_ols_influence_matches_exact_case_deletion_identity(self) -> None:
        result = influence_diagnostics(self.ols, self.response, self.features)

        self.assertIsInstance(result, InfluenceResult)
        self.assertEqual(result.model_family, "ols")
        self.assertEqual(len(result.observations), len(self.response))
        self.assertAlmostEqual(
            sum(value.leverage for value in result.observations),
            self.ols.rank,
        )
        deleted_index = 4
        deleted = fit_ols(
            tuple(
                value
                for index, value in enumerate(self.response)
                if index != deleted_index
            ),
            tuple(
                row for index, row in enumerate(self.features) if index != deleted_index
            ),
            feature_names=("x", "z"),
        )
        expected_change = tuple(
            full - reduced
            for full, reduced in zip(
                self.ols.coefficients,
                deleted.coefficients,
                strict=True,
            )
        )
        np.testing.assert_allclose(
            result.observations[deleted_index].coefficient_change,
            expected_change,
            atol=1e-12,
        )
        self.assertTrue(
            all(value.cooks_distance >= 0.0 for value in result.observations)
        )

    def test_binary_influence_is_finite_and_hat_trace_matches_rank(self) -> None:
        result = influence_diagnostics(
            self.binary,
            self.binary_response,
            self.binary_features,
        )

        self.assertEqual(result.model_family, "binary-logistic")
        self.assertAlmostEqual(
            sum(value.leverage for value in result.observations),
            self.binary.rank,
            places=9,
        )
        self.assertTrue(
            all(
                math.isfinite(value.standardized_residual)
                and all(math.isfinite(item) for item in value.dfbetas)
                for value in result.observations
            )
        )

    def test_vif_matches_predictor_correlation_definition(self) -> None:
        values = variance_inflation_factors(self.ols)
        correlation = float(np.corrcoef(self.x, self.z)[0, 1])
        expected = 1.0 / (1.0 - correlation**2)

        self.assertEqual(tuple(value.coefficient_name for value in values), ("x", "z"))
        self.assertAlmostEqual(values[0].value, expected)
        self.assertAlmostEqual(values[1].value, expected)

    def test_robustness_wraps_the_accepted_sandwich_covariance(self) -> None:
        clusters = tuple(index // 2 for index in range(len(self.response)))
        expected = robust_covariance(
            self.ols,
            self.response,
            self.features,
            clusters=clusters,
        )
        result = robustness_diagnostics(
            self.ols,
            self.response,
            self.features,
            clusters=clusters,
        )

        self.assertEqual(result.covariance, expected)
        self.assertEqual(len(result.coefficients), len(self.ols.coefficients))
        for index, value in enumerate(result.coefficients):
            self.assertAlmostEqual(
                value.robust_standard_error**2,
                expected.matrix[index][index],
            )
            self.assertGreaterEqual(value.robust_to_model_ratio, 0.0)

    def test_penalty_trace_selects_declared_criterion(self) -> None:
        result = trace_penalty(
            self.ols,
            self.response,
            self.features,
            (0.0, 0.1, 1.0, 10.0),
            criterion="bic",
        )

        self.assertIsInstance(result, PenaltyTraceResult)
        self.assertEqual(result.model_family, "ols")
        self.assertEqual(result.points[0].coefficients, self.ols.coefficients)
        self.assertEqual(
            result.selected_point.bic,
            min(point.bic for point in result.points),
        )
        self.assertEqual(result.points[0].effective_degrees_of_freedom, self.ols.rank)
        self.assertTrue(
            all(point.effective_degrees_of_freedom > 0.0 for point in result.points)
        )
        self.assertLess(
            abs(result.points[-1].coefficients[1]),
            abs(result.points[0].coefficients[1]),
        )

        binary = trace_penalty(
            self.binary,
            self.binary_response,
            self.binary_features,
            (0.0, 0.5, 2.0),
        )
        self.assertEqual(binary.model_family, "lrm-binary")
        self.assertEqual(len(binary.points), 3)

    def test_backward_selection_fully_refits_declared_groups(self) -> None:
        result = backward_select(
            self.ols,
            self.response,
            self.features,
            {"signal": ("x",), "noise": ("z",)},
        )

        self.assertIsInstance(result, BackwardSelectionResult)
        self.assertEqual(result.selected_terms, ("signal",))
        self.assertEqual(len(result.steps), 1)
        self.assertEqual(result.steps[0].removed_term, "noise")
        self.assertEqual(result.final_model.coefficient_names, ("Intercept", "x"))
        self.assertIsNone(result.final_model.design_fingerprint)

        protected = backward_select(
            self.ols,
            self.response,
            self.features,
            {"signal": ("x",), "noise": ("z",)},
            protected_terms=("noise",),
        )
        self.assertEqual(protected.selected_terms, ("signal", "noise"))
        self.assertEqual(protected.steps, ())

    def test_diagnostic_and_selection_inputs_fail_closed(self) -> None:
        glm = fit_glm(
            self.binary_response,
            self.binary_features,
            family="binomial",
            feature_names=("x", "z"),
        )
        with self.assertRaisesRegex(UnsupportedFeatureError, "not Glm"):
            trace_penalty(
                glm,
                self.binary_response,
                self.binary_features,
                (0.0, 1.0),
            )
        with self.assertRaisesRegex(InputValidationError, "strictly increasing"):
            trace_penalty(
                self.ols,
                self.response,
                self.features,
                (0.0, 1.0, 0.5),
            )
        with self.assertRaisesRegex(InputValidationError, "do not apply to OLS"):
            trace_penalty(
                self.ols,
                self.response,
                self.features,
                (0.0, 1.0),
                max_iterations=10,
            )
        with self.assertRaisesRegex(InputValidationError, "does not apply to binary"):
            trace_penalty(
                self.binary,
                self.binary_response,
                self.binary_features,
                (0.0, 1.0),
                ols_variance="sandwich",
            )
        with self.assertRaisesRegex(InputValidationError, "partition"):
            backward_select(
                self.ols,
                self.response,
                self.features,
                {"incomplete": ("x",)},
            )
        wrong_response = (*self.response[:-1], self.response[-1] + 1.0)
        with self.assertRaisesRegex(InputValidationError, "fitted OLS response"):
            influence_diagnostics(self.ols, wrong_response, self.features)


if __name__ == "__main__":
    unittest.main()
