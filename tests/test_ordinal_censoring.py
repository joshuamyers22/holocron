from __future__ import annotations

import math
import unittest

import numpy as np

from holocron.design import DesignSpec
from holocron.exceptions import (
    ConvergenceError,
    InputValidationError,
    RankDeficiencyError,
)
from holocron.models import (
    CensoredResponse,
    OrdinalResult,
    fit_ordinal_lrm,
    fit_orm,
    fit_random_intercept_orm,
)
from reference.contracts import (
    CASES,
    EXPECTED,
    ORDINAL_RESULT_SCHEMA,
    compare_json,
    load_json,
    output_payload,
    require_object,
    validate_case_pair,
    validate_document,
)
from reference.python_parity import build_python_output


def clustered_data() -> tuple[
    tuple[int, ...],
    tuple[tuple[float], ...],
    tuple[int, ...],
    tuple[float, ...],
]:
    responses: list[int] = []
    features: list[tuple[float]] = []
    clusters: list[int] = []
    mix_re: list[float] = []
    effects = (-1.2, -0.8, -0.4, 0.0, 0.3, 0.7, 1.0, 1.3)
    noise = (-1.1, 0.2, 0.8, -0.5, 1.2, -0.9, 0.5, -0.1)
    for cluster, effect in enumerate(effects):
        for visit in range(8):
            value = (visit - 3.5) / 2.0
            latent = 0.55 * value + effect + noise[(visit + 2 * cluster) % 8]
            response = 1 if latent < -0.65 else 2 if latent < 0.4 else 3
            responses.append(response)
            features.append((value,))
            clusters.append(cluster)
            mix_re.append(float(visit >= 4))
    return tuple(responses), tuple(features), tuple(clusters), tuple(mix_re)


