"""Typed adapters from statistical results to backend-neutral plot data."""

from __future__ import annotations

import math
from collections.abc import Iterable
from numbers import Real
from typing import cast

from holocron.exceptions import InputValidationError
from holocron.graphics.specification import (
    AxisSpec,
    BandLayer,
    BarLayer,
    IntervalLayer,
    LineLayer,
    PlotMetadata,
    PlotSpec,
    PointLayer,
    ReferenceLine,
)
from holocron.models.diagnostics import (
    InfluenceResult,
    PenaltyTraceResult,
    RobustnessDiagnostics,
    VarianceInflationFactor,
)
from holocron.models.postfit import AnovaResult, InferenceEstimate, PredictionResult
from holocron.models.survival import SurvivalCurveResult
from holocron.models.survival_validation import SurvivalValidationResult
from holocron.validation.models import ModelCalibrationResult
from holocron.validation.optimism import (
    OptimismCorrectedCalibrationResult,
    OptimismCorrectedValidationResult,
)
from holocron.validation.probability import ProbabilityValidationResult


def _values(values: Iterable[float], *, name: str) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise InputValidationError(f"{name} must contain finite numbers")
        normalized = float(value)
        if not math.isfinite(normalized):
            raise InputValidationError(f"{name} must contain finite numbers")
        result.append(normalized)
    if not result:
        raise InputValidationError(f"{name} must not be empty")
    return tuple(result)


def _increasing(values: tuple[float, ...], *, name: str) -> None:
    if any(left >= right for left, right in zip(values, values[1:], strict=False)):
        raise InputValidationError(f"{name} must be strictly increasing")


def effect_plot_spec(
    predictions: PredictionResult,
    predictor_values: Iterable[float],
    *,
    predictor_label: str = "Predictor",
    response_label: str = "Predicted value",
    plot_id: str = "effect",
    title: str = "Adjusted effect",
) -> PlotSpec:
    """Adapt ordered predictions and their explicit predictor grid to an effect plot."""
    if not isinstance(cast(object, predictions), PredictionResult):
        raise InputValidationError("predictions must be a PredictionResult")
    x = _values(predictor_values, name="predictor_values")
    _increasing(x, name="predictor_values")
    if len(x) != len(predictions.values):
        raise InputValidationError("predictor_values must match prediction rows")
    level = f"{100.0 * predictions.confidence_level:g}%"
    return PlotSpec(
        plot_id=plot_id,
        kind="effect",
        title=title,
        alt_text=(
            f"Adjusted {response_label.lower()} across {predictor_label.lower()}, "
            f"with a {level} {predictions.interval} confidence band."
        ),
        x_axis=AxisSpec(predictor_label),
        y_axis=AxisSpec(response_label),
        layers=(
            BandLayer(
                "confidence-interval",
                x,
                predictions.lower,
                predictions.upper,
                label=f"{level} confidence interval",
            ),
            LineLayer("estimate", x, predictions.values, label="Estimate"),
        ),
        metadata=(
            PlotMetadata("prediction_scale", predictions.scale),
            PlotMetadata("interval", predictions.interval),
            PlotMetadata("confidence_level", f"{predictions.confidence_level:.17g}"),
        ),
        legend_order=("estimate", "confidence-interval"),
    )


def contrast_plot_spec(
    estimates: Iterable[InferenceEstimate],
    *,
    plot_id: str = "contrasts",
    title: str = "Contrasts",
) -> PlotSpec:
    """Adapt named estimates to a horizontal confidence-interval plot."""
    values = tuple(estimates)
    if not values or any(
        not isinstance(cast(object, value), InferenceEstimate) for value in values
    ):
        raise InputValidationError("estimates must contain InferenceEstimate values")
    categories = tuple(value.name for value in values)
    level = "confidence"
    return PlotSpec(
        plot_id=plot_id,
        kind="contrast",
        title=title,
        alt_text=(
            f"{len(values)} named contrast estimates with {level} intervals and a "
            "zero-difference reference line."
        ),
        x_axis=AxisSpec("Contrast estimate"),
        y_axis=AxisSpec("Contrast", scale="categorical"),
        layers=(
            IntervalLayer(
                "contrasts",
                categories,
                tuple(value.estimate for value in values),
                tuple(value.lower for value in values),
                tuple(value.upper for value in values),
                label="Estimate and confidence interval",
            ),
        ),
        annotations=(ReferenceLine("x", 0.0, "No difference"),),
        show_legend=False,
    )


