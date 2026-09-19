from __future__ import annotations

import unittest
from xml.etree import ElementTree as ET

from holocron.exceptions import InputValidationError
from holocron.graphics import (
    AxisSpec,
    BarLayer,
    IntervalLayer,
    LineLayer,
    PlotSpec,
    ReferenceLine,
    anova_plot_spec,
    calibration_plot_spec,
    contrast_plot_spec,
    diagnostic_plot_spec,
    effect_plot_spec,
    render_svg,
    survival_plot_spec,
    validation_plot_spec,
)
from holocron.models import (
    AnovaResult,
    AnovaTest,
    InferenceEstimate,
    InfluenceObservation,
    InfluenceResult,
    PredictionResult,
    SurvivalCurveResult,
    VarianceInflationFactor,
    fit_ols,
    robustness_diagnostics,
    trace_penalty,
    validate_survival_predictions,
)
from holocron.validation import (
    ResamplePlan,
    calibrate_model,
    optimism_correct_calibration,
    optimism_correct_validation,
    validate_model,
    validate_probabilities,
)

SVG = "{http://www.w3.org/2000/svg}"


class PlotAdapterTests(unittest.TestCase):
    def test_effect_contrast_and_anova_adapters_preserve_source_values(self) -> None:
        predictions = PredictionResult(
            scale="response",
            interval="mean",
            confidence_level=0.95,
            values=(1.0, 1.5, 2.2),
            standard_errors=(0.1, 0.1, 0.2),
            lower=(0.8, 1.3, 1.8),
            upper=(1.2, 1.7, 2.6),
        )
        effect = effect_plot_spec(predictions, (0.0, 1.0, 2.0))
        estimate = effect.layers[1]
        self.assertEqual(effect.kind, "effect")
        self.assertEqual(estimate.layer_id, "estimate")

        estimates = (
            InferenceEstimate("A - B", 0.4, 0.2, 2.0, "normal", None, 0.04, 0.01, 0.79),
            InferenceEstimate(
                "A - C", -0.2, 0.1, -2.0, "normal", None, 0.04, -0.4, 0.0
            ),
        )
        contrasts = contrast_plot_spec(estimates)
        self.assertEqual(contrasts.kind, "contrast")
        reference = contrasts.annotations[0]
        self.assertIsInstance(reference, ReferenceLine)
        assert isinstance(reference, ReferenceLine)
        self.assertEqual(reference.value, 0.0)

        anova = anova_plot_spec(
            AnovaResult(
                (
                    AnovaTest("age", ("age",), 5.2, "chi-square", 1, None, 0.02),
                    AnovaTest(
                        "treatment", ("treatment",), 2.1, "chi-square", 1, None, 0.15
                    ),
                )
            )
        )
        self.assertEqual(anova.kind, "anova")
        terms = anova.layers[0]
        self.assertIsInstance(terms, BarLayer)
        assert isinstance(terms, BarLayer)
        self.assertEqual(terms.categories, ("age", "treatment"))

    def test_probability_and_survival_validation_and_calibration_adapters(self) -> None:
        probability = validate_probabilities(
            (0, 1, 0, 1, 0, 1, 1, 0),
            (0.1, 0.7, 0.4, 0.6, 0.55, 0.8, 0.35, 0.45),
            calibration_groups=4,
            thresholds=(0.4, 0.5, 0.6),
        )
        validation = validation_plot_spec(probability)
        calibration = calibration_plot_spec(probability)
        self.assertEqual(
            tuple(layer.layer_id for layer in validation.layers),
            ("sensitivity", "specificity", "accuracy"),
        )
        self.assertEqual(calibration.layers[1].layer_id, "groups")

        survival = validate_survival_predictions(
            (1, 2, 3, 4, 5, 6),
            (1, 0, 1, 0, 1, 1),
            (
                (0.75, 0.50, 0.25),
                (0.80, 0.58, 0.32),
                (0.70, 0.45, 0.20),
                (0.85, 0.65, 0.40),
                (0.90, 0.72, 0.48),
                (0.92, 0.78, 0.55),
            ),
            (2.5, 4.5, 5.5),
        )
        survival_validation = validation_plot_spec(survival)
        survival_calibration = calibration_plot_spec(survival)
        self.assertEqual(survival_validation.kind, "validation")
        self.assertGreater(len(survival_calibration.layers), 1)

    def test_survival_and_diagnostic_adapters(self) -> None:
        curves = SurvivalCurveResult(
            times=(0.0, 1.0, 2.0),
            strata=("low risk", "high risk"),
            survival=((1.0, 0.9, 0.75), (1.0, 0.7, 0.4)),
            linear_predictors=(0.0, 1.0),
        )
        survival = survival_plot_spec(curves)
        self.assertEqual(len(survival.layers), 2)
        self.assertTrue(all(isinstance(layer, LineLayer) for layer in survival.layers))
        for layer in survival.layers:
            assert isinstance(layer, LineLayer)
            self.assertEqual(layer.interpolation, "step")

        observations = (
            InfluenceObservation(0, 0.1, 0.2, 0.01, (0.0,), (0.0,), False),
            InfluenceObservation(1, 0.6, 2.2, 0.8, (0.5,), (1.2,), True),
        )
        influence = diagnostic_plot_spec(
            InfluenceResult("ols", ("x",), observations, 0.5, 0.4, 1.0)
        )
        self.assertEqual(
            tuple(layer.layer_id for layer in influence.layers),
            ("cook-distance", "influential"),
        )

        vif = diagnostic_plot_spec(
            (VarianceInflationFactor("x", 1.5), VarianceInflationFactor("z", 2.0))
        )
        self.assertEqual(vif.layers[0].layer_id, "vif")

    def test_corrected_validation_calibration_and_other_diagnostics(self) -> None:
        x = tuple(float(index) for index in range(12))
        features = tuple((value,) for value in x)
        response = tuple(
            1.0 + 0.5 * value + 0.1 * ((index % 3) - 1) for index, value in enumerate(x)
        )
        fitted = fit_ols(response, features, feature_names=("x",))
        plan = ResamplePlan.k_fold(12, folds=3, seed=7)
        corrected_validation = optimism_correct_validation(
            validate_model(fitted, response, features, plan)
        )
        corrected_calibration = optimism_correct_calibration(
            calibrate_model(
                fitted,
                response,
                features,
                plan,
                prediction_grid=(1.0, 3.0, 5.0),
            )
        )

        validation = validation_plot_spec(corrected_validation)
        calibration = calibration_plot_spec(corrected_calibration)
        self.assertEqual(validation.legend_order, ("apparent", "corrected"))
        self.assertEqual(calibration.legend_order, ("apparent", "corrected", "ideal"))

        robust = robustness_diagnostics(
            fitted,
            response,
            features,
            clusters=tuple(index // 2 for index in range(12)),
        )
        penalty = trace_penalty(
            fitted, response, features, (0.0, 0.5, 2.0), criterion="bic"
        )
        self.assertEqual(
            diagnostic_plot_spec(robust).legend_order,
            ("model-se", "robust-se"),
        )
        selected = diagnostic_plot_spec(penalty).annotations[0]
        assert isinstance(selected, ReferenceLine)
        self.assertEqual(selected.value, penalty.selected_penalty)

    def test_adapters_reject_missing_required_plot_context(self) -> None:
        predictions = PredictionResult(
            "response", "mean", 0.95, (1.0, 2.0), (0.1, 0.1), (0.8, 1.8), (1.2, 2.2)
        )
        with self.assertRaisesRegex(InputValidationError, "match prediction"):
            effect_plot_spec(predictions, (0.0,))


class SvgRendererTests(unittest.TestCase):
    def test_svg_is_deterministic_accessible_and_escapes_text(self) -> None:
        spec = PlotSpec(
            "safe-svg",
            "anova",
            "Terms < effects",
            "Bars comparing A & B without executable content.",
            AxisSpec("Term", scale="categorical"),
            AxisSpec("Statistic", scale="log"),
            (BarLayer("terms", ("A & B", "C < D"), (2.0, 8.0), label="Wald"),),
        )

        svg = render_svg(spec)
        root = ET.fromstring(svg)
        title = root.find(f"{SVG}title")
        description = root.find(f"{SVG}desc")
        assert title is not None and description is not None

        self.assertEqual(svg, render_svg(spec))
        self.assertEqual(root.attrib["role"], "img")
        self.assertEqual(title.text, "Terms < effects")
        self.assertEqual(description.text, spec.alt_text)
        self.assertNotIn("<script", svg.lower())
        self.assertIn("A &amp; B", svg)
        self.assertNotIn("nan", svg.lower())

    def test_renderer_covers_numeric_bands_intervals_steps_and_references(self) -> None:
        predictions = PredictionResult(
            "response", "mean", 0.95, (1.0, 2.0), (0.1, 0.1), (0.8, 1.8), (1.2, 2.2)
        )
        effect_svg = render_svg(effect_plot_spec(predictions, (0.0, 1.0)))
        self.assertIn("polygon", effect_svg)

        estimate = InferenceEstimate(
            "A - B", 0.4, 0.2, 2.0, "normal", None, 0.04, 0.01, 0.79
        )
        contrast_svg = render_svg(contrast_plot_spec((estimate,)))
        self.assertIn("No difference", contrast_svg)

        curve = SurvivalCurveResult((0.0, 1.0, 2.0), ("all",), ((1.0, 0.8, 0.6),), None)
        survival_svg = render_svg(survival_plot_spec(curve))
        self.assertIn('data-layer-id="curve-1"', survival_svg)

    def test_renderer_rejects_unbounded_dimensions(self) -> None:
        spec = PlotSpec(
            "size-check",
            "custom",
            "Size check",
            "A single bar.",
            AxisSpec("Category", scale="categorical"),
            AxisSpec("Value"),
            (BarLayer("bar", ("A",), (1.0,)),),
        )
        with self.assertRaisesRegex(InputValidationError, "width"):
            render_svg(spec, width=100)

    def test_renderer_handles_logit_axes_and_vertical_intervals(self) -> None:
        logit = PlotSpec(
            "logit-line",
            "custom",
            "Logit axis",
            "A line over a logit-scaled probability axis.",
            AxisSpec("Probability", scale="logit"),
            AxisSpec("Value"),
            (LineLayer("line", (0.1, 0.5, 0.9), (1.0, 2.0, 3.0)),),
            show_legend=False,
        )
        intervals = PlotSpec(
            "vertical-intervals",
            "contrast",
            "Vertical intervals",
            "Two vertical estimate intervals.",
            AxisSpec("Contrast", scale="categorical"),
            AxisSpec("Estimate"),
            (
                IntervalLayer(
                    "intervals",
                    ("A", "B"),
                    (0.2, 0.8),
                    (0.0, 0.5),
                    (0.4, 1.1),
                    orientation="vertical",
                ),
            ),
            show_legend=False,
        )

        self.assertNotIn("nan", render_svg(logit).lower())
        self.assertIn('data-layer-id="intervals"', render_svg(intervals))


if __name__ == "__main__":
    unittest.main()
