"""Typed adapters from statistical results to structured tables."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from holocron.exceptions import InputValidationError
from holocron.models.diagnostics import (
    InfluenceResult,
    PenaltyTraceResult,
    RobustnessDiagnostics,
    VarianceInflationFactor,
)
from holocron.models.postfit import AnovaResult, InferenceEstimate, ModelSummary
from holocron.models.survival_validation import SurvivalValidationResult
from holocron.reporting.specification import (
    ColumnKind,
    TableColumn,
    TableMetadata,
    TableRow,
    TableSpec,
)
from holocron.validation.optimism import OptimismCorrectedValidationResult
from holocron.validation.probability import ProbabilityValidationResult
from holocron.validation.reporting import ResampleReport


def _column(
    key: str,
    label: str,
    kind: ColumnKind = "number",
    *,
    digits: int = 3,
) -> TableColumn:
    if kind == "text":
        return TableColumn(key, label, "text", "left", 0)
    if kind == "integer":
        return TableColumn(key, label, "integer", "right", 0)
    return TableColumn(key, label, kind, "right", digits)


def _inference_columns() -> tuple[TableColumn, ...]:
    return (
        _column("term", "Term", "text"),
        _column("estimate", "Estimate"),
        _column("standard_error", "Std. error"),
        _column("statistic", "Statistic"),
        _column("distribution", "Distribution", "text"),
        _column("degrees_of_freedom", "df", "integer"),
        _column("p_value", "p", "p-value"),
        _column("lower", "Lower"),
        _column("upper", "Upper"),
    )


def _inference_rows(values: tuple[InferenceEstimate, ...]) -> tuple[TableRow, ...]:
    return tuple(
        TableRow(
            f"estimate-{index}",
            (
                value.name,
                value.estimate,
                value.standard_error,
                value.statistic,
                value.distribution,
                value.degrees_of_freedom,
                value.p_value,
                value.lower,
                value.upper,
            ),
        )
        for index, value in enumerate(values)
    )


def model_summary_table(
    summary: ModelSummary,
    *,
    table_id: str = "model-summary",
    title: str = "Model coefficient summary",
) -> TableSpec:
    """Adapt one supported model summary without recomputing inference."""
    if not isinstance(cast(object, summary), ModelSummary):
        raise InputValidationError("summary must be a ModelSummary")
    inference_columns = _inference_columns()
    likelihood_columns = (
        _column("log_likelihood", "Log likelihood"),
        _column("null_log_likelihood", "Null log likelihood"),
        _column("parameter_count", "Parameters", "integer"),
        _column("aic", "AIC"),
        _column("likelihood_ratio", "Likelihood ratio"),
        _column("likelihood_degrees_of_freedom", "LR df", "integer"),
        _column("likelihood_p_value", "LR p", "p-value"),
    )
    inference_rows = _inference_rows(summary.coefficients)
    likelihood = summary.likelihood
    return TableSpec(
        table_id,
        "model-summary",
        title,
        inference_columns + likelihood_columns,
        tuple(
            TableRow(
                row.row_id,
                row.values
                + (
                    (
                        likelihood.log_likelihood,
                        likelihood.null_log_likelihood,
                        likelihood.parameter_count,
                        likelihood.aic,
                        likelihood.likelihood_ratio,
                        likelihood.degrees_of_freedom,
                        likelihood.p_value,
                    )
                    if index == 0
                    else (None,) * len(likelihood_columns)
                ),
            )
            for index, row in enumerate(inference_rows)
        ),
        notes=(
            f"Intervals use confidence level {100.0 * summary.confidence_level:g}%.",
            "Model likelihood statistics appear once on the first coefficient row.",
        ),
        metadata=(
            TableMetadata("model_type", summary.model_type),
            TableMetadata("n_observations", str(summary.n_observations)),
            TableMetadata("rank", str(summary.rank)),
        ),
    )


def contrast_table(
    estimates: Iterable[InferenceEstimate],
    *,
    table_id: str = "contrasts",
    title: str = "Contrasts",
) -> TableSpec:
    """Adapt named inference estimates to a structured contrast table."""
    values = tuple(estimates)
    if not values or any(
        not isinstance(cast(object, value), InferenceEstimate) for value in values
    ):
        raise InputValidationError("estimates must contain InferenceEstimate values")
    return TableSpec(
        table_id, "contrast", title, _inference_columns(), _inference_rows(values)
    )


def anova_table(
    result: AnovaResult,
    *,
    table_id: str = "anova",
    title: str = "ANOVA term tests",
) -> TableSpec:
    """Adapt joint Wald tests in their declared formula-term order."""
    if not isinstance(cast(object, result), AnovaResult) or not result.tests:
        raise InputValidationError("result must contain ANOVA tests")
    return TableSpec(
        table_id,
        "anova",
        title,
        (
            _column("term", "Term", "text"),
            _column("coefficients", "Coefficients", "text"),
            _column("statistic", "Statistic"),
            _column("distribution", "Distribution", "text"),
            _column("degrees_of_freedom", "df", "integer"),
            _column("denominator_degrees_of_freedom", "Denominator df", "integer"),
            _column("p_value", "p", "p-value"),
        ),
        tuple(
            TableRow(
                f"term-{index}",
                (
                    test.term,
                    ", ".join(test.coefficient_names),
                    test.statistic,
                    test.distribution,
                    test.degrees_of_freedom,
                    test.denominator_degrees_of_freedom,
                    test.p_value,
                ),
            )
            for index, test in enumerate(result.tests)
        ),
    )


_PROBABILITY_METRICS = (
    "auc",
    "dxy",
    "brier_score",
    "scaled_brier_score",
    "log_loss",
    "null_log_loss",
    "nagelkerke_r_squared",
    "discrimination_index",
    "unreliability_index",
    "quality_index",
    "likelihood_ratio_chi_square",
    "likelihood_ratio_p_value",
    "unreliability_chi_square",
    "unreliability_p_value",
    "calibration_intercept",
    "calibration_slope",
    "maximum_absolute_calibration_error",
    "p90_absolute_calibration_error",
    "mean_absolute_calibration_error",
    "spiegelhalter_z",
    "spiegelhalter_p_value",
    "prevalence",
    "mean_prediction",
    "calibration_in_the_large",
)


def validation_table(
    result: (
        ProbabilityValidationResult
        | SurvivalValidationResult
        | OptimismCorrectedValidationResult
    ),
    *,
    table_id: str = "validation",
    title: str = "Validation results",
) -> TableSpec:
    """Adapt probability, survival, or optimism-corrected validation results."""
    if not isinstance(
        cast(object, result),
        (
            ProbabilityValidationResult,
            SurvivalValidationResult,
            OptimismCorrectedValidationResult,
        ),
    ):
        raise InputValidationError("unsupported validation result type")
    if isinstance(result, ProbabilityValidationResult):
        p_values = {
            "likelihood_ratio_p_value",
            "unreliability_p_value",
            "spiegelhalter_p_value",
        }
        return TableSpec(
            table_id,
            "validation",
            title,
            (
                _column("metric", "Metric", "text"),
                _column("value", "Value"),
                _column("p_value", "p", "p-value"),
            ),
            tuple(
                TableRow(
                    f"metric-{index}",
                    (
                        name.replace("_", " "),
                        None if name in p_values else getattr(result, name),
                        getattr(result, name) if name in p_values else None,
                    ),
                )
                for index, name in enumerate(_PROBABILITY_METRICS)
            ),
            metadata=(
                TableMetadata("n_observations", str(result.n_observations)),
                TableMetadata("total_weight", f"{result.total_weight:.17g}"),
            ),
        )
    if isinstance(result, SurvivalValidationResult):
        return TableSpec(
            table_id,
            "validation",
            title,
            (
                _column("horizon", "Horizon"),
                _column("brier_score", "Brier score"),
                _column("auc", "AUC", "probability"),
                _column("dxy", "Dxy"),
                _column("observed_survival", "Observed survival", "probability"),
                _column("predicted_survival", "Mean predicted survival", "probability"),
                _column("calibration_error", "Calibration error"),
                _column("censoring_survival", "Censoring survival", "probability"),
                _column("cases", "Cases", "integer"),
                _column("controls", "Controls", "integer"),
                _column("integrated_brier_score", "Integrated Brier score"),
                _column("integrated_auc", "Integrated AUC", "probability"),
                _column(
                    "integrated_calibration_error",
                    "Integrated absolute calibration error",
                    "probability",
                ),
            ),
            tuple(
                TableRow(
                    f"horizon-{index}",
                    (
                        horizon,
                        result.brier_scores[index],
                        result.aucs[index],
                        result.dxy[index],
                        result.observed_survival[index],
                        result.mean_predicted_survival[index],
                        result.calibration_errors[index],
                        result.censoring_survival[index],
                        result.case_counts[index],
                        result.control_counts[index],
                        result.integrated_brier_score if index == 0 else None,
                        result.integrated_auc if index == 0 else None,
                        (
                            result.integrated_absolute_calibration_error
                            if index == 0
                            else None
                        ),
                    ),
                )
                for index, horizon in enumerate(result.horizons)
            ),
            notes=(
                "Integrated metrics appear once on the first horizon row; "
                "null means unavailable.",
            ),
            metadata=(
                TableMetadata("n_observations", str(result.n_observations)),
                TableMetadata("total_weight", f"{result.total_weight:.17g}"),
            ),
        )
    return TableSpec(
        table_id,
        "validation",
        title,
        (
            _column("metric", "Metric", "text"),
            _column("apparent", "Apparent"),
            _column("mean_training", "Mean training"),
            _column("mean_assessment", "Mean assessment"),
            _column("optimism", "Optimism"),
            _column("corrected", "Corrected"),
            _column("contributors", "Contributors", "integer"),
        ),
        tuple(
            TableRow(
                f"metric-{index}",
                (
                    metric.name.replace("_", " "),
                    metric.apparent,
                    metric.mean_training,
                    metric.mean_assessment,
                    metric.optimism,
                    metric.corrected,
                    metric.contributing_resamples,
                ),
            )
            for index, metric in enumerate(result.metrics)
        ),
        metadata=(
            TableMetadata("model_family", result.model_family),
            TableMetadata("resample_status", result.status),
            TableMetadata("failure_rate", f"{result.failure_rate:.17g}"),
        ),
    )


def resample_report_table(
    report: ResampleReport,
    *,
    table_id: str = "resample-report",
    title: str = "Resample execution",
) -> TableSpec:
    """Adapt exact resample counts and per-metric coverage to a table."""
    if not isinstance(cast(object, report), ResampleReport):
        raise InputValidationError("report must be a ResampleReport")
    rows = tuple(
        TableRow(
            f"metric-{index}",
            (
                metric.metric_name,
                metric.contributing_resamples,
                metric.omitted_successes,
                metric.planned_coverage,
                metric.successful_coverage,
            ),
        )
        for index, metric in enumerate(report.metric_coverage)
    )
    if not rows:
        rows = (
            TableRow("execution", ("(no metric coverage)", None, None, None, None)),
        )
    notes = tuple(
        f"{reason.exception_type}: {reason.message} ({reason.count} failures)"
        for reason in report.failure_reasons
    )
    return TableSpec(
        table_id,
        "resampling",
        title,
        (
            _column("metric", "Metric", "text"),
            _column("contributors", "Contributors", "integer"),
            _column("omitted_successes", "Omitted successes", "integer"),
            _column("planned_coverage", "Planned coverage", "probability"),
            _column("successful_coverage", "Successful coverage", "probability"),
        ),
        rows,
        notes=notes,
        metadata=(
            TableMetadata("plan_fingerprint", report.plan_fingerprint),
            TableMetadata("status", report.status),
            TableMetadata("aggregation_policy", report.aggregation_policy),
            TableMetadata(
                "aggregation_permitted", str(report.aggregation_permitted).lower()
            ),
            TableMetadata("planned_resamples", str(report.planned_resamples)),
            TableMetadata("successful_resamples", str(report.successful_resamples)),
            TableMetadata("failed_resamples", str(report.failed_resamples)),
            TableMetadata("failure_rate", f"{report.failure_rate:.17g}"),
        ),
    )


def diagnostic_table(
    result: (
        InfluenceResult
        | RobustnessDiagnostics
        | PenaltyTraceResult
        | Iterable[VarianceInflationFactor]
    ),
    *,
    table_id: str = "diagnostics",
    title: str = "Model diagnostics",
) -> TableSpec:
    """Adapt supported influence, robustness, penalty, or VIF diagnostics."""
    if isinstance(result, InfluenceResult):
        return TableSpec(
            table_id,
            "diagnostic",
            title,
            (
                _column("row", "Row", "integer"),
                _column("leverage", "Leverage"),
                _column("standardized_residual", "Standardized residual"),
                _column("cooks_distance", "Cook distance"),
                _column("influential", "Influential", "text"),
            ),
            tuple(
                TableRow(
                    f"observation-{value.row_index}",
                    (
                        value.row_index,
                        value.leverage,
                        value.standardized_residual,
                        value.cooks_distance,
                        "yes" if value.influential else "no",
                    ),
                )
                for value in result.observations
            ),
            metadata=(TableMetadata("model_family", result.model_family),),
        )
    if isinstance(result, RobustnessDiagnostics):
        return TableSpec(
            table_id,
            "diagnostic",
            title,
            (
                _column("coefficient", "Coefficient", "text"),
                _column("estimate", "Estimate"),
                _column("model_se", "Model SE"),
                _column("robust_se", "Robust SE"),
                _column("ratio", "Robust/model ratio"),
            ),
            tuple(
                TableRow(
                    f"coefficient-{index}",
                    (
                        value.coefficient_name,
                        value.coefficient,
                        value.model_standard_error,
                        value.robust_standard_error,
                        value.robust_to_model_ratio,
                    ),
                )
                for index, value in enumerate(result.coefficients)
            ),
        )
    if isinstance(result, PenaltyTraceResult):
        return TableSpec(
            table_id,
            "diagnostic",
            title,
            (
                _column("penalty", "Penalty"),
                _column("effective_df", "Effective df"),
                _column("deviance", "Deviance"),
                _column("aic", "AIC"),
                _column("bic", "BIC"),
                _column("selected", "Selected", "text"),
            ),
            tuple(
                TableRow(
                    f"penalty-{index}",
                    (
                        point.penalty,
                        point.effective_degrees_of_freedom,
                        point.deviance,
                        point.aic,
                        point.bic,
                        "yes" if point.penalty == result.selected_penalty else "no",
                    ),
                )
                for index, point in enumerate(result.points)
            ),
            metadata=(
                TableMetadata("model_family", result.model_family),
                TableMetadata("criterion", result.criterion),
            ),
        )
    values = tuple(result)
    if not values or any(
        not isinstance(cast(object, value), VarianceInflationFactor) for value in values
    ):
        raise InputValidationError("unsupported diagnostic result type")
    return TableSpec(
        table_id,
        "diagnostic",
        title,
        (_column("coefficient", "Coefficient", "text"), _column("vif", "VIF")),
        tuple(
            TableRow(f"coefficient-{index}", (value.coefficient_name, value.value))
            for index, value in enumerate(values)
        ),
    )


__all__ = [
    "anova_table",
    "contrast_table",
    "diagnostic_table",
    "model_summary_table",
    "resample_report_table",
    "validation_table",
]