class OrdinalCensoringTests(unittest.TestCase):
    def test_matches_all_frozen_orm_fixtures(self) -> None:
        case_paths = [
            path
            for path in sorted(CASES.glob("*.json"))
            if require_object(load_json(path), name=str(path)).get("operation") == "orm"
        ]
        self.assertEqual(len(case_paths), 3)
        for case_path in case_paths:
            raw_case = require_object(load_json(case_path), name=str(case_path))
            with self.subTest(case_id=raw_case["case_id"]):
                case, expected, policy = validate_case_pair(
                    case_path, EXPECTED / str(raw_case["expected_output"])
                )
                report = compare_json(
                    build_python_output(case), output_payload(expected), policy
                )
                report.require_match()
                self.assertGreater(report.numeric_comparisons, 0)

    def test_fixed_fit_predictions_and_serialization(self) -> None:
        specification = DesignSpec.from_formula("severity ~ x")
        design = specification.transform(
            {"x": (-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5)}
        )
        response = (1, 1, 2, 1, 2, 2, 3, 2, 3, 3)
        result = fit_orm(response, design)
        restored = OrdinalResult.from_json(result.to_json())
        future = specification.transform({"x": (-0.75, 0.75)})

        self.assertEqual(restored, result)
        self.assertEqual(result.design_fingerprint, specification.fingerprint)
        self.assertEqual(len(result.thresholds), 2)
        self.assertTrue(result.thresholds[0] > result.thresholds[1])
        self.assertTrue(
            all(math.isclose(sum(row), 1.0) for row in result.fitted_probabilities)
        )
        self.assertEqual(len(result.predict_linear(future)), 2)
        self.assertEqual(len(result.predict_mean(future)), 2)
        self.assertEqual(len(result.predict_quantile(future)), 2)
        self.assertEqual(len(result.predict_exceedance(future, level=2.0)), 2)
        self.assertEqual(result.likelihood_ratio_test().degrees_of_freedom, 1)
        self.assertEqual(result.wald_test().coefficient_names, result.feature_names)
        self.assertGreaterEqual(result.diagnostics().covariance_condition, 1.0)
        self.assertLessEqual(result.diagnostics().maximum_simplex_error, 1e-12)
        validate_document(result.to_dict(), ORDINAL_RESULT_SCHEMA)

        wrong = DesignSpec.from_formula("severity ~ pol(x, 2)").transform({"x": (0.0,)})
        with self.assertRaisesRegex(InputValidationError, "fingerprint"):
            restored.predict_probabilities(wrong)

    def test_all_links_and_multi_intercept_lrm(self) -> None:
        response = (1, 1, 2, 1, 2, 2, 3, 2, 3, 3, 1, 3)
        features = tuple((value,) for value in (-2.0, -1.5, -1.0, -0.5, 0.0, 0.5) * 2)
        for family in ("logistic", "probit", "loglog", "cloglog", "cauchit"):
            with self.subTest(family=family):
                result = fit_orm(response, features, family=family)  # type: ignore[arg-type]
                self.assertEqual(result.family, family)
                diagonal = np.asarray(result.covariance).diagonal()
                self.assertTrue(all(value > 0.0 for value in diagonal))
        lrm = fit_ordinal_lrm(response, features)
        self.assertEqual((lrm.estimator, lrm.family), ("lrm", "logistic"))

    def test_exact_grid_turnbull_and_mixed_censoring_fit(self) -> None:
        response = CensoredResponse.from_intervals(
            (1, 1, 2, 2, 3, 3, -math.inf, 1, 2, 1, 2, 3),
            (1, 1, 2, 2, 3, 3, 2, math.inf, 3, 1, 2, 3),
        )
        turnbull = response.turnbull()
        self.assertEqual(
            response.censoring_types,
            (
                "exact",
                "exact",
                "exact",
                "exact",
                "exact",
                "exact",
                "left",
                "right",
                "interval",
                "exact",
                "exact",
                "exact",
            ),
        )
        self.assertTrue(turnbull.converged)
        self.assertEqual((turnbull.lower, turnbull.upper), ((1.0, 2.0, 3.0),) * 2)
        self.assertEqual((turnbull.first[6], turnbull.last[6]), (0, 0))
        self.assertEqual((turnbull.first[7], turnbull.last[7]), (1, 2))
        self.assertAlmostEqual(sum(turnbull.probabilities), 1.0)

        features = tuple((float(index % 5) - 2.0,) for index in range(12))
        result = fit_orm(response, features)
        self.assertTrue(result.censored)
        self.assertEqual(result.response_levels, (1.0, 2.0, 3.0))

    def test_right_tail_creates_a_distinct_exact_grid_category(self) -> None:
        response = CensoredResponse.from_intervals(
            (1, 1, 2, 2, 3, 3, 3),
            (1, 1, 2, 2, 3, 3, math.inf),
        )
        turnbull = response.turnbull()
        self.assertEqual(turnbull.lower, (1.0, 2.0, 3.0, 4.0))
        self.assertEqual(turnbull.upper[-1], math.inf)
        self.assertEqual((turnbull.first[-1], turnbull.last[-1]), (3, 3))

    def test_many_level_stress_fit(self) -> None:
        response: list[int] = []
        features: list[tuple[float]] = []
        for replicate in range(4):
            for level in range(1, 65):
                response.append(level)
                features.append((math.sin(level * 1.7 + replicate),))
        result = fit_orm(response, features)
        self.assertEqual(len(result.response_levels), 64)
        self.assertEqual(len(result.thresholds), 63)
        self.assertEqual(np.asarray(result.covariance).shape, (64, 64))

    def test_random_intercept_quadrature_and_mix_re(self) -> None:
        response, features, clusters, mix_re = clustered_data()
        arguments = {
            "quadrature_grid": (7, 11, 15, 21),
            "quadrature_tolerance": 3e-5,
            "max_iterations": 100,
            "tolerance": 2e-5,
        }
        plain = fit_random_intercept_orm(
            response,
            features,
            clusters,
            **arguments,  # type: ignore[arg-type]
        )
        mixed = fit_random_intercept_orm(
            response,
            features,
            clusters,
            mix_re=mix_re,
            **arguments,  # type: ignore[arg-type]
        )

        self.assertGreater(plain.sigma or 0.0, 0.0)
        self.assertGreater(mixed.sigma1 or 0.0, 0.0)
        self.assertIsNotNone(mixed.sigma2)
        self.assertEqual(plain.cluster_count, 8)
        self.assertEqual(len(plain.quadrature_history), 2)
        self.assertEqual(
            plain.variance_component_test.mixture, "0.5*chi2(0)+0.5*chi2(1)"
        )
        self.assertEqual(
            mixed.variance_component_test.mixture, "0.5*chi2(1)+0.5*chi2(2)"
        )
        self.assertGreater(plain.log_likelihood, plain.clustered_null_log_likelihood)
        self.assertEqual(len(mixed.parameter_names), len(mixed.covariance))
        diagonal = np.asarray(mixed.covariance).diagonal()
        self.assertTrue(all(value > 0.0 for value in diagonal))

        with self.assertRaisesRegex(InputValidationError, "vary within"):
            fit_random_intercept_orm(
                response, features, clusters, mix_re=(0.0,) * len(response)
            )

    def test_failure_contracts(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "at least three levels"):
            fit_orm((1, 1, 2, 2), ((0.0,), (1.0,), (2.0,), (3.0,)))
        with self.assertRaises(RankDeficiencyError):
            fit_orm(
                (1, 1, 2, 2, 3, 3),
                tuple((float(value), float(value) * 2.0) for value in range(6)),
            )
        with self.assertRaises(ConvergenceError):
            fit_orm(
                (1, 1, 2, 1, 2, 3, 2, 3, 3),
                tuple((float(value),) for value in range(9)),
                max_iterations=1,
            )
        with self.assertRaisesRegex(InputValidationError, "exact response"):
            CensoredResponse.from_intervals((-math.inf, 1.0), (1.0, math.inf))
        with self.assertRaisesRegex(InputValidationError, "invalid censoring"):
            CensoredResponse.from_intervals((2.0, 1.0), (1.0, 1.0))

        result = fit_orm(
            (1, 1, 2, 1, 2, 2, 3, 2, 3, 3),
            tuple(
                (value,)
                for value in (-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5)
            ),
        )
        document = result.to_dict()
        document["future_field"] = True
        with self.assertRaises(InputValidationError):
            OrdinalResult.from_dict(document)


if __name__ == "__main__":
    unittest.main()