def anova_plot_spec(
    result: AnovaResult,
    *,
    plot_id: str = "anova",
    title: str = "ANOVA term statistics",
) -> PlotSpec:
    """Adapt joint Wald tests to a horizontal term-statistic plot."""
    if not isinstance(cast(object, result), AnovaResult) or not result.tests:
        raise InputValidationError("result must contain ANOVA tests")
    distributions = {test.distribution for test in result.tests}
    label = "Wald statistic" if len(distributions) > 1 else next(iter(distributions))
    return PlotSpec(
        plot_id=plot_id,
        kind="anova",
        title=title,
        alt_text=f"Wald statistics for {len(result.tests)} model terms.",
        x_axis=AxisSpec("Statistic"),
        y_axis=AxisSpec("Term", scale="categorical"),
        layers=(
            BarLayer(
                "term-statistics",
                tuple(test.term for test in result.tests),
                tuple(test.statistic for test in result.tests),
                label=label,
                orientation="horizontal",
            ),
        ),
        show_legend=False,
    )


def validation_plot_spec(
    result: (
        OptimismCorrectedValidationResult
        | ProbabilityValidationResult
        | SurvivalValidationResult
    ),
    *,
    plot_id: str = "validation",
    title: str = "Validation performance",
) -> PlotSpec:
    """Adapt corrected, probability, or survival validation measurements."""
    if not isinstance(
        cast(object, result),
        (
            OptimismCorrectedValidationResult,
            ProbabilityValidationResult,
            SurvivalValidationResult,
        ),
    ):
        raise InputValidationError("unsupported validation result type")
    if isinstance(result, OptimismCorrectedValidationResult):
        usable = tuple(
            metric
            for metric in result.metrics
            if metric.apparent is not None and metric.corrected is not None
        )
        if not usable:
            raise InputValidationError("validation result has no plottable metrics")
        categories = tuple(metric.name.replace("_", " ") for metric in usable)
        return PlotSpec(
            plot_id=plot_id,
            kind="validation",
            title=title,
            subtitle=f"{result.model_family}; resampling status: {result.status}",
            alt_text=(
                f"Apparent and optimism-corrected values for {len(usable)} "
                f"{result.model_family} validation metrics."
            ),
            x_axis=AxisSpec("Metric value"),
            y_axis=AxisSpec("Metric", scale="categorical"),
            layers=(
                BarLayer(
                    "apparent",
                    categories,
                    tuple(cast(float, metric.apparent) for metric in usable),
                    label="Apparent",
                    role="estimate",
                    orientation="horizontal",
                ),
                BarLayer(
                    "corrected",
                    categories,
                    tuple(cast(float, metric.corrected) for metric in usable),
                    label="Optimism-corrected",
                    role="comparison",
                    orientation="horizontal",
                ),
            ),
            metadata=(
                PlotMetadata("model_family", result.model_family),
                PlotMetadata("resample_status", result.status),
                PlotMetadata("failure_rate", f"{result.failure_rate:.17g}"),
            ),
            legend_order=("apparent", "corrected"),
        )
    if isinstance(result, ProbabilityValidationResult):
        if result.threshold_metrics:
            thresholds = tuple(item.threshold for item in result.threshold_metrics)
            return PlotSpec(
                plot_id=plot_id,
                kind="validation",
                title=title,
                subtitle="Binary probability thresholds",
                alt_text=(
                    "Sensitivity, specificity, and accuracy across declared "
                    "probability thresholds."
                ),
                x_axis=AxisSpec("Probability threshold", scale="probability"),
                y_axis=AxisSpec("Metric", scale="probability", limits=(0.0, 1.0)),
                layers=(
                    LineLayer(
                        "sensitivity",
                        thresholds,
                        tuple(item.sensitivity for item in result.threshold_metrics),
                        label="Sensitivity",
                    ),
                    LineLayer(
                        "specificity",
                        thresholds,
                        tuple(item.specificity for item in result.threshold_metrics),
                        label="Specificity",
                        role="comparison",
                    ),
                    LineLayer(
                        "accuracy",
                        thresholds,
                        tuple(item.accuracy for item in result.threshold_metrics),
                        label="Accuracy",
                        role="observed",
                    ),
                ),
                legend_order=("sensitivity", "specificity", "accuracy"),
            )
        categories = ("AUC", "Brier score", "Scaled Brier score")
        return PlotSpec(
            plot_id=plot_id,
            kind="validation",
            title=title,
            subtitle="Binary probability validation",
            alt_text="AUC, Brier score, and scaled Brier score summary values.",
            x_axis=AxisSpec("Metric value"),
            y_axis=AxisSpec("Metric", scale="categorical"),
            layers=(
                BarLayer(
                    "probability-metrics",
                    categories,
                    (result.auc, result.brier_score, result.scaled_brier_score),
                    orientation="horizontal",
                ),
            ),
            show_legend=False,
        )
    else:
        layers: list[LineLayer] = [
            LineLayer(
                "brier-score",
                result.horizons,
                result.brier_scores,
                label="Brier score",
            )
        ]
        defined_auc = tuple(
            (horizon, auc)
            for horizon, auc in zip(result.horizons, result.aucs, strict=True)
            if auc is not None
        )
        if defined_auc:
            layers.append(
                LineLayer(
                    "auc",
                    tuple(item[0] for item in defined_auc),
                    tuple(item[1] for item in defined_auc),
                    label="AUC",
                    role="comparison",
                )
            )
        return PlotSpec(
            plot_id=plot_id,
            kind="validation",
            title=title,
            subtitle="Right-censored survival validation",
            alt_text="Brier score and available AUC values across time horizons.",
            x_axis=AxisSpec("Time horizon"),
            y_axis=AxisSpec("Metric", scale="probability", limits=(0.0, 1.0)),
            layers=tuple(layers),
            legend_order=tuple(layer.layer_id for layer in layers),
        )
    raise InputValidationError("unsupported validation result type")


