from __future__ import annotations

import unittest
from typing import cast

import numpy as np

from holocron.design import DesignSpec
from holocron.exceptions import (
    ConvergenceError,
    InputValidationError,
    RankDeficiencyError,
    SeparationError,
    UnsupportedFeatureError,
)
from holocron.models import BinaryLogisticResult, OlsResult, fit_glm, fit_lrm
from reference.contracts import (
    BINARY_LOGISTIC_RESULT_SCHEMA,
    CASES,
    EXPECTED,
    compare_json,
    load_json,
    output_payload,
    require_object,
    validate_case_pair,
    validate_document,
)
from reference.python_parity import build_python_output


class GeneralizedModelTests(unittest.TestCase):
    def test_lrm_predicts_and_round_trips_with_design_identity(self) -> None:
        specification = DesignSpec.from_formula("event ~ x")
        training = specification.transform(
            {"x": (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0)}
        )
        result = fit_lrm((0, 0, 0, 1, 0, 1, 1, 1), training)
        restored = BinaryLogisticResult.from_json(result.to_json())
        future = specification.transform({"x": (-0.5, 0.5, 2.5)})

        self.assertEqual(restored, result)
        self.assertEqual(result.estimator, "lrm")
        self.assertEqual(result.design_fingerprint, specification.fingerprint)
        self.assertEqual(
            restored.predict_probability(future), result.predict_probability(future)
        )
        self.assertTrue(all(0.0 < value < 1.0 for value in result.fitted_probabilities))
        self.assertEqual(len(result.fingerprint), 64)
        validate_document(result.to_dict(), BINARY_LOGISTIC_RESULT_SCHEMA)

        wrong_design = DesignSpec.from_formula("event ~ pol(x, 2)").transform(
            {"x": (0.0,)}
        )
        with self.assertRaisesRegex(InputValidationError, "fingerprint"):
            restored.predict_probability(wrong_design)

    def test_glm_supports_gaussian_identity_and_binomial_logit(self) -> None:
        features = ((-2.0,), (-1.0,), (0.0,), (1.0,), (2.0,), (3.0,))
        gaussian = fit_glm(
            (-1.8, -0.9, 0.2, 1.0, 2.2, 2.8),
            features,
            family="gaussian",
            feature_names=("x",),
        )
        binary = fit_glm(
            (0, 0, 0, 1, 0, 1),
            features,
            family="binomial",
            feature_names=("x",),
        )

        self.assertIsInstance(gaussian, OlsResult)
        self.assertIsInstance(binary, BinaryLogisticResult)
        self.assertEqual(binary.estimator, "glm")
        self.assertEqual(binary.coefficient_names, ("Intercept", "x"))

    def test_failures_are_structured_and_fail_closed(self) -> None:
        with self.assertRaisesRegex(InputValidationError, "both 0 and 1"):
            fit_lrm((1, 1, 1, 1), ((0.0,), (1.0,), (2.0,), (3.0,)))
        with self.assertRaisesRegex(RankDeficiencyError, "full column rank"):
            fit_lrm(
                (0, 0, 1, 1, 0, 1),
                tuple((float(value), float(value) * 2.0) for value in range(6)),
            )
        with self.assertRaises(SeparationError):
            fit_lrm(
                (0, 0, 0, 1, 1, 1),
                ((-3.0,), (-2.0,), (-1.0,), (1.0,), (2.0,), (3.0,)),
            )
        with self.assertRaises(SeparationError):
            fit_glm(
                (0, 0, 0, 1, 1, 1),
                ((-3.0,), (-2.0,), (-1.0,), (1.0,), (2.0,), (3.0,)),
                family="binomial",
            )
        with self.assertRaises(ConvergenceError):
            fit_lrm(
                (0, 0, 1, 0, 1, 1),
                ((-3.0,), (-2.0,), (-1.0,), (1.0,), (2.0,), (3.0,)),
                max_iterations=1,
            )
        with self.assertRaises(UnsupportedFeatureError):
            fit_glm(  # pyright: ignore[reportCallIssue]
                (0.0, 1.0, 2.0, 3.0),
                ((0.0,), (1.0,), (2.0,), (3.0,)),
                family="gaussian",
                link=cast(object, "log"),  # pyright: ignore[reportArgumentType]
            )

    def test_binary_reader_rejects_tampering(self) -> None:
        result = fit_lrm(
            (0, 0, 1, 0, 1, 1),
            ((-3.0,), (-2.0,), (-1.0,), (1.0,), (2.0,), (3.0,)),
        )
        document = result.to_dict()
        document["future_field"] = True
        with self.assertRaises(InputValidationError):
            BinaryLogisticResult.from_dict(document)

        with self.assertRaises(InputValidationError):
            BinaryLogisticResult.from_json('{"schema_version":NaN}')

    def test_matches_all_lrm_and_glm_oracle_fixtures(self) -> None:
        case_paths = [
            path
            for path in sorted(CASES.glob("*.json"))
            if require_object(load_json(path), name=str(path)).get("operation")
            in {"glm", "lrm"}
        ]
        self.assertEqual(len(case_paths), 7)
        for case_path in case_paths:
            raw_case = require_object(load_json(case_path), name=str(case_path))
            with self.subTest(case_id=raw_case["case_id"]):
                case, expected, policy = validate_case_pair(
                    case_path, EXPECTED / str(raw_case["expected_output"])
                )
                actual = build_python_output(case)
                report = compare_json(actual, output_payload(expected), policy)
                report.require_match()
                self.assertGreater(report.numeric_comparisons, 0)

    def test_glm_binomial_matches_reference_coefficients_tightly(self) -> None:
        result = fit_glm(
            (0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1),
            tuple((float(value),) for value in (-3, -2, -1, 0, 1, 2, 3) * 2),
            family="binomial",
            feature_names=("x",),
        )
        np.testing.assert_allclose(
            result.coefficients,
            (1.726857782787479e-16, 0.9096224285560882),
            atol=1e-14,
            rtol=1e-13,
        )
        np.testing.assert_allclose(
            result.covariance,
            (
                (0.4927852638970139, 2.1032197738607934e-17),
                (2.1032197738607934e-17, 0.20780673067355898),
            ),
            atol=1e-14,
            rtol=1e-13,
        )


if __name__ == "__main__":
    unittest.main()
