"""Optimism correction for retained model-validation resample pairs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import Literal, TypeAlias, cast

from holocron.exceptions import InputValidationError, NumericalError
from holocron.validation.models import (
    CalibrationScale,
    ModelCalibrationResult,
    ModelCalibrationSplit,
    ModelFamily,
    ModelValidationResult,
    ModelValidationSplit,
)
from holocron.validation.resampling import ResampleExecution

ValidationMetricName: TypeAlias = Literal[
    "r_squared",
    "mean_squared_error",
    "dxy",
    "brier_score",
    "calibration_intercept",
    "calibration_slope",
]

_OLS_METRICS: tuple[ValidationMetricName, ...] = (
    "r_squared",
    "mean_squared_error",
    "calibration_intercept",
    "calibration_slope",
)
_BINARY_METRICS: tuple[ValidationMetricName, ...] = (
    "dxy",
    "brier_score",
    "calibration_intercept",
    "calibration_slope",
)


def _optional_finite(value: object, *, name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise InputValidationError(f"{name} must be finite or None")
    try:
        normalized = float(cast(float, value))
    except (TypeError, ValueError) as error:
        raise InputValidationError(f"{name} must be finite or None") from error
    if not math.isfinite(normalized):
        raise InputValidationError(f"{name} must be finite or None")
    return normalized


def _finite_tuple(values: object, *, name: str) -> tuple[float, ...]:
    if not isinstance(values, tuple):
        raise InputValidationError(f"{name} must be a tuple")
    normalized = tuple(
        _optional_finite(value, name=name) for value in cast(tuple[object, ...], values)
    )
    if any(value is None for value in normalized):
        raise InputValidationError(f"{name} must contain finite values")
    return tuple(cast(float, value) for value in normalized)


@dataclass(frozen=True, slots=True)
class OptimismCorrectedMetric:
    """One apparent, resampled-optimism, and corrected performance metric."""

    name: ValidationMetricName
    apparent: float | None
    mean_training: float | None
    mean_assessment: float | None
    optimism: float | None
    corrected: float | None
    contributing_resamples: int

    def __post_init__(self) -> None:
        if self.name not in {*_OLS_METRICS, *_BINARY_METRICS}:
            raise InputValidationError("unsupported optimism-corrected metric name")
        for name in (
            "apparent",
            "mean_training",
            "mean_assessment",
            "optimism",
            "corrected",
        ):
            object.__setattr__(
                self,
                name,
                _optional_finite(getattr(self, name), name=name),
            )
        raw_count = cast(object, self.contributing_resamples)
        if (
            isinstance(raw_count, bool)
            or not isinstance(raw_count, Integral)
            or self.contributing_resamples < 0
        ):
            raise InputValidationError(
                "contributing_resamples must be a non-negative integer"
            )
        aggregates = (
            self.mean_training,
            self.mean_assessment,
            self.optimism,
        )
        if self.contributing_resamples == 0:
            if any(value is not None for value in (*aggregates, self.corrected)):
                raise InputValidationError(
                    "a metric without contributing resamples must be undefined"
                )
            return
        if any(value is None for value in aggregates):
            raise InputValidationError(
                "resampled metric aggregates must be jointly defined"
            )
        assert self.mean_training is not None
        assert self.mean_assessment is not None
        assert self.optimism is not None
        if not math.isclose(
            self.optimism,
            self.mean_training - self.mean_assessment,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise InputValidationError("optimism must equal training minus assessment")
        if self.apparent is None:
            if self.corrected is not None:
                raise InputValidationError(
                    "corrected metric requires an apparent estimate"
                )
        elif self.corrected is None or not math.isclose(
            self.corrected,
            self.apparent - self.optimism,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise InputValidationError(
                "corrected metric must equal apparent minus optimism"
            )


@dataclass(frozen=True, slots=True)
class OptimismCorrectedValidationResult:
    """Metric-wise optimism correction with the exact source execution retained."""

    model_family: ModelFamily
    metrics: tuple[OptimismCorrectedMetric, ...]
    resamples: ResampleExecution[object]

    def __post_init__(self) -> None:
        expected = _OLS_METRICS if self.model_family == "ols" else _BINARY_METRICS
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported optimism-correction model_family")
        if (
            not isinstance(cast(object, self.metrics), tuple)
            or any(
                not isinstance(cast(object, metric), OptimismCorrectedMetric)
                for metric in self.metrics
            )
            or tuple(metric.name for metric in self.metrics) != expected
        ):
            raise InputValidationError(
                "optimism-corrected metrics do not match model_family"
            )
        if not isinstance(cast(object, self.resamples), ResampleExecution):
            raise InputValidationError("resamples must be a ResampleExecution")
        if not self.resamples.successes or any(
            not isinstance(success.value, ModelValidationSplit)
            for success in self.resamples.successes
        ):
            raise InputValidationError(
                "resamples must retain successful model-validation pairs"
            )
        if any(
            metric.contributing_resamples > len(self.resamples.successes)
            for metric in self.metrics
        ):
            raise InputValidationError(
                "metric contributors exceed successful resamples"
            )

    @property
    def status(self) -> Literal["complete", "partial", "failed"]:
        """Return the source execution status without hiding failed refits."""
        return self.resamples.status

    @property
    def failure_rate(self) -> float:
        """Return the source execution failure rate."""
        return self.resamples.failure_rate

    @property
    def successful_resamples(self) -> int:
        """Return the number of resamples contributing any result."""
        return len(self.resamples.successes)

    def metric(self, name: ValidationMetricName) -> OptimismCorrectedMetric:
        """Return one named metric or fail for a metric outside this family."""
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise InputValidationError(f"metric {name!r} is unavailable for model_family")


@dataclass(frozen=True, slots=True)
class OptimismCorrectedCalibrationResult:
    """Pointwise optimism-corrected parametric calibration curve."""

    model_family: ModelFamily
    scale: CalibrationScale
    prediction_grid: tuple[float, ...]
    apparent_curve: tuple[float, ...]
    mean_training_curve: tuple[float, ...]
    mean_assessment_curve: tuple[float, ...]
    optimism_curve: tuple[float, ...]
    corrected_curve: tuple[float, ...]
    resamples: ResampleExecution[object]

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported calibration model_family")
        expected_scale = "response" if self.model_family == "ols" else "probability"
        if self.scale != expected_scale:
            raise InputValidationError("calibration scale does not match model_family")
        grid = _finite_tuple(self.prediction_grid, name="prediction_grid")
        if len(grid) < 2 or any(
            left >= right for left, right in zip(grid, grid[1:], strict=False)
        ):
            raise InputValidationError("prediction_grid must be strictly increasing")
        object.__setattr__(self, "prediction_grid", grid)
        curves = (
            "apparent_curve",
            "mean_training_curve",
            "mean_assessment_curve",
            "optimism_curve",
            "corrected_curve",
        )
        for name in curves:
            curve = _finite_tuple(getattr(self, name), name=name)
            if len(curve) != len(grid):
                raise InputValidationError(
                    "optimism-corrected curves must match prediction_grid"
                )
            object.__setattr__(self, name, curve)
        if self.scale == "probability":
            bounded_curves = (
                self.apparent_curve,
                self.mean_training_curve,
                self.mean_assessment_curve,
            )
            if any(
                not 0.0 <= value <= 1.0 for curve in bounded_curves for value in curve
            ):
                raise InputValidationError(
                    "uncorrected probability calibration curves must be probabilities"
                )
        for index in range(len(grid)):
            if not math.isclose(
                self.optimism_curve[index],
                self.mean_training_curve[index] - self.mean_assessment_curve[index],
                rel_tol=1e-12,
                abs_tol=1e-12,
            ) or not math.isclose(
                self.corrected_curve[index],
                self.apparent_curve[index] - self.optimism_curve[index],
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise InputValidationError(
                    "calibration curves violate the optimism-correction identity"
                )
        if not isinstance(cast(object, self.resamples), ResampleExecution):
            raise InputValidationError("resamples must be a ResampleExecution")
        if not self.resamples.successes or any(
            not isinstance(success.value, ModelCalibrationSplit)
            for success in self.resamples.successes
        ):
            raise InputValidationError(
                "resamples must retain successful model-calibration pairs"
            )

    @property
    def status(self) -> Literal["complete", "partial", "failed"]:
        """Return the source execution status without hiding failed refits."""
        return self.resamples.status

    @property
    def failure_rate(self) -> float:
        """Return the source execution failure rate."""
        return self.resamples.failure_rate

    @property
    def contributing_resamples(self) -> int:
        """Return the number of successful curves in each pointwise mean."""
        return len(self.resamples.successes)


def _require_aggregatable(
    execution: ResampleExecution[object], *, allow_partial: bool
) -> None:
    if not isinstance(cast(object, allow_partial), bool):
        raise InputValidationError("allow_partial must be a boolean")
    if not execution.successes:
        raise NumericalError("optimism correction requires a successful resample")
    if execution.failures and not allow_partial:
        raise InputValidationError(
            "resample execution is partial; pass allow_partial=True to aggregate "
            "successful pairs explicitly"
        )


def optimism_correct_validation(
    result: ModelValidationResult,
    *,
    allow_partial: bool = False,
) -> OptimismCorrectedValidationResult:
    """Subtract the mean training-assessment gap from apparent performance.

    Metrics that are undefined on either side of a successful split are omitted
    from that metric's pairwise mean. The contributing count therefore belongs
    to each metric rather than to the result as a whole.
    """
    if not isinstance(cast(object, result), ModelValidationResult):
        raise InputValidationError("result must be a ModelValidationResult")
    execution = cast(ResampleExecution[object], result.resamples)
    _require_aggregatable(execution, allow_partial=allow_partial)
    names = _OLS_METRICS if result.model_family == "ols" else _BINARY_METRICS
    summaries: list[OptimismCorrectedMetric] = []
    for name in names:
        apparent = _optional_finite(getattr(result.apparent, name), name=name)
        pairs: list[tuple[float, float]] = []
        for success in result.resamples.successes:
            training = _optional_finite(
                getattr(success.value.training, name), name=name
            )
            assessment = _optional_finite(
                getattr(success.value.assessment, name), name=name
            )
            if training is not None and assessment is not None:
                pairs.append((training, assessment))
        if not pairs:
            summaries.append(
                OptimismCorrectedMetric(
                    name=name,
                    apparent=apparent,
                    mean_training=None,
                    mean_assessment=None,
                    optimism=None,
                    corrected=None,
                    contributing_resamples=0,
                )
            )
            continue
        count = len(pairs)
        mean_training = math.fsum(pair[0] for pair in pairs) / count
        mean_assessment = math.fsum(pair[1] for pair in pairs) / count
        optimism = mean_training - mean_assessment
        summaries.append(
            OptimismCorrectedMetric(
                name=name,
                apparent=apparent,
                mean_training=mean_training,
                mean_assessment=mean_assessment,
                optimism=optimism,
                corrected=None if apparent is None else apparent - optimism,
                contributing_resamples=count,
            )
        )
    return OptimismCorrectedValidationResult(
        model_family=result.model_family,
        metrics=tuple(summaries),
        resamples=execution,
    )


def optimism_correct_calibration(
    result: ModelCalibrationResult,
    *,
    allow_partial: bool = False,
) -> OptimismCorrectedCalibrationResult:
    """Correct a parametric calibration curve pointwise for mean optimism."""
    if not isinstance(cast(object, result), ModelCalibrationResult):
        raise InputValidationError("result must be a ModelCalibrationResult")
    execution = cast(ResampleExecution[object], result.resamples)
    _require_aggregatable(execution, allow_partial=allow_partial)
    training_curves = tuple(
        success.value.training.predict(result.prediction_grid, scale=result.scale)
        for success in result.resamples.successes
    )
    assessment_curves = tuple(
        success.value.assessment.predict(result.prediction_grid, scale=result.scale)
        for success in result.resamples.successes
    )
    count = len(training_curves)
    mean_training = tuple(
        math.fsum(curve[index] for curve in training_curves) / count
        for index in range(len(result.prediction_grid))
    )
    mean_assessment = tuple(
        math.fsum(curve[index] for curve in assessment_curves) / count
        for index in range(len(result.prediction_grid))
    )
    optimism = tuple(
        training - assessment
        for training, assessment in zip(mean_training, mean_assessment, strict=True)
    )
    corrected = tuple(
        apparent - gap
        for apparent, gap in zip(result.apparent_curve, optimism, strict=True)
    )
    return OptimismCorrectedCalibrationResult(
        model_family=result.model_family,
        scale=result.scale,
        prediction_grid=result.prediction_grid,
        apparent_curve=result.apparent_curve,
        mean_training_curve=mean_training,
        mean_assessment_curve=mean_assessment,
        optimism_curve=optimism,
        corrected_curve=corrected,
        resamples=execution,
    )


__all__ = [
    "OptimismCorrectedCalibrationResult",
    "OptimismCorrectedMetric",
    "OptimismCorrectedValidationResult",
    "optimism_correct_calibration",
    "optimism_correct_validation",
]
