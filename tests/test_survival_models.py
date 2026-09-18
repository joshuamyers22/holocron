from __future__ import annotations

import unittest
from typing import Literal

from holocron.exceptions import (
    ConvergenceError,
    InputValidationError,
    RankDeficiencyError,
)
from holocron.models import (
    CoxResult,
    NonparametricSurvivalResult,
    ParametricSurvivalResult,
    fit_cph,
    fit_npsurv,
    fit_psm,
)
from reference.contracts import (
    CASES,
    COX_RESULT_SCHEMA,
    EXPECTED,
    NONPARAMETRIC_SURVIVAL_RESULT_SCHEMA,
    PARAMETRIC_SURVIVAL_RESULT_SCHEMA,
    compare_json,
    load_json,
    output_payload,
    require_object,
    validate_case_pair,
    validate_document,
)
from reference.python_parity import build_python_output


class SurvivalModelTests(unittest.TestCase):
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

    def test_matches_all_survival_oracle_fixtures(self) -> None:
        case_paths = [
            path
            for path in sorted(CASES.glob("*.json"))
            if require_object(load_json(path), name=str(path)).get("operation")
            in {"cph", "psm", "npsurv"}
        ]
        self.assertEqual(len(case_paths), 6)
        exact_comparisons = 0
        numeric_comparisons = 0
        for case_path in case_paths:
            raw = require_object(load_json(case_path), name=str(case_path))
            with self.subTest(case_id=raw["case_id"]):
                case, expected, policy = validate_case_pair(
                    case_path, EXPECTED / str(raw["expected_output"])
                )
                report = compare_json(
                    build_python_output(case), output_payload(expected), policy
                )
                report.require_match()
                self.assertGreater(report.numeric_comparisons, 0)
                exact_comparisons += report.exact_comparisons
                numeric_comparisons += report.numeric_comparisons
        self.assertEqual(exact_comparisons, 190)
        self.assertEqual(numeric_comparisons, 446)

    def test_cox_ties_predictions_and_round_trip(self) -> None:
        features = tuple((float(value),) for value in self.x)
        result = fit_cph(
            self.times,
            self.events,
            features,
            method="efron",
            feature_names=("x",),
        )
        restored = CoxResult.from_json(result.to_json())

        self.assertEqual(restored, result)
        self.assertEqual(result.coefficient_names, ("x",))
        self.assertGreater(result.log_likelihood[1], result.log_likelihood[0])
        self.assertEqual(
            len(result.baseline_times),
            len(
                {
                    time
                    for time, event in zip(self.times, self.events, strict=True)
                    if event
                }
            ),
        )
        self.assertEqual(
            restored.predict_linear(((-1.5,), (0.0,), (1.5,))),
            result.predict_linear(((-1.5,), (0.0,), (1.5,))),
        )
        predictions = result.predict_survival(
            ((-1.5,), (0.0,), (1.5,)), (0.0, 3.0, 6.0, 10.0)
        )
        self.assertTrue(all(row[0] == 1.0 for row in predictions))
        self.assertTrue(
            all(
                later <= earlier
                for row in predictions
                for earlier, later in zip(row[:-1], row[1:], strict=True)
            )
        )
        validate_document(result.to_dict(), COX_RESULT_SCHEMA)

    def test_parametric_distributions_predictions_and_round_trip(self) -> None:
        features = tuple((float(value),) for value in self.x)
        distributions: tuple[Literal["weibull", "exponential"], ...] = (
            "weibull",
            "exponential",
        )
        for distribution in distributions:
            with self.subTest(distribution=distribution):
                result = fit_psm(
                    self.times,
                    self.events,
                    features,
                    distribution=distribution,
                    feature_names=("x",),
                )
                restored = ParametricSurvivalResult.from_json(result.to_json())
                self.assertEqual(restored, result)
                self.assertGreater(result.log_likelihood[1], result.log_likelihood[0])
                predictions = result.predict_survival(
                    ((-1.5,), (0.0,), (1.5,)), (3.0, 6.0, 10.0)
                )
                self.assertTrue(
                    all(
                        later < earlier
                        for row in predictions
                        for earlier, later in zip(row[:-1], row[1:], strict=True)
                    )
                )
                validate_document(result.to_dict(), PARAMETRIC_SURVIVAL_RESULT_SCHEMA)

    def test_kaplan_meier_counts_intervals_and_round_trip(self) -> None:
        result = fit_npsurv((1, 2, 2, 3, 4, 4, 5, 6), (1, 1, 0, 1, 0, 1, 1, 0))
        restored = NonparametricSurvivalResult.from_json(result.to_json())

        self.assertEqual(restored, result)
        self.assertEqual(result.n_risk, (8, 7, 5, 4, 2, 1))
        self.assertEqual(result.n_event, (1, 1, 1, 1, 1, 0))
        self.assertEqual(result.n_censor, (0, 1, 0, 1, 0, 1))
        for actual, expected in zip(
            result.predict((0, 1, 2.5, 9)),
            (1.0, 0.875, 0.75, 0.225),
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertTrue(
            all(
                low <= survival <= high
                for low, survival, high in zip(
                    result.lower, result.survival, result.upper, strict=True
                )
            )
        )
        validate_document(result.to_dict(), NONPARAMETRIC_SURVIVAL_RESULT_SCHEMA)

    def test_failures_are_structured_and_readers_reject_tampering(self) -> None:
        features = tuple((float(value),) for value in self.x)
        with self.assertRaisesRegex(InputValidationError, "positive"):
            fit_npsurv((0.0, 1.0), (1, 0))
        with self.assertRaisesRegex(InputValidationError, "observed event"):
            fit_npsurv((1.0, 2.0), (0, 0))
        with self.assertRaisesRegex(InputValidationError, "one row"):
            fit_cph(self.times, self.events, features[:-1])
        with self.assertRaises(RankDeficiencyError):
            fit_psm(
                self.times,
                self.events,
                tuple((float(value), 2.0 * float(value)) for value in self.x),
            )
        with self.assertRaises(ConvergenceError):
            fit_psm(
                self.times,
                self.events,
                features,
                max_iterations=1,
            )

        result = fit_cph(self.times, self.events, features)
        document = result.to_dict()
        document["future_field"] = True
        with self.assertRaises(InputValidationError):
            CoxResult.from_dict(document)
        with self.assertRaises(InputValidationError):
            ParametricSurvivalResult.from_json('{"schema_version":NaN}')


if __name__ == "__main__":
    unittest.main()
