from __future__ import annotations

import unittest

import numpy as np

from holocron.design import DesignSpec
from holocron.exceptions import InputValidationError, NumericalError
from holocron.models import (
    bootstrap_covariance,
    fit_glm,
    fit_lrm,
    fit_ols,
    fit_penalized_lrm,
    fit_penalized_ols,
    robust_covariance,
)
from reference.contracts import (
    CASES,
    EXPECTED,
    compare_json,
    output_payload,
    validate_case_pair,
)
from reference.python_parity import build_python_output


class RegularizationCovarianceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x = tuple(float(value) for value in range(-3, 9))
        self.y = (1.1, 1.8, 2.4, 3.2, 3.7, 5.1, 5.5, 6.8, 7.4, 8.1, 9.3, 9.9)
        self.ols_specification = DesignSpec.from_formula("y ~ x")
        self.ols_design = self.ols_specification.transform({"x": self.x})

        self.binary_x = tuple(float(value) for value in (-3, -2, -1, 0, 1, 2, 3) * 2)
        self.binary_y = (0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1)
        self.binary_specification = DesignSpec.from_formula("event ~ x")
        self.binary_design = self.binary_specification.transform({"x": self.binary_x})

    def test_penalized_ols_matches_closed_form_and_preserves_design(self) -> None:
        result = fit_penalized_ols(self.y, self.ols_design, penalty={"asis(x)": 2.0})
        matrix = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (np.ones(len(self.x)), self.x)
        )
        penalty = np.diag(  # pyright: ignore[reportUnknownMemberType]
            (0.0, 2.0)
        )
        expected = np.linalg.solve(matrix.T @ matrix + penalty, matrix.T @ self.y)

        np.testing.assert_allclose(result.coefficients, expected, atol=1e-14)
        self.assertEqual(result.penalty_weights, (2.0,))
        self.assertLess(
            result.coefficients[1], fit_ols(self.y, self.ols_design).coefficients[1]
        )
        self.assertGreater(result.effective_degrees_of_freedom, 1.0)
        self.assertEqual(result.predict_response(self.ols_design), result.fitted_values)

    def test_penalized_ols_supports_both_rms_variance_contracts(self) -> None:
        simple = fit_penalized_ols(
            self.y, self.ols_design, penalty=2.0, variance="simple"
        )
        sandwich = fit_penalized_ols(
            self.y, self.ols_design, penalty=2.0, variance="sandwich"
        )
        self.assertEqual(simple.coefficients, sandwich.coefficients)
        self.assertNotEqual(simple.covariance, sandwich.covariance)

    def test_penalized_lrm_shrinks_slope_and_handles_separation(self) -> None:
        unpenalized = fit_lrm(self.binary_y, self.binary_design)
        penalized = fit_penalized_lrm(self.binary_y, self.binary_design, penalty=1.5)
        self.assertLess(
            abs(penalized.coefficients[1]), abs(unpenalized.coefficients[1])
        )
        self.assertEqual(
            penalized.predict_response(self.binary_design), penalized.fitted_values
        )
        self.assertTrue(1.0 < penalized.effective_degrees_of_freedom < 2.0)

        separated_x = tuple(float(value) for value in range(-4, 4))
        separated_y = (0, 0, 0, 0, 1, 1, 1, 1)
        specification = DesignSpec.from_formula("event ~ x")
        separated = fit_penalized_lrm(
            separated_y,
            specification.transform({"x": separated_x}),
            penalty=1.0,
        )
        self.assertTrue(all(np.isfinite(separated.coefficients)))

    def test_cluster_robust_covariance_matches_sandwich_definition(self) -> None:
        fit = fit_ols(self.y, self.ols_design)
        clusters = tuple(index // 2 for index in range(len(self.y)))
        result = robust_covariance(fit, self.y, self.ols_design, clusters=clusters)
        design = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (np.ones(len(self.x)), self.x)
        )
        bread = np.linalg.inv(design.T @ design)
        scores = design * np.asarray(fit.residuals)[:, None]
        sums = np.asarray(
            [
                np.sum(scores[np.asarray(clusters) == group], axis=0)
                for group in range(6)
            ]
        )
        expected = bread @ sums.T @ sums @ bread

        self.assertEqual(result.cluster_count, 6)
        np.testing.assert_allclose(result.matrix, expected, atol=1e-15)

    def test_robust_covariance_supports_both_binary_estimators(self) -> None:
        clusters = tuple(index // 2 for index in range(len(self.binary_y)))
        for fit in (
            fit_glm(self.binary_y, self.binary_design, family="binomial"),
            fit_lrm(self.binary_y, self.binary_design),
        ):
            with self.subTest(estimator=fit.estimator):
                result = robust_covariance(
                    fit,
                    self.binary_y,
                    self.binary_design,
                    clusters=clusters,
                )
                self.assertEqual(result.coefficient_names, fit.coefficient_names)
                self.assertTrue(
                    all(
                        float(value) >= -1e-14
                        for value in np.linalg.eigvalsh(result.matrix)
                    )
                )

    def test_declared_bootstrap_schedule_matches_sample_covariance(self) -> None:
        fit = fit_ols(self.y, self.ols_design)
        schedule = (
            (0, 1, 1, 3, 4, 5, 5, 7, 8, 9, 10, 11),
            (0, 0, 2, 3, 4, 4, 6, 7, 8, 10, 10, 11),
            (1, 1, 2, 2, 4, 5, 6, 8, 8, 9, 11, 11),
            (0, 2, 2, 3, 5, 5, 6, 7, 9, 9, 10, 11),
        )
        result = bootstrap_covariance(
            fit,
            self.y,
            self.ols_design,
            replicates=len(schedule),
            seed=17,
            resample_indices=schedule,
        )
        repetitions: list[tuple[float, ...]] = []
        rows = self.ols_design.rows
        for indices in schedule:
            repetitions.append(
                fit_ols(
                    tuple(self.y[index] for index in indices),
                    tuple(rows[index] for index in indices),
                    feature_names=("asis(x)",),
                ).coefficients
            )
        np.testing.assert_allclose(
            result.matrix,
            np.cov(np.asarray(repetitions, dtype=np.float64), rowvar=False, ddof=1),
            atol=1e-15,
        )
        self.assertIsNotNone(result.coefficient_mean)
        np.testing.assert_allclose(
            result.coefficient_mean or (),
            np.mean(np.asarray(repetitions, dtype=np.float64), axis=0),
            atol=1e-15,
        )

    def test_seeded_bootstrap_is_reproducible(self) -> None:
        fit = fit_ols(self.y, self.ols_design)
        first = bootstrap_covariance(
            fit, self.y, self.ols_design, replicates=12, seed=90210
        )
        second = bootstrap_covariance(
            fit, self.y, self.ols_design, replicates=12, seed=90210
        )
        self.assertEqual(first, second)

    def test_invalid_regularization_inputs_fail_closed(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "positive"):
            fit_penalized_ols(self.y, self.ols_design, penalty=0.0)
        with self.assertRaisesRegex(InputValidationError, "unknown"):
            fit_penalized_ols(self.y, self.ols_design, penalty={"missing": 1.0})
        with self.assertRaisesRegex(InputValidationError, "names must be strings"):
            fit_penalized_ols(
                self.y,
                self.ols_design,
                penalty={1: 1.0},  # pyright: ignore[reportArgumentType]
            )
        fit = fit_ols(self.y, self.ols_design)
        wrong_design = self.ols_specification.transform(
            {"x": tuple(value + 1.0 for value in self.x)}
        )
        with self.assertRaisesRegex(InputValidationError, "fitted design"):
            robust_covariance(fit, self.y, wrong_design)
        wrong_response = (*self.y[:-1], self.y[-1] + 1.0)
        with self.assertRaisesRegex(InputValidationError, "fitted OLS response"):
            bootstrap_covariance(fit, wrong_response, self.ols_design, replicates=2)
        with self.assertRaisesRegex(InputValidationError, "two clusters"):
            robust_covariance(
                fit, self.y, self.ols_design, clusters=("only",) * len(self.y)
            )
        with self.assertRaisesRegex(InputValidationError, "replicates"):
            bootstrap_covariance(fit, self.y, self.ols_design, replicates=1)
        with self.assertRaisesRegex(InputValidationError, "replicates"):
            bootstrap_covariance(
                fit,
                self.y,
                self.ols_design,
                replicates=2.5,  # pyright: ignore[reportArgumentType]
            )
        with self.assertRaisesRegex(InputValidationError, "seed"):
            bootstrap_covariance(
                fit,
                self.y,
                self.ols_design,
                replicates=2,
                seed=1.5,  # pyright: ignore[reportArgumentType]
            )
        bad_schedule = ((0,) * len(self.y), (99,) * len(self.y))
        with self.assertRaisesRegex(InputValidationError, "outside"):
            bootstrap_covariance(
                fit,
                self.y,
                self.ols_design,
                replicates=2,
                resample_indices=bad_schedule,
            )
        fractional_schedule = ((0.5,) * len(self.y), (1,) * len(self.y))
        with self.assertRaisesRegex(InputValidationError, "outside"):
            bootstrap_covariance(  # type: ignore[arg-type]
                fit,
                self.y,
                self.ols_design,
                replicates=2,
                resample_indices=fractional_schedule,  # pyright: ignore[reportArgumentType]
            )
        separating_schedule = (
            (0,) * len(self.binary_y),
            (1,) * len(self.binary_y),
        )
        binary = fit_lrm(self.binary_y, self.binary_design)
        with self.assertRaisesRegex(NumericalError, "refit"):
            bootstrap_covariance(
                binary,
                self.binary_y,
                self.binary_design,
                replicates=2,
                resample_indices=separating_schedule,
            )

    def test_alternative_covariance_accepts_response_generators(self) -> None:
        fit = fit_lrm(self.binary_y, self.binary_design)
        result = robust_covariance(
            fit,
            (value for value in self.binary_y),
            self.binary_design,
        )
        self.assertEqual(result.cluster_count, len(self.binary_y))

    def test_all_regularization_oracle_fixtures_match(self) -> None:
        case_paths = sorted(CASES.glob("regularization-*.json"))
        self.assertEqual(len(case_paths), 3)
        for case_path in case_paths:
            with self.subTest(case_id=case_path.stem):
                case, expected, policy = validate_case_pair(
                    case_path, EXPECTED / case_path.name
                )
                report = compare_json(
                    build_python_output(case), output_payload(expected), policy
                )
                report.require_match()
                self.assertGreaterEqual(report.numeric_comparisons, 10)


if __name__ == "__main__":
    unittest.main()