def calibration_plot_spec(
    result: (
        ModelCalibrationResult
        | OptimismCorrectedCalibrationResult
        | ProbabilityValidationResult
        | SurvivalValidationResult
    ),
    *,
    plot_id: str = "calibration",
    title: str = "Calibration",
) -> PlotSpec:
    """Adapt model, corrected, probability, or survival calibration results."""
    if not isinstance(
        cast(object, result),
        (
            ModelCalibrationResult,
            OptimismCorrectedCalibrationResult,
            ProbabilityValidationResult,
            SurvivalValidationResult,
        ),
    ):
        raise InputValidationError("unsupported calibration result type")
    if isinstance(result, ModelCalibrationResult):
        grid = result.prediction_grid
        model_layers = (
            LineLayer("ideal", grid, grid, label="Ideal", role="reference"),
            LineLayer(
                "apparent",
                grid,
                result.apparent_curve,
                label="Apparent",
            ),
        )
        scale = "probability" if result.scale == "probability" else "linear"
        return PlotSpec(
            plot_id=plot_id,
            kind="calibration",
            title=title,
            alt_text="Apparent model calibration curve compared with the ideal line.",
            x_axis=AxisSpec("Predicted value", scale=scale),
            y_axis=AxisSpec("Observed value", scale=scale),
            layers=model_layers,
            metadata=(PlotMetadata("resample_status", result.status),),
            legend_order=("apparent", "ideal"),
        )
    if isinstance(result, OptimismCorrectedCalibrationResult):
        grid = result.prediction_grid
        scale = "probability" if result.scale == "probability" else "linear"
        return PlotSpec(
            plot_id=plot_id,
            kind="calibration",
            title=title,
            subtitle=f"Resampling status: {result.status}",
            alt_text=(
                "Apparent and optimism-corrected calibration curves compared "
                "with the ideal line."
            ),
            x_axis=AxisSpec("Predicted value", scale=scale),
            y_axis=AxisSpec("Observed value", scale=scale),
            layers=(
                LineLayer("ideal", grid, grid, label="Ideal", role="reference"),
                LineLayer("apparent", grid, result.apparent_curve, label="Apparent"),
                LineLayer(
                    "corrected",
                    grid,
                    result.corrected_curve,
                    label="Optimism-corrected",
                    role="comparison",
                ),
            ),
            metadata=(
                PlotMetadata("resample_status", result.status),
                PlotMetadata("failure_rate", f"{result.failure_rate:.17g}"),
            ),
            legend_order=("apparent", "corrected", "ideal"),
        )
    if isinstance(result, ProbabilityValidationResult):
        if not result.calibration_groups:
            raise InputValidationError("probability calibration groups are empty")
        x = tuple(group.mean_prediction for group in result.calibration_groups)
        observed = tuple(
            group.observed_frequency for group in result.calibration_groups
        )
        return PlotSpec(
            plot_id=plot_id,
            kind="calibration",
            title=title,
            subtitle="Grouped binary calibration",
            alt_text=(
                "Grouped observed event frequencies versus mean predicted "
                "probabilities, compared with ideal calibration."
            ),
            x_axis=AxisSpec("Mean predicted probability", scale="probability"),
            y_axis=AxisSpec(
                "Observed event frequency", scale="probability", limits=(0.0, 1.0)
            ),
            layers=(
                LineLayer(
                    "ideal",
                    (0.0, 1.0),
                    (0.0, 1.0),
                    label="Ideal",
                    role="reference",
                ),
                PointLayer("groups", x, observed, label="Calibration groups"),
            ),
            legend_order=("groups", "ideal"),
        )
    else:
        survival_layers: list[PointLayer | LineLayer] = [
            LineLayer(
                "ideal",
                (0.0, 1.0),
                (0.0, 1.0),
                label="Ideal",
                role="reference",
            )
        ]
        for index, groups in enumerate(result.calibration_groups):
            if groups:
                survival_layers.append(
                    PointLayer(
                        f"horizon-{index + 1}",
                        tuple(group.mean_predicted_survival for group in groups),
                        tuple(group.observed_survival for group in groups),
                        label=f"Horizon {result.horizons[index]:g}",
                        role="comparison",
                    )
                )
        if len(survival_layers) == 1:
            raise InputValidationError("survival calibration groups are empty")
        return PlotSpec(
            plot_id=plot_id,
            kind="calibration",
            title=title,
            subtitle="Grouped right-censored survival calibration",
            alt_text=(
                "Grouped observed survival versus mean predicted survival at "
                f"{len(survival_layers) - 1} time horizons."
            ),
            x_axis=AxisSpec("Mean predicted survival", scale="probability"),
            y_axis=AxisSpec("Observed survival", scale="probability"),
            layers=tuple(survival_layers),
            legend_order=tuple(layer.layer_id for layer in survival_layers[1:])
            + ("ideal",),
        )
    raise InputValidationError("unsupported calibration result type")


