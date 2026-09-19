from __future__ import annotations

import math
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
    SurvivalCurveResult,
    SurvivalResponse,
    fit_cph,
    fit_npsurv,
    fit_psm,
    survival_residuals,
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
        self.assertEqual(len(case_paths), 14)
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
        self.assertEqual(exact_comparisons, 579)
        self.assertEqual(numeric_comparisons, 1019)

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

    def test_parametric_left_and_interval_censoring(self) -> None:
        lower = (12, 8, 12, 7, 10, -math.inf, 7, -math.inf, 5, 8, 12, 7)
        upper = (12, 10, math.inf, 7, math.inf, 7, 9, 5, 5, math.inf, 14, 7)
        response = SurvivalResponse.from_intervals(lower, upper)
        self.assertEqual(
            response.censoring_types,
            (
                "exact",
                "interval",
                "right",
                "exact",
                "right",
                "left",
                "interval",
                "left",
                "exact",
                "right",
                "interval",
                "exact",
            ),
        )
        features = tuple((float(value),) for value in self.x[: len(lower)])
        result = fit_psm(response, features, feature_names=("x",))
        self.assertEqual(result.n_observations, len(lower))
        self.assertTrue(all(math.isfinite(value) for value in result.coefficients))
        self.assertGreater(result.log_likelihood[1], result.log_likelihood[0])
        self.assertEqual(ParametricSurvivalResult.from_json(result.to_json()), result)

        ordinary_features = tuple((float(value),) for value in self.x)
        ordinary = fit_psm(self.times, self.events, ordinary_features)
        explicit = SurvivalResponse.from_intervals(
            self.times,
            tuple(
                float(time) if event else math.inf
                for time, event in zip(self.times, self.events, strict=True)
            ),
        )
        reconstructed = fit_psm(explicit, ordinary_features)
        for actual, expected in zip(
            reconstructed.coefficients, ordinary.coefficients, strict=True
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertIsNotNone(reconstructed.scale)
        self.assertIsNotNone(ordinary.scale)
        assert reconstructed.scale is not None and ordinary.scale is not None
        self.assertAlmostEqual(reconstructed.scale, ordinary.scale)

        with self.assertRaisesRegex(InputValidationError, "invalid survival"):
            SurvivalResponse.from_intervals((1.0, 3.0), (2.0, 2.0))
        with self.assertRaisesRegex(InputValidationError, "finite event bound"):
            SurvivalResponse.from_intervals((1.0, 2.0), (math.inf, math.inf))
        with self.assertRaisesRegex(InputValidationError, "invalid survival"):
            SurvivalResponse.from_intervals((True,), (1.0,))

    def test_cox_curve_quantile_and_restricted_mean_predictions(self) -> None:
        features = tuple((float(value),) for value in self.x)
        result = fit_cph(
            self.times,
            self.events,
            features,
            feature_names=("x",),
        )
        evaluation = ((-1.5,), (0.0,), (1.5,))

        curve = result.predict_curve(evaluation, (0.0, 3.0, 6.0, 10.0))
        self.assertIsInstance(curve, SurvivalCurveResult)
        self.assertEqual(curve.times, (0.0, 3.0, 6.0, 10.0))
        self.assertEqual(curve.strata, ("__all__",) * 3)
        self.assertEqual(
            curve.survival,
            result.predict_survival(evaluation, curve.times),
        )
        self.assertEqual(curve.linear_predictors, result.predict_linear(evaluation))

        quantiles = result.predict_quantile(evaluation, (0.25, 0.5, 0.9))
        self.assertEqual(len(quantiles), 3)
        self.assertTrue(
            all(
                first is None or second is None or first <= second
                for row in quantiles
                for first, second in zip(row[:-1], row[1:], strict=True)
            )
        )
        means = result.predict_mean(evaluation, restricted_time=10.0)
        self.assertTrue(all(0.0 < value <= 10.0 for value in means))
        self.assertGreater(means[0], means[1])
        self.assertGreater(means[1], means[2])

        linear_quantiles = result.predict_quantile(
            evaluation, (0.25, 0.5), interpolation="linear"
        )
        linear_means = result.predict_mean(
            evaluation, restricted_time=10.0, interpolation="linear"
        )
        self.assertTrue(
            all(
                value is None or value > 0.0
                for row in linear_quantiles
                for value in row
            )
        )
        self.assertTrue(all(0.0 < value <= 10.0 for value in linear_means))

    def test_parametric_curve_quantile_and_mean_predictions(self) -> None:
        features = tuple((float(value),) for value in self.x)
        evaluation = ((-1.5,), (0.0,), (1.5,))
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
                curve = result.predict_curve(evaluation, (3.0, 6.0, 10.0))
                self.assertEqual(
                    curve.survival,
                    result.predict_survival(evaluation, curve.times),
                )
                quantiles = result.predict_quantile(evaluation, (0.25, 0.5, 0.75))
                self.assertTrue(
                    all(
                        first < second
                        for row in quantiles
                        for first, second in zip(row[:-1], row[1:], strict=True)
                    )
                )
                means = result.predict_mean(evaluation)
                self.assertTrue(all(value > 0.0 for value in means))
                self.assertGreater(means[0], means[1])
                self.assertGreater(means[1], means[2])
                for index, values in enumerate(quantiles):
                    median = values[1]
                    predicted = result.predict_survival(
                        (evaluation[index],),
                        (median,),
                    )
                    self.assertAlmostEqual(predicted[0][0], 0.5)

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

    def test_kaplan_meier_curve_quantile_and_restricted_mean_predictions(self) -> None:
        result = fit_npsurv(
            (1, 2, 2, 3, 4, 4, 5, 6),
            (1, 1, 0, 1, 0, 1, 1, 0),
        )

        curve = result.predict_curve((0.0, 1.0, 2.5, 5.0))
        self.assertEqual(curve.strata, ("__all__",))
        self.assertEqual(curve.linear_predictors, None)
        for actual, expected in zip(
            curve.survival[0], (1.0, 0.875, 0.75, 0.225), strict=True
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(
            result.predict_quantile((0.25, 0.5, 0.9)),
            ((2.5, 4.0, None),),
        )
        self.assertAlmostEqual(result.predict_mean(restricted_time=5.0)[0], 3.675)
        self.assertTrue(
            0.0
            < result.predict_mean(restricted_time=5.0, interpolation="linear")[0]
            <= 5.0
        )

        terminal_plateau = fit_npsurv((1, 1, 2, 3), (1, 1, 0, 0))
        self.assertEqual(terminal_plateau.predict_quantile((0.5,)), ((2.0,),))
        ending_drop = fit_npsurv((1, 1, 1, 2, 3, 4), (1, 1, 1, 0, 0, 1))
        self.assertEqual(ending_drop.predict_quantile((0.5,)), ((2.5,),))

        with self.assertRaisesRegex(InputValidationError, "strictly increasing"):
            result.predict_curve((1.0, 1.0))
        with self.assertRaisesRegex(InputValidationError, "strictly between"):
            result.predict_quantile((0.0,))
        with self.assertRaisesRegex(InputValidationError, "curve support"):
            result.predict_mean(restricted_time=7.0)
        with self.assertRaisesRegex(InputValidationError, "inconsistent"):
            SurvivalCurveResult(
                times=(1.0, 2.0),
                strata=("__all__",),
                survival=((0.5, 0.6),),
                linear_predictors=None,
            )

    def test_cox_counting_process_strata_weights_offsets_and_residuals(self) -> None:
        features = tuple((float(value),) for value in self.x)
        strata = tuple("A" if index % 2 == 0 else "B" for index in range(18))
        entry = tuple(
            float(min(index % 3, time - 1)) for index, time in enumerate(self.times)
        )
        weights = tuple(1.0 + 0.5 * (index % 3) for index in range(18))
        offsets = tuple(0.05 * (index % 4 - 1.5) for index in range(18))
        result = fit_cph(
            self.times,
            self.events,
            features,
            feature_names=("x",),
            entry_times=entry,
            strata=strata,
            weights=weights,
            offsets=offsets,
        )

        self.assertEqual(result.strata_levels, ("A", "B"))
        self.assertEqual(set(result.baseline_strata), {"A", "B"})
        self.assertTrue(all(value > 0.0 for value in result.baseline_hazard))
        self.assertEqual(
            result.baseline_survival,
            tuple(math.exp(-value) for value in result.baseline_cumulative_hazard),
        )
        survival = result.predict_survival(
            ((-1.0,), (0.5,)),
            (3.0, 6.0, 10.0),
            strata=("A", "B"),
            offsets=(0.1, -0.1),
        )
        cumulative = result.predict_cumulative_hazard(
            ((-1.0,), (0.5,)),
            (3.0, 6.0, 10.0),
            strata=("A", "B"),
            offsets=(0.1, -0.1),
        )
        self.assertEqual(len(survival), 2)
        self.assertTrue(all(value >= 0.0 for row in cumulative for value in row))
        martingale = survival_residuals(
            result,
            self.times,
            self.events,
            entry_times=entry,
            strata=strata,
        )
        deviance = survival_residuals(
            result,
            self.times,
            self.events,
            kind="deviance",
            entry_times=entry,
            strata=strata,
        )
        self.assertEqual(len(martingale.values), len(self.times))
        self.assertTrue(all(value == value for value in deviance.values))
        self.assertEqual(CoxResult.from_json(result.to_json()), result)

    def test_parametric_scale_strata_weights_offsets_and_residuals(self) -> None:
        features = tuple((float(value),) for value in self.x)
        strata = tuple("A" if index % 2 == 0 else "B" for index in range(18))
        weights = tuple(1.0 + 0.5 * (index % 3) for index in range(18))
        offsets = tuple(0.05 * (index % 4 - 1.5) for index in range(18))
        result = fit_psm(
            self.times,
            self.events,
            features,
            feature_names=("x",),
            strata=strata,
            weights=weights,
            offsets=offsets,
        )

        self.assertIsNone(result.scale)
        self.assertEqual(result.strata_levels, ("A", "B"))
        self.assertEqual(len(result.scales), 2)
        hazard = result.predict_hazard(
            ((-1.0,), (0.5,)),
            (3.0, 6.0, 10.0),
            strata=("A", "B"),
            offsets=(0.1, -0.1),
        )
        self.assertTrue(all(value > 0.0 for row in hazard for value in row))
        for kind in ("normalized", "response", "martingale", "deviance"):
            residual = survival_residuals(
                result, self.times, self.events, kind=kind, strata=strata
            )
            self.assertEqual(len(residual.values), len(self.times))
        self.assertEqual(ParametricSurvivalResult.from_json(result.to_json()), result)
        with self.assertRaisesRegex(InputValidationError, "scale strata"):
            fit_psm(
                self.times,
                self.events,
                features,
                distribution="exponential",
                strata=strata,
            )

    def test_counting_process_weighted_stratified_kaplan_meier(self) -> None:
        result = fit_npsurv(
            (2, 3, 4, 5, 2, 4, 5, 6),
            (1, 0, 1, 1, 0, 1, 0, 1),
            entry_times=(0, 1, 1, 2, 0, 0, 3, 2),
            strata=("A", "A", "A", "A", "B", "B", "B", "B"),
            weights=(1, 2, 1, 2, 1, 2, 1, 2),
        )

        self.assertEqual(result.strata_levels, ("A", "B"))
        self.assertEqual(result.n_risk, (4.0, 5.0, 3.0, 2.0, 3.0, 5.0, 3.0, 2.0))
        self.assertEqual(result.predict((0, 2, 6), stratum="A"), (1.0, 0.75, 0.0))
        self.assertEqual(result.predict((0, 2, 6), stratum="B"), (1.0, 1.0, 0.0))
        self.assertEqual(
            NonparametricSurvivalResult.from_json(result.to_json()), result
        )

    def test_v1_survival_results_are_migrated_in_memory(self) -> None:
        features = tuple((float(value),) for value in self.x)
        cox_document = fit_cph(self.times, self.events, features).to_dict()
        cox_document["schema_version"] = "holocron-cox-result/v1"
        for field in (
            "baseline_strata",
            "baseline_hazard",
            "baseline_survival",
            "strata_levels",
        ):
            del cox_document[field]
        self.assertEqual(CoxResult.from_dict(cox_document).strata_levels, ("__all__",))

        psm_document = fit_psm(self.times, self.events, features).to_dict()
        psm_document["schema_version"] = "holocron-parametric-survival-result/v1"
        del psm_document["strata_levels"]
        del psm_document["scales"]
        self.assertEqual(
            ParametricSurvivalResult.from_dict(psm_document).strata_levels,
            ("__all__",),
        )

        npsurv_document = fit_npsurv(self.times, self.events).to_dict()
        npsurv_document["schema_version"] = "holocron-nonparametric-survival-result/v1"
        del npsurv_document["strata"]
        del npsurv_document["strata_levels"]
        self.assertEqual(
            NonparametricSurvivalResult.from_dict(npsurv_document).strata_levels,
            ("__all__",),
        )

    def test_failures_are_structured_and_readers_reject_tampering(self) -> None:
        features = tuple((float(value),) for value in self.x)
        with self.assertRaisesRegex(InputValidationError, "positive"):
            fit_npsurv((0.0, 1.0), (1, 0))
        with self.assertRaisesRegex(InputValidationError, "observed event"):
            fit_npsurv((1.0, 2.0), (0, 0))
        with self.assertRaisesRegex(InputValidationError, "one row"):
            fit_cph(self.times, self.events, features[:-1])
        with self.assertRaisesRegex(InputValidationError, "strictly below"):
            fit_cph(
                self.times,
                self.events,
                features,
                entry_times=self.times,
            )
        with self.assertRaisesRegex(InputValidationError, "positive"):
            fit_cph(self.times, self.events, features, weights=(0.0,) * len(self.times))
        with self.assertRaisesRegex(InputValidationError, "non-empty string"):
            fit_npsurv(
                self.times,
                self.events,
                strata=("A",) * (len(self.times) - 1) + (0,),  # type: ignore[arg-type]
            )
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
