from __future__ import annotations

import unittest

import numpy as np

from holocron.design import DesignSpec
from holocron.exceptions import InputValidationError
from holocron.models import (
    AnovaResult,
    ModelSummary,
    PredictionResult,
    anova,
    contrast,
    covariance,
    fit_glm,
    fit_lrm,
    fit_ols,
    likelihood,
    predict,
    residuals,
    summarize,
)
from reference.contracts import (
    CASES,
    EXPECTED,
    compare_json,
    output_payload,
    validate_case_pair,
)
from reference.python_parity import build_python_output


class PostfitOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x = tuple(float(value) for value in range(-3, 9))
        self.y = (1.1, 1.8, 2.4, 3.2, 3.7, 5.1, 5.5, 6.8, 7.4, 8.1, 9.3, 9.9)
        self.ols_specification = DesignSpec.from_formula("y ~ x")
        self.ols_design = self.ols_specification.transform({"x": self.x})
        self.ols = fit_ols(self.y, self.ols_design)

        self.binary_x = tuple(float(value) for value in (-3, -2, -1, 0, 1, 2, 3) * 2)
        self.binary_y = (0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1)
        self.binary_specification = DesignSpec.from_formula("event ~ x")
        self.binary_design = self.binary_specification.transform({"x": self.binary_x})

    def test_ols_operations_match_rms_reference_values(self) -> None:
        selected = covariance(self.ols, ("asis(x)",))
        fit_likelihood = likelihood(self.ols)
        fit_summary = summarize(self.ols)
        fit_anova = anova(self.ols, self.ols_specification)
        slope = contrast(self.ols, {"asis(x)": 1.0}, name="x: 1 vs 0")
        predictions = predict(
            self.ols,
            self.ols_specification.transform({"x": (-1.5, 2.5, 6.5)}),
        )

        self.assertEqual(selected.coefficient_names, ("asis(x)",))
        np.testing.assert_allclose(selected.matrix, ((0.0003525274,),), atol=5e-11)
        self.assertAlmostEqual(fit_likelihood.log_likelihood, 1.991891968430485)
        self.assertAlmostEqual(fit_likelihood.null_log_likelihood, -29.564180851066375)
        self.assertAlmostEqual(fit_likelihood.aic, 2.01621606313903)
        self.assertIsInstance(fit_summary, ModelSummary)
        self.assertEqual(fit_summary.coefficients[1].distribution, "t")
        self.assertEqual(fit_summary.coefficients[1].degrees_of_freedom, 10)
        np.testing.assert_allclose(
            (slope.estimate, slope.standard_error, slope.lower, slope.upper),
            (0.8213286713286716, 0.018775713726886658, 0.7794937741, 0.8631635686),
            atol=1e-10,
        )
        self.assertIsInstance(predictions, PredictionResult)
        np.testing.assert_allclose(
            predictions.values,
            (2.0730186480186488, 5.358333333333335, 8.643648018648022),
            atol=1e-13,
        )
        np.testing.assert_allclose(
            predictions.standard_errors,
            (0.09920378340172233, 0.06481475006471779, 0.0992037834017223),
            atol=1e-13,
        )
        np.testing.assert_allclose(
            predictions.lower,
            (1.8519788439572404, 5.213917070532358, 8.422608214586614),
            atol=1e-12,
        )
        self.assertIsInstance(fit_anova, AnovaResult)
        self.assertEqual(fit_anova.tests[0].term, "x")
        self.assertEqual(fit_anova.tests[0].distribution, "f")
        self.assertAlmostEqual(fit_anova.tests[0].statistic, 1913.555475920743)
        np.testing.assert_allclose(
            residuals(self.ols).values,
            (
                0.25897435897435894,
                0.1376456876456873,
                -0.08368298368298444,
                -0.10501165501165577,
                -0.4263403263403278,
                0.1523310023310005,
                -0.2689976689976703,
                0.20967365967365748,
                -0.011655011655014036,
                -0.1329836829836868,
                0.245687645687644,
                0.024358974358971608,
            ),
            atol=1e-14,
        )

    def test_binary_operations_match_lrm_and_glm_reference_values(self) -> None:
        future = self.binary_specification.transform({"x": (-2.5, 0.5, 2.5)})
        for result in (
            fit_lrm(self.binary_y, self.binary_design),
            fit_glm(self.binary_y, self.binary_design, family="binomial"),
        ):
            if result.estimator == "lrm":
                expected_coefficient = 0.909622450368207
                expected_prediction_se = (1.3386568142545736, 0.7381151869649283)
                expected_lower = -4.897775269518606
                expected_wald = 3.9805369082431374
                expected_p = 0.04602888920118259
            else:
                expected_coefficient = 0.9096224285560887
                expected_prediction_se = (1.3384981623471726, 0.7380629692413808)
                expected_lower = -5.190393039998245
                expected_wald = 3.981646599464812
                expected_p = 0.04599857626243741
            with self.subTest(estimator=result.estimator):
                prediction = predict(result, future, scale="linear")
                term_test = anova(result, self.binary_specification).tests[0]
                slope = contrast(result, {"asis(x)": 1.0}, name="slope")
                fit_likelihood = likelihood(result)

                self.assertAlmostEqual(slope.estimate, expected_coefficient, places=13)
                np.testing.assert_allclose(
                    prediction.standard_errors[:2],
                    expected_prediction_se,
                    atol=1e-13,
                )
                self.assertAlmostEqual(prediction.lower[0], expected_lower)
                self.assertAlmostEqual(term_test.statistic, expected_wald)
                self.assertAlmostEqual(term_test.p_value, expected_p)
                self.assertAlmostEqual(
                    fit_likelihood.log_likelihood, -6.322770550791965
                )
                self.assertAlmostEqual(fit_likelihood.aic, 16.64554110158393)
                self.assertEqual(term_test.distribution, "chi-square")
                self.assertEqual(
                    slope.distribution, "t" if result.estimator == "glm" else "normal"
                )
                deviance = residuals(
                    result, kind="deviance", response=self.binary_y
                ).values
                np.testing.assert_allclose(
                    deviance[:4],
                    (-0.3556686, -0.5482156, -0.8226567, -1.1774100),
                    atol=6e-8,
                )

    def test_response_scale_prediction_transforms_link_limits(self) -> None:
        result = fit_lrm(self.binary_y, self.binary_design)
        future = self.binary_specification.transform({"x": (-2.5, 0.5, 2.5)})
        linear = predict(result, future, scale="linear")
        probability = predict(result, future, scale="response")

        np.testing.assert_allclose(
            probability.values,
            tuple(1.0 / (1.0 + np.exp(-value)) for value in linear.values),
            atol=1e-15,
        )
        self.assertTrue(all(0.0 < value < 1.0 for value in probability.lower))
        self.assertTrue(all(0.0 < value < 1.0 for value in probability.upper))

    def test_anova_respects_multiple_formula_term_blocks(self) -> None:
        specification = DesignSpec.from_formula("y ~ rcs(x, [-3, 0, 4, 8]) + z")
        z = tuple(float(index % 3) for index in range(len(self.x)))
        design = specification.transform({"x": self.x, "z": z})
        response = tuple(
            2.0 + 0.4 * x + 0.3 * z_value + 0.03 * x * x + (-1) ** index * 0.1
            for index, (x, z_value) in enumerate(zip(self.x, z, strict=True))
        )
        result = fit_ols(response, design)
        tests = anova(result, specification).tests

        self.assertEqual(
            tuple(test.term for test in tests),
            (
                "rcs(x, [-3.0, 0.0, 4.0, 8.0])",
                "z",
            ),
        )
        self.assertEqual(tuple(test.degrees_of_freedom for test in tests), (3, 1))
        self.assertEqual(tests[0].coefficient_names, result.coefficient_names[1:4])

    def test_operations_fail_closed_on_missing_inputs_and_wrong_identity(self) -> None:
        binary = fit_lrm(self.binary_y, self.binary_design)
        with self.assertRaisesRegex(InputValidationError, "original response"):
            residuals(binary, kind="pearson")
        with self.assertRaisesRegex(InputValidationError, "unknown coefficients"):
            contrast(binary, {"missing": 1.0})
        with self.assertRaisesRegex(InputValidationError, "all be zero"):
            contrast(binary, (0.0, 0.0))
        with self.assertRaisesRegex(InputValidationError, "mean intervals"):
            predict(binary, ((0.0,),), interval="individual")
        wrong = DesignSpec.from_formula("event ~ pol(x, 2)")
        with self.assertRaisesRegex(InputValidationError, "differs"):
            anova(binary, wrong)
        raw_fit = fit_ols(self.y, tuple((value,) for value in self.x))
        with self.assertRaisesRegex(InputValidationError, "DesignMatrix"):
            anova(raw_fit, self.ols_specification)

    def test_all_postfit_oracle_fixtures_match(self) -> None:
        case_paths = sorted(CASES.glob("postfit-*.json"))
        self.assertEqual(len(case_paths), 3)
        for case_path in case_paths:
            with self.subTest(case_id=case_path.stem):
                case, expected, policy = validate_case_pair(
                    case_path, EXPECTED / f"{case_path.stem}.json"
                )
                report = compare_json(
                    build_python_output(case), output_payload(expected), policy
                )
                report.require_match()
                self.assertGreater(report.numeric_comparisons, 60)


if __name__ == "__main__":
    unittest.main()