def survival_plot_spec(
    result: SurvivalCurveResult,
    *,
    plot_id: str = "survival",
    title: str = "Survival curves",
) -> PlotSpec:
    """Adapt one or more predicted survival curves to step-line layers."""
    if not isinstance(cast(object, result), SurvivalCurveResult):
        raise InputValidationError("result must be a SurvivalCurveResult")
    layers = tuple(
        LineLayer(
            f"curve-{index + 1}",
            result.times,
            curve,
            label=stratum,
            role="estimate" if index == 0 else "comparison",
            interpolation="step",
        )
        for index, (stratum, curve) in enumerate(
            zip(result.strata, result.survival, strict=True)
        )
    )
    return PlotSpec(
        plot_id=plot_id,
        kind="survival",
        title=title,
        alt_text=f"{len(layers)} predicted survival curves shown over time.",
        x_axis=AxisSpec("Time"),
        y_axis=AxisSpec("Survival probability", scale="probability", limits=(0.0, 1.0)),
        layers=layers,
        legend_order=tuple(layer.layer_id for layer in layers),
    )


DiagnosticResult = (
    InfluenceResult
    | RobustnessDiagnostics
    | PenaltyTraceResult
    | tuple[VarianceInflationFactor, ...]
)


def diagnostic_plot_spec(
    result: DiagnosticResult,
    *,
    plot_id: str = "diagnostic",
    title: str = "Model diagnostic",
) -> PlotSpec:
    """Adapt supported influence, robustness, penalty, or VIF diagnostics."""
    if not isinstance(
        cast(object, result),
        (InfluenceResult, RobustnessDiagnostics, PenaltyTraceResult, tuple),
    ):
        raise InputValidationError("unsupported diagnostic result type")
    if isinstance(result, InfluenceResult):
        all_points = result.observations
        layers: list[PointLayer] = [
            PointLayer(
                "cook-distance",
                tuple(float(item.row_index) for item in all_points),
                tuple(item.cooks_distance for item in all_points),
                label="Cook distance",
                role="diagnostic",
            )
        ]
        flagged = tuple(item for item in all_points if item.influential)
        if flagged:
            layers.append(
                PointLayer(
                    "influential",
                    tuple(float(item.row_index) for item in flagged),
                    tuple(item.cooks_distance for item in flagged),
                    label="Influential row",
                    role="comparison",
                )
            )
        return PlotSpec(
            plot_id=plot_id,
            kind="diagnostic",
            title=title,
            subtitle=f"{result.model_family} influence",
            alt_text=(
                "Cook distance by observation, with influential rows highlighted "
                "and the declared Cook-distance threshold shown."
            ),
            x_axis=AxisSpec("Observation index"),
            y_axis=AxisSpec("Cook distance"),
            layers=tuple(layers),
            annotations=(
                ReferenceLine(
                    "y", result.cooks_distance_threshold, "Cook-distance threshold"
                ),
            ),
            legend_order=tuple(layer.layer_id for layer in layers),
        )
    if isinstance(result, RobustnessDiagnostics):
        categories = tuple(item.coefficient_name for item in result.coefficients)
        return PlotSpec(
            plot_id=plot_id,
            kind="diagnostic",
            title=title,
            subtitle="Model-based and robust uncertainty",
            alt_text="Model-based and robust standard errors by coefficient.",
            x_axis=AxisSpec("Standard error"),
            y_axis=AxisSpec("Coefficient", scale="categorical"),
            layers=(
                BarLayer(
                    "model-se",
                    categories,
                    tuple(item.model_standard_error for item in result.coefficients),
                    label="Model-based",
                    orientation="horizontal",
                ),
                BarLayer(
                    "robust-se",
                    categories,
                    tuple(item.robust_standard_error for item in result.coefficients),
                    label="Robust",
                    role="comparison",
                    orientation="horizontal",
                ),
            ),
            legend_order=("model-se", "robust-se"),
        )
    if isinstance(result, PenaltyTraceResult):
        criterion = result.criterion.upper()
        return PlotSpec(
            plot_id=plot_id,
            kind="diagnostic",
            title=title,
            subtitle=f"{result.model_family} penalty trace",
            alt_text=(
                f"{criterion} over the declared penalty path, with the selected "
                "penalty marked."
            ),
            x_axis=AxisSpec("Penalty"),
            y_axis=AxisSpec(criterion),
            layers=(
                LineLayer(
                    "criterion",
                    tuple(point.penalty for point in result.points),
                    tuple(getattr(point, result.criterion) for point in result.points),
                    label=criterion,
                    role="diagnostic",
                ),
            ),
            annotations=(
                ReferenceLine("x", result.selected_penalty, "Selected penalty"),
            ),
            show_legend=False,
        )
    if result and all(
        isinstance(cast(object, item), VarianceInflationFactor) for item in result
    ):
        return PlotSpec(
            plot_id=plot_id,
            kind="diagnostic",
            title=title,
            subtitle="Variance inflation factors",
            alt_text=f"Variance inflation factors for {len(result)} coefficients.",
            x_axis=AxisSpec(
                "Variance inflation factor",
                limits=(1.0, max(1.0, max(item.value for item in result)) + 0.01),
            ),
            y_axis=AxisSpec("Coefficient", scale="categorical"),
            layers=(
                BarLayer(
                    "vif",
                    tuple(item.coefficient_name for item in result),
                    tuple(item.value for item in result),
                    orientation="horizontal",
                    role="diagnostic",
                ),
            ),
            show_legend=False,
        )
    raise InputValidationError("unsupported diagnostic result type")
