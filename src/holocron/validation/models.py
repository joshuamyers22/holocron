"""Model-specific validation and parametric calibration over exact plans."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, TypeAlias, cast

import numpy as np

from holocron.design import DesignMatrix
from holocron.exceptions import (
    InputValidationError,
    NumericalError,
    UnsupportedFeatureError,
)
from holocron.models.glm import fit_glm, fit_lrm
from holocron.models.linear import OlsResult, fit_ols
from holocron.models.logistic import BinaryLogisticResult
from holocron.validation.resampling import (
    FailurePolicy,
    ResampleExecution,
    ResamplePlan,
    ResampleSplit,
    run_resample_plan,
    take_rows,
)

ModelFamily: TypeAlias = Literal["ols", "binary-logistic"]
CalibrationScale: TypeAlias = Literal["response", "probability"]
SupportedModel: TypeAlias = OlsResult | BinaryLogisticResult
MAX_CALIBRATION_POINTS = 1_000


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise InputValidationError(f"{name} must be a finite number")
    try:
        normalized = float(cast(float, value))
    except (TypeError, ValueError) as error:
        raise InputValidationError(f"{name} must be a finite number") from error
    if not math.isfinite(normalized):
        raise InputValidationError(f"{name} must be a finite number")
    return normalized


def _optional_finite(value: object, *, name: str) -> float | None:
    return None if value is None else _finite(value, name=name)


@dataclass(frozen=True, slots=True)
class OlsValidationIndices:
    """OLS validation indices on one evaluation sample."""

    r_squared: float | None
    mean_squared_error: float
    calibration_intercept: float
    calibration_slope: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "r_squared",
            _optional_finite(self.r_squared, name="r_squared"),
        )
        for name in (
            "mean_squared_error",
            "calibration_intercept",
            "calibration_slope",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name=name))
        if self.mean_squared_error < 0.0:
            raise InputValidationError("mean_squared_error must be non-negative")


@dataclass(frozen=True, slots=True)
class BinaryValidationIndices:
    """Binary-logistic validation indices on one evaluation sample."""

    dxy: float | None
    brier_score: float
    calibration_intercept: float
    calibration_slope: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "dxy", _optional_finite(self.dxy, name="dxy"))
        for name in (
            "brier_score",
            "calibration_intercept",
            "calibration_slope",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name=name))
        if self.dxy is not None and not -1.0 <= self.dxy <= 1.0:
            raise InputValidationError("dxy must be between -1 and 1")
        if not 0.0 <= self.brier_score <= 1.0:
            raise InputValidationError("brier_score must be between 0 and 1")


ValidationIndices: TypeAlias = OlsValidationIndices | BinaryValidationIndices


@dataclass(frozen=True, slots=True)
class ModelValidationSplit:
    """Training and assessment indices from one freshly refitted model."""

    training: ValidationIndices
    assessment: ValidationIndices

    def __post_init__(self) -> None:
        supported = (OlsValidationIndices, BinaryValidationIndices)
        if not isinstance(cast(object, self.training), supported) or not isinstance(
            cast(object, self.assessment), supported
        ):
            raise InputValidationError(
                "validation split values must contain supported indices"
            )
        if type(self.training) is not type(self.assessment):
            raise InputValidationError(
                "training and assessment validation indices must share a model family"
            )


@dataclass(frozen=True, slots=True)
class ModelValidationResult:
    """Apparent and resampled model-specific validation measurements.

    This result intentionally retains each training/assessment pair. It does not
    average them or label their difference optimism-corrected; aggregation and
    optimism correction are a separate Phase 6 contract.
    """

    model_family: ModelFamily
    apparent: ValidationIndices
    resamples: ResampleExecution[ModelValidationSplit]

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported validation model_family")
        expected = (
            OlsValidationIndices
            if self.model_family == "ols"
            else BinaryValidationIndices
        )
        if not isinstance(cast(object, self.apparent), expected):
            raise InputValidationError("apparent indices do not match model_family")
        if not isinstance(cast(object, self.resamples), ResampleExecution) or any(
            not isinstance(cast(object, success.value), ModelValidationSplit)
            for success in self.resamples.successes
        ):
            raise InputValidationError(
                "resamples must contain model-validation split results"
            )
        if any(
            not isinstance(cast(object, success.value.training), expected)
            for success in self.resamples.successes
        ):
            raise InputValidationError("resample indices do not match model_family")

    @property
    def status(self) -> Literal["complete", "partial", "failed"]:
        """Return the exact execution status without hiding failed refits."""
        return self.resamples.status

    @property
    def failure_rate(self) -> float:
        """Return the proportion of planned refits that failed."""
        return self.resamples.failure_rate


@dataclass(frozen=True, slots=True)
class CalibrationEstimate:
    """Intercept and slope for one model-family recalibration fit."""

    intercept: float
    slope: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "intercept", _finite(self.intercept, name="intercept"))
        object.__setattr__(self, "slope", _finite(self.slope, name="slope"))

    def predict(
        self,
        values: Iterable[float],
        *,
        scale: CalibrationScale,
    ) -> tuple[float, ...]:
        """Evaluate the fitted recalibration relationship."""
        grid = tuple(_finite(value, name="calibration value") for value in values)
        if scale == "response":
            return tuple(self.intercept + self.slope * value for value in grid)
        if scale != "probability":
            raise InputValidationError("unsupported calibration scale")
        if any(not 0.0 < value < 1.0 for value in grid):
            raise InputValidationError(
                "probability calibration values must be strictly between 0 and 1"
            )
        linear = np.asarray(
            [
                self.intercept + self.slope * math.log(value / (1.0 - value))
                for value in grid
            ],
            dtype=np.float64,
        )
        output = np.empty_like(linear)
        positive = linear >= 0.0
        output[positive] = 1.0 / (1.0 + np.exp(-linear[positive]))
        exponential = np.exp(linear[~positive])
        output[~positive] = exponential / (1.0 + exponential)
        return tuple(float(value) for value in output)


@dataclass(frozen=True, slots=True)
class ModelCalibrationSplit:
    """Training and assessment recalibration from one fresh model fit."""

    training: CalibrationEstimate
    assessment: CalibrationEstimate

    def __post_init__(self) -> None:
        if not isinstance(
            cast(object, self.training), CalibrationEstimate
        ) or not isinstance(cast(object, self.assessment), CalibrationEstimate):
            raise InputValidationError(
                "calibration split values must be CalibrationEstimate instances"
            )


@dataclass(frozen=True, slots=True)
class ModelCalibrationResult:
    """Apparent curve and resampled calibration fits for a supported model."""

    model_family: ModelFamily
    scale: CalibrationScale
    prediction_grid: tuple[float, ...]
    apparent: CalibrationEstimate
    apparent_curve: tuple[float, ...]
    resamples: ResampleExecution[ModelCalibrationSplit]

    def __post_init__(self) -> None:
        expected_scale = "response" if self.model_family == "ols" else "probability"
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported calibration model_family")
        if self.scale != expected_scale:
            raise InputValidationError("calibration scale does not match model_family")
        if not isinstance(cast(object, self.apparent), CalibrationEstimate):
            raise InputValidationError("apparent must be a CalibrationEstimate")
        if not isinstance(cast(object, self.resamples), ResampleExecution) or any(
            not isinstance(cast(object, success.value), ModelCalibrationSplit)
            for success in self.resamples.successes
        ):
            raise InputValidationError(
                "resamples must contain model-calibration split results"
            )
        if (
            not isinstance(cast(object, self.prediction_grid), tuple)
            or not 2 <= len(self.prediction_grid) <= MAX_CALIBRATION_POINTS
        ):
            raise InputValidationError(
                f"prediction_grid must contain 2-{MAX_CALIBRATION_POINTS} values"
            )
        normalized = tuple(
            _finite(value, name="prediction_grid") for value in self.prediction_grid
        )
        if any(
            left >= right
            for left, right in zip(normalized, normalized[1:], strict=False)
        ):
            raise InputValidationError("prediction_grid must be strictly increasing")
        if self.scale == "probability" and any(
            not 0.0 < value < 1.0 for value in normalized
        ):
            raise InputValidationError(
                "probability prediction_grid must be strictly between 0 and 1"
            )
        object.__setattr__(self, "prediction_grid", normalized)
        if len(self.apparent_curve) != len(normalized):
            raise InputValidationError("apparent_curve must match prediction_grid")
        curve = tuple(
            _finite(value, name="apparent_curve") for value in self.apparent_curve
        )
        if self.scale == "probability" and any(
            not 0.0 <= value <= 1.0 for value in curve
        ):
            raise InputValidationError(
                "probability apparent_curve must be between 0 and 1"
            )
        object.__setattr__(self, "apparent_curve", curve)

    @property
    def status(self) -> Literal["complete", "partial", "failed"]:
        """Return the exact execution status without hiding failed refits."""
        return self.resamples.status

    @property
    def failure_rate(self) -> float:
        """Return the proportion of planned refits that failed."""
        return self.resamples.failure_rate


def _snapshot_inputs(
    model: SupportedModel,
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    plan: ResamplePlan,
    row_ids: Iterable[str] | None,
) -> tuple[tuple[float, ...], tuple[tuple[float, ...], ...]]:
    if not isinstance(cast(object, plan), ResamplePlan):
        raise InputValidationError("plan must be a ResamplePlan")
    y = tuple(_finite(value, name="response") for value in response)
    rows_source = features.rows if isinstance(features, DesignMatrix) else features
    try:
        rows = tuple(
            tuple(_finite(value, name="features") for value in row)
            for row in rows_source
        )
    except TypeError as error:
        raise InputValidationError("features must contain iterable rows") from error
    if len(y) != plan.observation_count or len(rows) != plan.observation_count:
        raise InputValidationError(
            "response and features must match the plan observation count"
        )
    if model.n_observations != plan.observation_count:
        raise InputValidationError(
            "fitted model observations must match the plan observation count"
        )
    if not rows or any(len(row) != model.n_features for row in rows):
        raise InputValidationError(
            "feature rows must match the fitted model feature count"
        )
    if row_ids is not None and tuple(row_ids) != plan.row_ids:
        raise InputValidationError("row_ids must match the exact plan row identity")
    if isinstance(features, DesignMatrix):
        if (
            model.design_fingerprint is not None
            and features.specification_fingerprint != model.design_fingerprint
        ):
            raise InputValidationError(
                "feature design fingerprint differs from the fitted model"
            )
        if features.include_intercept != model.includes_intercept:
            raise InputValidationError(
                "feature design intercept differs from the fitted model"
            )
    return y, rows


def _family(model: SupportedModel) -> ModelFamily:
    return "ols" if isinstance(model, OlsResult) else "binary-logistic"


def _feature_names(model: SupportedModel) -> tuple[str, ...]:
    return (
        model.coefficient_names[1:]
        if model.includes_intercept
        else model.coefficient_names
    )


def _fit_like(
    model: SupportedModel,
    response: tuple[float, ...],
    features: tuple[tuple[float, ...], ...],
    *,
    max_iterations: int,
    tolerance: float | None,
) -> SupportedModel:
    names = _feature_names(model)
    includes_intercept = model.includes_intercept
    fingerprint = model.design_fingerprint
    if isinstance(model, OlsResult):
        if tolerance is not None or max_iterations != 100:
            raise InputValidationError(
                "iterative controls do not apply to OLS validation"
            )
        return fit_ols(
            response,
            features,
            feature_names=names,
            include_intercept=includes_intercept,
            design_fingerprint=fingerprint,
        )
    normalized_tolerance = (
        (1e-10 if model.estimator == "lrm" else 1e-8)
        if tolerance is None
        else _finite(tolerance, name="tolerance")
    )
    if normalized_tolerance <= 0.0:
        raise InputValidationError("tolerance must be positive")
    if model.estimator == "lrm":
        return fit_lrm(
            response,
            features,
            feature_names=names,
            include_intercept=includes_intercept,
            design_fingerprint=fingerprint,
            max_iterations=max_iterations,
            tolerance=normalized_tolerance,
        )
    return fit_glm(
        response,
        features,
        family="binomial",
        feature_names=names,
        include_intercept=includes_intercept,
        design_fingerprint=fingerprint,
        max_iterations=max_iterations,
        tolerance=normalized_tolerance,
    )


def _linear_calibration(
    response: tuple[float, ...], predictions: tuple[float, ...]
) -> CalibrationEstimate:
    if len(response) < 2:
        raise NumericalError("linear calibration requires at least two observations")
    design = np.empty((len(predictions), 2), dtype=np.float64)
    design[:, 0] = 1.0
    design[:, 1] = np.asarray(predictions, dtype=np.float64)
    if int(np.linalg.matrix_rank(design)) != 2:
        raise NumericalError("linear calibration predictions must vary")
    coefficients, _, _, _ = np.linalg.lstsq(
        design, np.asarray(response, dtype=np.float64), rcond=None
    )
    return CalibrationEstimate(float(coefficients[0]), float(coefficients[1]))


def _logistic_calibration(
    response: tuple[float, ...], linear_predictors: tuple[float, ...]
) -> CalibrationEstimate:
    result = fit_lrm(
        response,
        tuple((value,) for value in linear_predictors),
        feature_names=("linear_predictor",),
    )
    return CalibrationEstimate(result.coefficients[0], result.coefficients[1])


def _auc(response: tuple[float, ...], predictions: tuple[float, ...]) -> float | None:
    cases = sum(value == 1.0 for value in response)
    controls = len(response) - cases
    if cases == 0 or controls == 0:
        return None
    ordered = sorted(zip(predictions, response, strict=True), key=lambda pair: pair[0])
    rank_sum = 0.0
    start = 0
    while start < len(ordered):
        stop = start + 1
        while stop < len(ordered) and ordered[stop][0] == ordered[start][0]:
            stop += 1
        average_rank = (start + 1 + stop) / 2.0
        rank_sum += average_rank * sum(value == 1.0 for _, value in ordered[start:stop])
        start = stop
    return (rank_sum - cases * (cases + 1) / 2.0) / (cases * controls)


def _ols_indices(
    response: tuple[float, ...], predictions: tuple[float, ...]
) -> OlsValidationIndices:
    observed = np.asarray(response, dtype=np.float64)
    predicted = np.asarray(predictions, dtype=np.float64)
    residual_sum = float(np.sum((observed - predicted) ** 2))
    total_sum = float(np.sum((observed - np.mean(observed)) ** 2))
    calibration = _linear_calibration(response, predictions)
    return OlsValidationIndices(
        r_squared=None if total_sum == 0.0 else 1.0 - residual_sum / total_sum,
        mean_squared_error=residual_sum / len(response),
        calibration_intercept=calibration.intercept,
        calibration_slope=calibration.slope,
    )


def _binary_indices(
    response: tuple[float, ...],
    probabilities: tuple[float, ...],
    linear_predictors: tuple[float, ...],
) -> BinaryValidationIndices:
    if any(value not in {0.0, 1.0} for value in response):
        raise InputValidationError("binary response values must be exactly 0 or 1")
    calibration = _logistic_calibration(response, linear_predictors)
    auc = _auc(response, probabilities)
    brier = float(
        np.mean(
            (np.asarray(response, dtype=np.float64) - np.asarray(probabilities)) ** 2
        )
    )
    return BinaryValidationIndices(
        dxy=None if auc is None else 2.0 * auc - 1.0,
        brier_score=brier,
        calibration_intercept=calibration.intercept,
        calibration_slope=calibration.slope,
    )


def _indices(
    model: SupportedModel,
    response: tuple[float, ...],
    features: tuple[tuple[float, ...], ...],
) -> ValidationIndices:
    if isinstance(model, OlsResult):
        return _ols_indices(response, model.predict(features))
    return _binary_indices(
        response,
        model.predict_probability(features),
        model.predict_linear(features),
    )


def _calibration(
    model: SupportedModel,
    response: tuple[float, ...],
    features: tuple[tuple[float, ...], ...],
) -> CalibrationEstimate:
    if isinstance(model, OlsResult):
        return _linear_calibration(response, model.predict(features))
    return _logistic_calibration(response, model.predict_linear(features))


def _require_supported(model: object) -> SupportedModel:
    if not isinstance(model, (OlsResult, BinaryLogisticResult)):
        raise UnsupportedFeatureError(
            "model-specific validation currently supports OLS and "
            "binary-logistic results"
        )
    return model


def validate_model(
    model: object,
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    plan: ResamplePlan,
    *,
    row_ids: Iterable[str] | None = None,
    failure_policy: FailurePolicy = "raise",
    max_iterations: int = 100,
    tolerance: float | None = None,
) -> ModelValidationResult:
    """Validate OLS or binary-logistic behavior with fresh per-split refits.

    ``features`` is a fixed realized numeric design. Formula transformations or
    other learned preprocessing are not rebuilt by this convenience API; use
    :func:`run_resample_plan` when those steps are part of the procedure.
    """
    supported = _require_supported(model)
    y, rows = _snapshot_inputs(
        supported, response, features, plan=plan, row_ids=row_ids
    )
    apparent = _indices(supported, y, rows)

    def procedure(split: ResampleSplit) -> ModelValidationSplit:
        analysis_y = take_rows(y, split.analysis_indices, plan=plan)
        analysis_x = take_rows(rows, split.analysis_indices, plan=plan)
        assessment_y = take_rows(y, split.assessment_indices, plan=plan)
        assessment_x = take_rows(rows, split.assessment_indices, plan=plan)
        fitted = _fit_like(
            supported,
            analysis_y,
            analysis_x,
            max_iterations=max_iterations,
            tolerance=tolerance,
        )
        return ModelValidationSplit(
            training=_indices(fitted, analysis_y, analysis_x),
            assessment=_indices(fitted, assessment_y, assessment_x),
        )

    execution = run_resample_plan(plan, procedure, failure_policy=failure_policy)
    return ModelValidationResult(_family(supported), apparent, execution)


def calibrate_model(
    model: object,
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    plan: ResamplePlan,
    *,
    prediction_grid: Iterable[float] | None = None,
    grid_points: int = 50,
    row_ids: Iterable[str] | None = None,
    failure_policy: FailurePolicy = "raise",
    max_iterations: int = 100,
    tolerance: float | None = None,
) -> ModelCalibrationResult:
    """Estimate apparent and per-split parametric recalibration relationships."""
    supported = _require_supported(model)
    y, rows = _snapshot_inputs(
        supported, response, features, plan=plan, row_ids=row_ids
    )
    scale: CalibrationScale
    apparent_predictions: tuple[float, ...]
    if isinstance(supported, OlsResult):
        scale = "response"
        apparent_predictions = supported.predict(rows)
    else:
        scale = "probability"
        apparent_predictions = supported.predict_probability(rows)
    if prediction_grid is None:
        raw_grid_points = cast(object, grid_points)
        if isinstance(raw_grid_points, bool) or not isinstance(raw_grid_points, int):
            raise InputValidationError("grid_points must be an integer")
        if not 2 <= grid_points <= MAX_CALIBRATION_POINTS:
            raise InputValidationError(
                f"grid_points must be between 2 and {MAX_CALIBRATION_POINTS}"
            )
        lower = min(apparent_predictions)
        upper = max(apparent_predictions)
        if scale == "probability":
            lower = max(lower, np.finfo(np.float64).eps)
            upper = min(upper, 1.0 - np.finfo(np.float64).eps)
        if lower >= upper:
            raise NumericalError("calibration prediction range must be positive")
        grid = tuple(float(value) for value in np.linspace(lower, upper, grid_points))
    else:
        grid = tuple(
            _finite(value, name="prediction_grid") for value in prediction_grid
        )
    apparent = _calibration(supported, y, rows)

    def procedure(split: ResampleSplit) -> ModelCalibrationSplit:
        analysis_y = take_rows(y, split.analysis_indices, plan=plan)
        analysis_x = take_rows(rows, split.analysis_indices, plan=plan)
        assessment_y = take_rows(y, split.assessment_indices, plan=plan)
        assessment_x = take_rows(rows, split.assessment_indices, plan=plan)
        fitted = _fit_like(
            supported,
            analysis_y,
            analysis_x,
            max_iterations=max_iterations,
            tolerance=tolerance,
        )
        return ModelCalibrationSplit(
            training=_calibration(fitted, analysis_y, analysis_x),
            assessment=_calibration(fitted, assessment_y, assessment_x),
        )

    execution = run_resample_plan(plan, procedure, failure_policy=failure_policy)
    return ModelCalibrationResult(
        model_family=_family(supported),
        scale=scale,
        prediction_grid=grid,
        apparent=apparent,
        apparent_curve=apparent.predict(grid, scale=scale),
        resamples=execution,
    )


__all__ = [
    "BinaryValidationIndices",
    "CalibrationEstimate",
    "ModelCalibrationResult",
    "ModelCalibrationSplit",
    "ModelValidationResult",
    "ModelValidationSplit",
    "OlsValidationIndices",
    "calibrate_model",
    "validate_model",
]
