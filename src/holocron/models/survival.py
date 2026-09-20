"""Owned survival estimators, censoring inputs, and result contracts."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Integral, Real
from statistics import NormalDist
from typing import Literal, TypeAlias, cast, overload

import numpy as np
import numpy.typing as npt

from holocron._serialization import canonical_json, parse_json_object
from holocron.exceptions import (
    ConvergenceError,
    InputValidationError,
    RankDeficiencyError,
)

FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]
IntVector = npt.NDArray[np.int64]
CoxMethod = Literal["efron", "breslow"]
ParametricDistribution = Literal["weibull", "exponential"]
SurvivalResidualKind = Literal["martingale", "deviance", "normalized", "response"]
SurvivalInterpolation = Literal["step", "linear"]
SurvivalCensoringType = Literal["exact", "left", "right", "interval"]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

MAX_OBSERVATIONS = 1_000_000
MAX_PARAMETERS = 1024
COX_SCHEMA_VERSION = "holocron-cox-result/v2"
PARAMETRIC_SCHEMA_VERSION = "holocron-parametric-survival-result/v2"
NONPARAMETRIC_SCHEMA_VERSION = "holocron-nonparametric-survival-result/v2"
COX_V1_SCHEMA_VERSION = "holocron-cox-result/v1"
PARAMETRIC_V1_SCHEMA_VERSION = "holocron-parametric-survival-result/v1"
NONPARAMETRIC_V1_SCHEMA_VERSION = "holocron-nonparametric-survival-result/v1"
BASELINE_STRATUM = "__all__"
EXACT_CENSORING = 0
LEFT_CENSORING = 1
RIGHT_CENSORING = 2
INTERVAL_CENSORING = 3


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, Real)
        and math.isfinite(float(value))
    )


def _as_times_events(
    times: Iterable[float], events: Iterable[int | bool]
) -> tuple[FloatVector, IntVector]:
    time_values = tuple(float(value) for value in times)
    event_values = tuple(events)
    if not time_values or len(time_values) != len(event_values):
        raise InputValidationError("times and events must have equal nonzero length")
    if len(time_values) > MAX_OBSERVATIONS:
        raise InputValidationError("survival response exceeds the observation limit")
    if not all(math.isfinite(value) and value > 0.0 for value in time_values):
        raise InputValidationError("times must contain only finite positive values")
    if any(
        not isinstance(value, Integral) or int(value) not in (0, 1)
        for value in event_values
    ):
        raise InputValidationError("events must contain only integer or boolean 0/1")
    event_array = np.asarray(
        tuple(int(value) for value in event_values), dtype=np.int64
    )
    if not np.any(  # pyright: ignore[reportUnknownMemberType]
        event_array == 1
    ):
        raise InputValidationError("at least one observed event is required")
    return np.asarray(time_values, dtype=np.float64), event_array


def _as_features(values: Iterable[Iterable[float]], rows: int) -> FloatMatrix:
    feature_rows = tuple(tuple(float(value) for value in row) for row in values)
    if len(feature_rows) != rows or not feature_rows:
        raise InputValidationError("features must have one row per observation")
    width = len(feature_rows[0])
    if width == 0 or width >= MAX_PARAMETERS:
        raise InputValidationError(
            "features must contain a supported number of columns"
        )
    if any(len(row) != width for row in feature_rows):
        raise InputValidationError("feature rows must have equal lengths")
    if not all(math.isfinite(value) for row in feature_rows for value in row):
        raise InputValidationError("features must contain only finite values")
    matrix = np.asarray(feature_rows, dtype=np.float64)
    if np.linalg.matrix_rank(matrix) < width:
        raise RankDeficiencyError("features must have full column rank")
    return matrix


def _feature_names(width: int, names: Iterable[str] | None) -> tuple[str, ...]:
    result = (
        tuple(names)
        if names is not None
        else tuple(f"x{index + 1}" for index in range(width))
    )
    if len(result) != width:
        raise InputValidationError("feature_names must match the feature columns")
    if any(not name for name in result) or len(set(result)) != width:
        raise InputValidationError("feature_names must be non-empty and unique")
    return result


def _matrix_rows(value: FloatMatrix) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(item) for item in row) for row in value)


def _vector(value: FloatVector) -> tuple[float, ...]:
    return tuple(float(item) for item in value)


def _validate_prediction_features(
    values: Iterable[Iterable[float]], width: int
) -> FloatMatrix:
    rows = tuple(tuple(float(value) for value in row) for row in values)
    if not rows or any(len(row) != width for row in rows):
        raise InputValidationError("prediction features have the wrong shape")
    if not all(math.isfinite(value) for row in rows for value in row):
        raise InputValidationError("prediction features must be finite")
    return np.asarray(rows, dtype=np.float64)


def _validate_prediction_times(values: Iterable[float]) -> FloatVector:
    times = tuple(float(value) for value in values)
    if not times or not all(math.isfinite(value) and value >= 0.0 for value in times):
        raise InputValidationError("prediction times must be finite and nonnegative")
    return np.asarray(times, dtype=np.float64)


def _validate_probabilities(values: Iterable[float]) -> FloatVector:
    probabilities = tuple(float(value) for value in values)
    if not probabilities or not all(
        math.isfinite(value) and 0.0 < value < 1.0 for value in probabilities
    ):
        raise InputValidationError(
            "prediction probabilities must be finite and strictly between zero and one"
        )
    return np.asarray(probabilities, dtype=np.float64)


def _validate_interpolation(value: str) -> SurvivalInterpolation:
    if value not in {"step", "linear"}:
        raise InputValidationError("survival interpolation must be 'step' or 'linear'")
    return cast(SurvivalInterpolation, value)


def _validate_restricted_time(value: float) -> float:
    restricted_time = float(value)
    if not math.isfinite(restricted_time) or restricted_time <= 0.0:
        raise InputValidationError("restricted_time must be finite and positive")
    return restricted_time


def _curve_quantiles(
    times: FloatVector,
    survival: FloatVector,
    probabilities: FloatVector,
    interpolation: SurvivalInterpolation,
) -> tuple[float | None, ...]:
    support_times = np.empty(times.size + 1, dtype=np.float64)
    support_times[0] = 0.0
    support_times[1:] = times
    support_survival = np.empty(survival.size + 1, dtype=np.float64)
    support_survival[0] = 1.0
    support_survival[1:] = survival
    values: list[float | None] = []
    for probability in probabilities:
        target = 1.0 - float(probability)
        reached = np.flatnonzero(  # pyright: ignore[reportUnknownMemberType]
            support_survival <= target
        )
        if reached.size == 0:
            values.append(None)
        elif interpolation == "step":
            values.append(float(support_times[int(reached[0])]))
        else:
            index = int(reached[0])
            if index == 0:
                values.append(0.0)
            else:
                left_survival = float(support_survival[index - 1])
                right_survival = float(support_survival[index])
                left_time = float(support_times[index - 1])
                right_time = float(support_times[index])
                fraction = (left_survival - target) / (left_survival - right_survival)
                values.append(left_time + fraction * (right_time - left_time))
    return tuple(values)


def _kaplan_meier_quantiles(
    times: FloatVector,
    survival: FloatVector,
    probabilities: FloatVector,
    interpolation: SurvivalInterpolation,
) -> tuple[float | None, ...]:
    """Match quantile.survfit, including exact-threshold plateau midpoints."""
    if interpolation == "linear":
        return _curve_quantiles(times, survival, probabilities, interpolation)
    values: list[float | None] = []
    for probability in probabilities:
        target = 1.0 - float(probability)
        reached = np.flatnonzero(  # pyright: ignore[reportUnknownMemberType]
            survival <= target
        )
        if reached.size == 0:
            values.append(None)
            continue
        index = int(reached[0])
        if math.isclose(float(survival[index]), target, rel_tol=1e-12, abs_tol=1e-12):
            endpoint = index
            while endpoint + 1 < times.size and math.isclose(
                float(survival[endpoint + 1]),
                target,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                endpoint += 1
            if endpoint + 1 < times.size:
                endpoint += 1
            values.append((float(times[index]) + float(times[endpoint])) / 2.0)
        else:
            values.append(float(times[index]))
    return tuple(values)


def _restricted_curve_mean(
    times: FloatVector,
    survival: FloatVector,
    restricted_time: float,
    interpolation: SurvivalInterpolation,
) -> float:
    if times.size == 0 or restricted_time > float(times[-1]):
        raise InputValidationError(
            "restricted_time must not exceed the fitted curve support"
        )
    interior = times[times < restricted_time]
    support_times = np.empty(interior.size + 2, dtype=np.float64)
    support_times[0] = 0.0
    support_times[1:-1] = interior
    support_times[-1] = restricted_time
    indices = (
        np.searchsorted(  # pyright: ignore[reportUnknownMemberType]
            times, support_times, side="right"
        )
        - 1
    )
    support_survival = np.where(  # pyright: ignore[reportUnknownMemberType]
        indices >= 0, survival[np.maximum(indices, 0)], 1.0
    )
    widths = support_times[1:] - support_times[:-1]
    if interpolation == "step":
        return float(np.sum(widths * support_survival[:-1]))
    return float(np.sum(widths * (support_survival[:-1] + support_survival[1:]) / 2.0))


def _cox_restricted_mean(
    times: FloatVector,
    survival: FloatVector,
    restricted_time: float,
    interpolation: SurvivalInterpolation,
) -> float:
    """Reproduce the pinned rms Mean.cph event-grid integration contract."""
    if times.size == 0 or restricted_time > float(times[-1]):
        raise InputValidationError(
            "restricted_time must not exceed the fitted curve support"
        )
    included = times <= restricted_time
    included_times = times[included]
    included_survival = survival[included]
    support_times = np.empty(included_times.size + 1, dtype=np.float64)
    support_times[0] = 0.0
    support_times[1:] = included_times
    support_survival = np.empty(included_survival.size + 1, dtype=np.float64)
    support_survival[0] = 1.0
    support_survival[1:] = included_survival
    if support_times.size < 2:
        return 0.0
    widths = support_times[1:] - support_times[:-1]
    if interpolation == "step":
        return float(np.sum(widths * support_survival[:-1]))
    return float(np.sum(widths * (support_survival[:-1] + support_survival[1:]) / 2.0))


def _as_optional_numeric(
    values: Iterable[float] | None,
    rows: int,
    *,
    name: str,
    default: float,
    positive: bool = False,
) -> FloatVector:
    if values is None:
        return np.full(rows, default, dtype=np.float64)
    raw = tuple(float(value) for value in values)
    if len(raw) != rows:
        raise InputValidationError(f"{name} must have one value per observation")
    if not all(math.isfinite(value) and (not positive or value > 0.0) for value in raw):
        requirement = "finite positive" if positive else "finite"
        raise InputValidationError(f"{name} must contain only {requirement} values")
    return np.asarray(raw, dtype=np.float64)


def _as_entry_times(values: Iterable[float] | None, stop: FloatVector) -> FloatVector:
    entry = _as_optional_numeric(values, stop.size, name="entry_times", default=0.0)
    if np.any(  # pyright: ignore[reportUnknownMemberType]
        entry < 0.0
    ) or np.any(  # pyright: ignore[reportUnknownMemberType]
        entry >= stop
    ):
        raise InputValidationError(
            "entry_times must be nonnegative and strictly below stop times"
        )
    return entry


def _as_strata(
    values: Iterable[object] | None, rows: int
) -> tuple[tuple[str, ...], tuple[str, ...], IntVector]:
    raw_values: tuple[object, ...] = (
        (BASELINE_STRATUM,) * rows if values is None else tuple(values)
    )
    if len(raw_values) != rows or any(
        not isinstance(value, str) or not value for value in raw_values
    ):
        raise InputValidationError("strata must contain one non-empty string per row")
    raw = tuple(cast(str, value) for value in raw_values)
    levels = tuple(dict.fromkeys(raw))
    if len(levels) > min(rows, 1024):
        raise InputValidationError("strata exceed the supported level limit")
    lookup = {value: index for index, value in enumerate(levels)}
    codes = np.asarray(tuple(lookup[value] for value in raw), dtype=np.int64)
    return raw, levels, codes


def _prediction_offsets(values: Iterable[float] | None, rows: int) -> FloatVector:
    return _as_optional_numeric(values, rows, name="offsets", default=0.0)


def _prediction_strata(
    values: Iterable[str] | None, rows: int, levels: tuple[str, ...]
) -> tuple[str, ...]:
    if values is None:
        if len(levels) != 1:
            raise InputValidationError(
                "prediction strata are required for a stratified fit"
            )
        return (levels[0],) * rows
    result = tuple(values)
    if len(result) != rows or any(value not in levels for value in result):
        raise InputValidationError("prediction strata must match fitted strata")
    return result


def _deviance_residual(event: int, martingale: float) -> float:
    inside = martingale
    if event:
        inside += math.log(max(1.0 - martingale, 1e-300))
    value = math.sqrt(max(-2.0 * inside, 0.0))
    return math.copysign(value, martingale)


@dataclass(frozen=True, slots=True)
class SurvivalResponse:
    """Positive-time exact, left-, right-, or interval-censored response."""

    lower: tuple[float, ...]
    upper: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.lower or len(self.lower) != len(self.upper):
            raise InputValidationError(
                "survival censoring endpoints must have equal nonzero length"
            )
        if len(self.lower) > MAX_OBSERVATIONS:
            raise InputValidationError(
                "survival response exceeds the observation limit"
            )
        has_finite_upper = False
        for lower, upper in zip(self.lower, self.upper, strict=True):
            if (
                isinstance(lower, bool)
                or isinstance(upper, bool)
                or not isinstance(lower, Real)
                or not isinstance(upper, Real)
                or math.isnan(float(lower))
                or math.isnan(float(upper))
                or lower == math.inf
                or upper == -math.inf
                or float(lower) > float(upper)
                or (lower == -math.inf and upper == math.inf)
                or (math.isfinite(lower) and float(lower) <= 0.0)
                or (math.isfinite(upper) and float(upper) <= 0.0)
            ):
                raise InputValidationError("invalid survival censoring interval")
            has_finite_upper = has_finite_upper or math.isfinite(float(upper))
        if not has_finite_upper:
            raise InputValidationError(
                "survival response requires at least one finite event bound"
            )
        object.__setattr__(self, "lower", tuple(float(value) for value in self.lower))
        object.__setattr__(self, "upper", tuple(float(value) for value in self.upper))

    @classmethod
    def from_intervals(
        cls, lower: Iterable[float], upper: Iterable[float] | None = None
    ) -> SurvivalResponse:
        """Construct a response; omitted upper endpoints declare exact times."""
        lower_values = tuple(lower)
        upper_values = lower_values if upper is None else tuple(upper)
        return cls(lower_values, upper_values)

    @property
    def censoring_types(self) -> tuple[SurvivalCensoringType, ...]:
        """Return the censoring contribution represented by each interval."""
        result: list[SurvivalCensoringType] = []
        for lower, upper in zip(self.lower, self.upper, strict=True):
            if lower == upper:
                result.append("exact")
            elif lower == -math.inf:
                result.append("left")
            elif upper == math.inf:
                result.append("right")
            else:
                result.append("interval")
        return tuple(result)


@dataclass(frozen=True, slots=True)
class SurvivalResidualResult:
    """A named survival residual vector in original training-row order."""

    kind: SurvivalResidualKind
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SurvivalCurveResult:
    """Structured survival curves with one row per prediction subject."""

    times: tuple[float, ...]
    strata: tuple[str, ...]
    survival: tuple[tuple[float, ...], ...]
    linear_predictors: tuple[float, ...] | None

    def __post_init__(self) -> None:
        if (
            not self.times
            or any(not math.isfinite(value) or value < 0.0 for value in self.times)
            or any(
                later <= earlier
                for earlier, later in zip(self.times, self.times[1:], strict=False)
            )
            or not self.survival
            or len(self.strata) != len(self.survival)
            or any(not value for value in self.strata)
            or any(len(row) != len(self.times) for row in self.survival)
            or any(
                not math.isfinite(value) or not 0.0 <= value <= 1.0
                for row in self.survival
                for value in row
            )
            or any(
                later > earlier
                for row in self.survival
                for earlier, later in zip(row, row[1:], strict=False)
            )
            or (
                self.linear_predictors is not None
                and (
                    len(self.linear_predictors) != len(self.survival)
                    or any(not math.isfinite(value) for value in self.linear_predictors)
                )
            )
        ):
            raise InputValidationError("inconsistent survival curve result")


@dataclass(frozen=True, slots=True)
class CoxResult:
    """Immutable Cox proportional-hazards fit for right-censored outcomes."""

    method: CoxMethod
    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    feature_means: tuple[float, ...]
    linear_predictors: tuple[float, ...]
    log_likelihood: tuple[float, float]
    baseline_times: tuple[float, ...]
    baseline_cumulative_hazard: tuple[float, ...]
    baseline_strata: tuple[str, ...]
    baseline_hazard: tuple[float, ...]
    baseline_survival: tuple[float, ...]
    strata_levels: tuple[str, ...]
    iterations: int
    n_observations: int

    @property
    def coefficient_names(self) -> tuple[str, ...]:
        """Return names in coefficient and covariance order."""
        return self.feature_names

    def predict_linear(
        self,
        features: Iterable[Iterable[float]],
        *,
        offsets: Iterable[float] | None = None,
    ) -> tuple[float, ...]:
        """Predict mean-centered log relative hazards."""
        matrix = _validate_prediction_features(features, len(self.coefficients))
        offset = _prediction_offsets(offsets, matrix.shape[0])
        return _vector(
            (matrix - np.asarray(self.feature_means, dtype=np.float64))
            @ np.asarray(self.coefficients, dtype=np.float64)
            + offset
        )

    def _baseline_at(
        self, requested: FloatVector, stratum: str, values: tuple[float, ...]
    ) -> FloatVector:
        mask = tuple(value == stratum for value in self.baseline_strata)
        observed = np.asarray(
            tuple(
                time
                for time, keep in zip(self.baseline_times, mask, strict=True)
                if keep
            ),
            dtype=np.float64,
        )
        baseline = np.asarray(
            tuple(value for value, keep in zip(values, mask, strict=True) if keep),
            dtype=np.float64,
        )
        if observed.size == 0:
            return np.zeros(requested.size, dtype=np.float64)
        indices = (
            np.searchsorted(  # pyright: ignore[reportUnknownMemberType]
                observed, requested, side="right"
            )
            - 1
        )
        return np.where(  # pyright: ignore[reportUnknownMemberType]
            indices >= 0, baseline[np.maximum(indices, 0)], 0.0
        )

    def predict_cumulative_hazard(
        self,
        features: Iterable[Iterable[float]],
        times: Iterable[float],
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        """Predict cumulative hazard at each time for every feature row."""
        matrix = _validate_prediction_features(features, len(self.coefficients))
        predictors = np.asarray(
            self.predict_linear(matrix, offsets=offsets), dtype=np.float64
        )
        requested = _validate_prediction_times(times)
        prediction_strata = _prediction_strata(
            strata, matrix.shape[0], self.strata_levels
        )
        rows = tuple(
            self._baseline_at(requested, stratum, self.baseline_cumulative_hazard)
            * math.exp(float(predictor))
            for predictor, stratum in zip(predictors, prediction_strata, strict=True)
        )
        return tuple(_vector(row) for row in rows)

    def predict_survival(
        self,
        features: Iterable[Iterable[float]],
        times: Iterable[float],
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        """Predict survival at each requested time for every feature row."""
        cumulative = np.asarray(
            self.predict_cumulative_hazard(
                features, times, strata=strata, offsets=offsets
            ),
            dtype=np.float64,
        )
        return _matrix_rows(np.exp(-cumulative))

    def predict_curve(
        self,
        features: Iterable[Iterable[float]],
        times: Iterable[float] | None = None,
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
    ) -> SurvivalCurveResult:
        """Return structured Cox survival curves on an explicit or fitted grid."""
        matrix = _validate_prediction_features(features, len(self.coefficients))
        requested = (
            np.asarray((0.0, *sorted(set(self.baseline_times))), dtype=np.float64)
            if times is None
            else _validate_prediction_times(times)
        )
        if any(
            later <= earlier
            for earlier, later in zip(requested[:-1], requested[1:], strict=True)
        ):
            raise InputValidationError(
                "curve prediction times must be strictly increasing"
            )
        prediction_strata = _prediction_strata(
            strata, matrix.shape[0], self.strata_levels
        )
        offset = _prediction_offsets(offsets, matrix.shape[0])
        predictors = self.predict_linear(matrix, offsets=offset)
        survival = self.predict_survival(
            matrix,
            requested,
            strata=prediction_strata,
            offsets=offset,
        )
        return SurvivalCurveResult(
            times=_vector(requested),
            strata=prediction_strata,
            survival=survival,
            linear_predictors=predictors,
        )

    def predict_quantile(
        self,
        features: Iterable[Iterable[float]],
        probabilities: Iterable[float] = (0.5,),
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
        interpolation: SurvivalInterpolation = "step",
    ) -> tuple[tuple[float | None, ...], ...]:
        """Predict event-time CDF quantiles; return ``None`` beyond follow-up."""
        matrix = _validate_prediction_features(features, len(self.coefficients))
        requested = _validate_probabilities(probabilities)
        interpolation = _validate_interpolation(interpolation)
        prediction_strata = _prediction_strata(
            strata, matrix.shape[0], self.strata_levels
        )
        predictors = self.predict_linear(matrix, offsets=offsets)
        rows: list[tuple[float | None, ...]] = []
        for predictor, stratum in zip(predictors, prediction_strata, strict=True):
            mask = tuple(value == stratum for value in self.baseline_strata)
            times = np.asarray(
                tuple(
                    time
                    for time, keep in zip(self.baseline_times, mask, strict=True)
                    if keep
                ),
                dtype=np.float64,
            )
            survival = np.exp(
                -np.asarray(
                    tuple(
                        value
                        for value, keep in zip(
                            self.baseline_cumulative_hazard, mask, strict=True
                        )
                        if keep
                    ),
                    dtype=np.float64,
                )
                * math.exp(predictor)
            )
            rows.append(_curve_quantiles(times, survival, requested, interpolation))
        return tuple(rows)

    def predict_mean(
        self,
        features: Iterable[Iterable[float]],
        *,
        restricted_time: float,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
        interpolation: SurvivalInterpolation = "step",
    ) -> tuple[float, ...]:
        """Predict the pinned rms event-grid mean at an explicit truncation."""
        matrix = _validate_prediction_features(features, len(self.coefficients))
        horizon = _validate_restricted_time(restricted_time)
        interpolation = _validate_interpolation(interpolation)
        prediction_strata = _prediction_strata(
            strata, matrix.shape[0], self.strata_levels
        )
        predictors = self.predict_linear(matrix, offsets=offsets)
        values: list[float] = []
        for predictor, stratum in zip(predictors, prediction_strata, strict=True):
            mask = tuple(value == stratum for value in self.baseline_strata)
            times = np.asarray(
                tuple(
                    time
                    for time, keep in zip(self.baseline_times, mask, strict=True)
                    if keep
                ),
                dtype=np.float64,
            )
            survival = np.exp(
                -np.asarray(
                    tuple(
                        value
                        for value, keep in zip(
                            self.baseline_cumulative_hazard, mask, strict=True
                        )
                        if keep
                    ),
                    dtype=np.float64,
                )
                * math.exp(predictor)
            )
            values.append(_cox_restricted_mean(times, survival, horizon, interpolation))
        return tuple(values)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned result document."""
        return {
            "schema_version": COX_SCHEMA_VERSION,
            "method": self.method,
            "feature_names": list(self.feature_names),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "feature_means": list(self.feature_means),
            "linear_predictors": list(self.linear_predictors),
            "log_likelihood": list(self.log_likelihood),
            "baseline_times": list(self.baseline_times),
            "baseline_cumulative_hazard": list(self.baseline_cumulative_hazard),
            "baseline_strata": list(self.baseline_strata),
            "baseline_hazard": list(self.baseline_hazard),
            "baseline_survival": list(self.baseline_survival),
            "strata_levels": list(self.strata_levels),
            "iterations": self.iterations,
            "n_observations": self.n_observations,
        }

    def to_json(self) -> str:
        """Serialize the fit as canonical non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical result document."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> CoxResult:
        """Reconstruct a Cox result from an exact-version document."""
        data = _result_object_any(document, {COX_SCHEMA_VERSION, COX_V1_SCHEMA_VERSION})
        if data["schema_version"] == COX_V1_SCHEMA_VERSION:
            data = _migrate_cox_v1(data)
        required = {
            "schema_version",
            "method",
            "feature_names",
            "coefficients",
            "covariance",
            "feature_means",
            "linear_predictors",
            "log_likelihood",
            "baseline_times",
            "baseline_cumulative_hazard",
            "baseline_strata",
            "baseline_hazard",
            "baseline_survival",
            "strata_levels",
            "iterations",
            "n_observations",
        }
        _exact_keys(data, required)
        method = data["method"]
        if method not in {"efron", "breslow"}:
            raise InputValidationError("invalid Cox method")
        names = _read_names(data["feature_names"])
        coefficients = _read_vector(data["coefficients"], len(names))
        covariance = _read_matrix(data["covariance"], len(names))
        means = _read_vector(data["feature_means"], len(names))
        linear = _read_vector(data["linear_predictors"])
        log_likelihood = _read_vector(data["log_likelihood"], 2)
        baseline_times = _read_vector(data["baseline_times"])
        baseline_hazard = _read_vector(
            data["baseline_cumulative_hazard"], len(baseline_times)
        )
        baseline_strata = _read_names_with_duplicates(
            data["baseline_strata"], len(baseline_times)
        )
        hazard = _read_vector(data["baseline_hazard"], len(baseline_times))
        baseline_survival = _read_vector(data["baseline_survival"], len(baseline_times))
        strata_levels = _read_names(data["strata_levels"])
        iterations = _read_positive_integer(data["iterations"], allow_zero=True)
        observations = _read_positive_integer(data["n_observations"])
        if (
            len(linear) != observations
            or any(value <= 0.0 for value in baseline_times)
            or any(value < 0.0 for value in baseline_hazard)
            or any(value < 0.0 for value in hazard)
            or any(not 0.0 <= value <= 1.0 for value in baseline_survival)
            or any(value not in strata_levels for value in baseline_strata)
            or not _valid_stratified_curve(
                baseline_times,
                baseline_hazard,
                baseline_strata,
                survival=baseline_survival,
                increments=hazard,
            )
        ):
            raise InputValidationError("inconsistent Cox result document")
        return cls(
            cast(CoxMethod, method),
            names,
            coefficients,
            covariance,
            means,
            linear,
            cast(tuple[float, float], log_likelihood),
            baseline_times,
            baseline_hazard,
            baseline_strata,
            hazard,
            baseline_survival,
            strata_levels,
            iterations,
            observations,
        )

    @classmethod
    def from_json(cls, value: str) -> CoxResult:
        """Reconstruct a Cox result from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="Cox result"))


@dataclass(frozen=True, slots=True)
class ParametricSurvivalResult:
    """Immutable Weibull or exponential accelerated-failure-time fit."""

    distribution: ParametricDistribution
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    scale: float | None
    strata_levels: tuple[str, ...]
    scales: tuple[float, ...]
    linear_predictors: tuple[float, ...]
    log_likelihood: tuple[float, float]
    iterations: int
    n_observations: int

    def predict_linear(
        self,
        features: Iterable[Iterable[float]],
        *,
        offsets: Iterable[float] | None = None,
    ) -> tuple[float, ...]:
        """Predict log survival-time location."""
        matrix = _validate_prediction_features(features, len(self.coefficients) - 1)
        offset = _prediction_offsets(offsets, matrix.shape[0])
        return _vector(
            self.coefficients[0]
            + matrix @ np.asarray(self.coefficients[1:], dtype=np.float64)
            + offset
        )

    def _prediction_scales(
        self, strata: Iterable[str] | None, rows: int
    ) -> FloatVector:
        labels = _prediction_strata(strata, rows, self.strata_levels)
        by_stratum = dict(zip(self.strata_levels, self.scales, strict=True))
        return np.asarray(
            tuple(by_stratum[label] for label in labels), dtype=np.float64
        )

    def predict_survival(
        self,
        features: Iterable[Iterable[float]],
        times: Iterable[float],
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        """Predict survival at each strictly positive requested time."""
        matrix = _validate_prediction_features(features, len(self.coefficients) - 1)
        predictors = np.asarray(
            self.predict_linear(matrix, offsets=offsets), dtype=np.float64
        )
        scales = self._prediction_scales(strata, matrix.shape[0])
        requested = _validate_prediction_times(times)
        if np.any(  # pyright: ignore[reportUnknownMemberType]
            requested <= 0.0
        ):
            raise InputValidationError("parametric prediction times must be positive")
        exponent = (np.log(requested)[None, :] - predictors[:, None]) / scales[:, None]
        values = np.exp(
            -np.exp(
                np.clip(  # pyright: ignore[reportUnknownMemberType]
                    exponent, -745.0, 700.0
                )
            )
        )
        return _matrix_rows(values)

    def predict_hazard(
        self,
        features: Iterable[Iterable[float]],
        times: Iterable[float],
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        """Predict the Weibull or exponential hazard function."""
        matrix = _validate_prediction_features(features, len(self.coefficients) - 1)
        predictors = np.asarray(
            self.predict_linear(matrix, offsets=offsets), dtype=np.float64
        )
        scales = self._prediction_scales(strata, matrix.shape[0])
        requested = _validate_prediction_times(times)
        if np.any(  # pyright: ignore[reportUnknownMemberType]
            requested <= 0.0
        ):
            raise InputValidationError("parametric prediction times must be positive")
        exponent = (np.log(requested)[None, :] - predictors[:, None]) / scales[:, None]
        cumulative = np.exp(
            np.clip(  # pyright: ignore[reportUnknownMemberType]
                exponent, -745.0, 700.0
            )
        )
        return _matrix_rows(cumulative / (scales[:, None] * requested[None, :]))

    def predict_curve(
        self,
        features: Iterable[Iterable[float]],
        times: Iterable[float],
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
    ) -> SurvivalCurveResult:
        """Return structured parametric survival curves on an explicit grid."""
        matrix = _validate_prediction_features(features, len(self.coefficients) - 1)
        requested = _validate_prediction_times(times)
        if np.any(  # pyright: ignore[reportUnknownMemberType]
            requested <= 0.0
        ):
            raise InputValidationError("parametric prediction times must be positive")
        if any(
            later <= earlier
            for earlier, later in zip(requested[:-1], requested[1:], strict=True)
        ):
            raise InputValidationError(
                "curve prediction times must be strictly increasing"
            )
        prediction_strata = _prediction_strata(
            strata, matrix.shape[0], self.strata_levels
        )
        offset = _prediction_offsets(offsets, matrix.shape[0])
        predictors = self.predict_linear(matrix, offsets=offset)
        survival = self.predict_survival(
            matrix,
            requested,
            strata=prediction_strata,
            offsets=offset,
        )
        return SurvivalCurveResult(
            times=_vector(requested),
            strata=prediction_strata,
            survival=survival,
            linear_predictors=predictors,
        )

    def predict_quantile(
        self,
        features: Iterable[Iterable[float]],
        probabilities: Iterable[float] = (0.5,),
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
    ) -> tuple[tuple[float, ...], ...]:
        """Predict event-time quantiles for CDF probabilities in ``(0, 1)``."""
        matrix = _validate_prediction_features(features, len(self.coefficients) - 1)
        requested = _validate_probabilities(probabilities)
        predictors = np.asarray(
            self.predict_linear(matrix, offsets=offsets), dtype=np.float64
        )
        scales = self._prediction_scales(strata, matrix.shape[0])
        log_multiplier = np.log(-np.log1p(-requested))
        with np.errstate(over="ignore"):
            values = np.exp(
                predictors[:, None] + scales[:, None] * log_multiplier[None, :]
            )
        if not np.all(  # pyright: ignore[reportUnknownMemberType]
            np.isfinite(values)
        ):
            raise InputValidationError(
                "parametric quantile prediction exceeds the finite numeric range"
            )
        return _matrix_rows(values)

    def predict_mean(
        self,
        features: Iterable[Iterable[float]],
        *,
        strata: Iterable[str] | None = None,
        offsets: Iterable[float] | None = None,
    ) -> tuple[float, ...]:
        """Predict the finite Weibull or exponential mean survival time."""
        matrix = _validate_prediction_features(features, len(self.coefficients) - 1)
        predictors = np.asarray(
            self.predict_linear(matrix, offsets=offsets), dtype=np.float64
        )
        scales = self._prediction_scales(strata, matrix.shape[0])
        log_values = np.asarray(
            tuple(
                float(predictor) + math.lgamma(1.0 + float(scale))
                for predictor, scale in zip(predictors, scales, strict=True)
            ),
            dtype=np.float64,
        )
        with np.errstate(over="ignore"):
            values = np.exp(log_values)
        if not np.all(  # pyright: ignore[reportUnknownMemberType]
            np.isfinite(values)
        ):
            raise InputValidationError(
                "parametric mean prediction exceeds the finite numeric range"
            )
        return _vector(values)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned result document."""
        return {
            "schema_version": PARAMETRIC_SCHEMA_VERSION,
            "distribution": self.distribution,
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "scale": self.scale,
            "strata_levels": list(self.strata_levels),
            "scales": list(self.scales),
            "linear_predictors": list(self.linear_predictors),
            "log_likelihood": list(self.log_likelihood),
            "iterations": self.iterations,
            "n_observations": self.n_observations,
        }

    def to_json(self) -> str:
        """Serialize the fit as canonical non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical result document."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> ParametricSurvivalResult:
        """Reconstruct a parametric result from an exact-version document."""
        data = _result_object_any(
            document, {PARAMETRIC_SCHEMA_VERSION, PARAMETRIC_V1_SCHEMA_VERSION}
        )
        if data["schema_version"] == PARAMETRIC_V1_SCHEMA_VERSION:
            data = _migrate_parametric_v1(data)
        required = {
            "schema_version",
            "distribution",
            "coefficient_names",
            "coefficients",
            "covariance",
            "scale",
            "strata_levels",
            "scales",
            "linear_predictors",
            "log_likelihood",
            "iterations",
            "n_observations",
        }
        _exact_keys(data, required)
        distribution = data["distribution"]
        if distribution not in {"weibull", "exponential"}:
            raise InputValidationError("invalid parametric survival distribution")
        names = _read_names(data["coefficient_names"])
        coefficients = _read_vector(data["coefficients"], len(names))
        covariance = _read_matrix(data["covariance"], len(names))
        scale = None if data["scale"] is None else _read_positive_number(data["scale"])
        strata_levels = _read_names(data["strata_levels"])
        scales = _read_vector(data["scales"], len(strata_levels))
        linear = _read_vector(data["linear_predictors"])
        log_likelihood = _read_vector(data["log_likelihood"], 2)
        iterations = _read_positive_integer(data["iterations"], allow_zero=True)
        observations = _read_positive_integer(data["n_observations"])
        if (
            len(linear) != observations
            or names[0] != "(Intercept)"
            or any(value <= 0.0 for value in scales)
            or (len(scales) == 1 and scale != scales[0])
            or (len(scales) > 1 and scale is not None)
            or (distribution == "exponential" and scales != (1.0,))
        ):
            raise InputValidationError("inconsistent parametric result document")
        return cls(
            cast(ParametricDistribution, distribution),
            names,
            coefficients,
            covariance,
            scale,
            strata_levels,
            scales,
            linear,
            cast(tuple[float, float], log_likelihood),
            iterations,
            observations,
        )

    @classmethod
    def from_json(cls, value: str) -> ParametricSurvivalResult:
        """Reconstruct a parametric result from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="parametric result"))


@dataclass(frozen=True, slots=True)
class NonparametricSurvivalResult:
    """Immutable Kaplan–Meier curve with log-scale Greenwood intervals."""

    time: tuple[float, ...]
    strata: tuple[str, ...]
    strata_levels: tuple[str, ...]
    n_risk: tuple[float, ...]
    n_event: tuple[float, ...]
    n_censor: tuple[float, ...]
    survival: tuple[float, ...]
    standard_error: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    confidence_level: float
    n_observations: int

    def predict(
        self, times: Iterable[float], *, stratum: str | None = None
    ) -> tuple[float, ...]:
        """Evaluate the right-continuous Kaplan–Meier step function."""
        requested = _validate_prediction_times(times)
        if stratum is None:
            if len(self.strata_levels) != 1:
                raise InputValidationError(
                    "stratum is required when predicting a stratified curve"
                )
            stratum = self.strata_levels[0]
        if stratum not in self.strata_levels:
            raise InputValidationError("prediction stratum was not fitted")
        observed = np.asarray(
            tuple(
                time
                for time, label in zip(self.time, self.strata, strict=True)
                if label == stratum
            ),
            dtype=np.float64,
        )
        survival = np.asarray(
            tuple(
                value
                for value, label in zip(self.survival, self.strata, strict=True)
                if label == stratum
            ),
            dtype=np.float64,
        )
        indices = (
            np.searchsorted(  # pyright: ignore[reportUnknownMemberType]
                observed, requested, side="right"
            )
            - 1
        )
        values = np.where(  # pyright: ignore[reportUnknownMemberType]
            indices >= 0, survival[np.maximum(indices, 0)], 1.0
        )
        return _vector(values)

    def predict_curve(
        self,
        times: Iterable[float] | None = None,
        *,
        strata: Iterable[str] | None = None,
    ) -> SurvivalCurveResult:
        """Return structured Kaplan–Meier curves for selected strata."""
        requested = (
            np.asarray((0.0, *sorted(set(self.time))), dtype=np.float64)
            if times is None
            else _validate_prediction_times(times)
        )
        if any(
            later <= earlier
            for earlier, later in zip(requested[:-1], requested[1:], strict=True)
        ):
            raise InputValidationError(
                "curve prediction times must be strictly increasing"
            )
        prediction_strata = self.strata_levels if strata is None else tuple(strata)
        if not prediction_strata or any(
            value not in self.strata_levels for value in prediction_strata
        ):
            raise InputValidationError("prediction strata must match fitted strata")
        return SurvivalCurveResult(
            times=_vector(requested),
            strata=prediction_strata,
            survival=tuple(
                self.predict(requested, stratum=stratum)
                for stratum in prediction_strata
            ),
            linear_predictors=None,
        )

    def predict_quantile(
        self,
        probabilities: Iterable[float] = (0.5,),
        *,
        strata: Iterable[str] | None = None,
        interpolation: SurvivalInterpolation = "step",
    ) -> tuple[tuple[float | None, ...], ...]:
        """Predict Kaplan–Meier event-time CDF quantiles by stratum."""
        requested = _validate_probabilities(probabilities)
        interpolation = _validate_interpolation(interpolation)
        prediction_strata = self.strata_levels if strata is None else tuple(strata)
        if not prediction_strata or any(
            value not in self.strata_levels for value in prediction_strata
        ):
            raise InputValidationError("prediction strata must match fitted strata")
        rows: list[tuple[float | None, ...]] = []
        for stratum in prediction_strata:
            mask = tuple(value == stratum for value in self.strata)
            times = np.asarray(
                tuple(time for time, keep in zip(self.time, mask, strict=True) if keep),
                dtype=np.float64,
            )
            survival = np.asarray(
                tuple(
                    value
                    for value, keep in zip(self.survival, mask, strict=True)
                    if keep
                ),
                dtype=np.float64,
            )
            rows.append(
                _kaplan_meier_quantiles(times, survival, requested, interpolation)
            )
        return tuple(rows)

    def predict_mean(
        self,
        *,
        restricted_time: float,
        strata: Iterable[str] | None = None,
        interpolation: SurvivalInterpolation = "step",
    ) -> tuple[float, ...]:
        """Predict restricted Kaplan–Meier mean survival by stratum."""
        horizon = _validate_restricted_time(restricted_time)
        interpolation = _validate_interpolation(interpolation)
        prediction_strata = self.strata_levels if strata is None else tuple(strata)
        if not prediction_strata or any(
            value not in self.strata_levels for value in prediction_strata
        ):
            raise InputValidationError("prediction strata must match fitted strata")
        values: list[float] = []
        for stratum in prediction_strata:
            mask = tuple(value == stratum for value in self.strata)
            times = np.asarray(
                tuple(time for time, keep in zip(self.time, mask, strict=True) if keep),
                dtype=np.float64,
            )
            survival = np.asarray(
                tuple(
                    value
                    for value, keep in zip(self.survival, mask, strict=True)
                    if keep
                ),
                dtype=np.float64,
            )
            values.append(
                _restricted_curve_mean(times, survival, horizon, interpolation)
            )
        return tuple(values)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned result document."""
        return {
            "schema_version": NONPARAMETRIC_SCHEMA_VERSION,
            "estimator": "kaplan-meier",
            "time": list(self.time),
            "strata": list(self.strata),
            "strata_levels": list(self.strata_levels),
            "n_risk": list(self.n_risk),
            "n_event": list(self.n_event),
            "n_censor": list(self.n_censor),
            "survival": list(self.survival),
            "standard_error": list(self.standard_error),
            "lower": list(self.lower),
            "upper": list(self.upper),
            "confidence_level": self.confidence_level,
            "n_observations": self.n_observations,
        }

    def to_json(self) -> str:
        """Serialize the curve as canonical non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical result document."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> NonparametricSurvivalResult:
        """Reconstruct a Kaplan–Meier result from an exact-version document."""
        data = _result_object_any(
            document,
            {NONPARAMETRIC_SCHEMA_VERSION, NONPARAMETRIC_V1_SCHEMA_VERSION},
        )
        if data["schema_version"] == NONPARAMETRIC_V1_SCHEMA_VERSION:
            data = _migrate_nonparametric_v1(data)
        required = {
            "schema_version",
            "estimator",
            "time",
            "strata",
            "strata_levels",
            "n_risk",
            "n_event",
            "n_censor",
            "survival",
            "standard_error",
            "lower",
            "upper",
            "confidence_level",
            "n_observations",
        }
        _exact_keys(data, required)
        if data["estimator"] != "kaplan-meier":
            raise InputValidationError("invalid nonparametric estimator")
        times = _read_vector(data["time"])
        size = len(times)
        curve_strata = _read_names_with_duplicates(data["strata"], size)
        strata_levels = _read_names(data["strata_levels"])
        risk = _read_nonnegative_vector(data["n_risk"], size)
        events = _read_nonnegative_vector(data["n_event"], size)
        censor = _read_nonnegative_vector(data["n_censor"], size)
        survival = _read_vector(data["survival"], size)
        standard_error = _read_vector(data["standard_error"], size)
        lower = _read_vector(data["lower"], size)
        upper = _read_vector(data["upper"], size)
        confidence = _read_probability(data["confidence_level"])
        observations = _read_positive_integer(data["n_observations"])
        if (
            any(value not in strata_levels for value in curve_strata)
            or any(value <= 0.0 for value in times)
            or any(value < 0.0 for value in standard_error)
            or any(
                observed + censored > at_risk
                for at_risk, observed, censored in zip(
                    risk, events, censor, strict=True
                )
            )
            or not _valid_stratified_curve(
                times, tuple(1.0 - value for value in survival), curve_strata
            )
            or any(
                not 0.0 <= low <= value <= high <= 1.0
                for low, value, high in zip(lower, survival, upper, strict=True)
            )
        ):
            raise InputValidationError("inconsistent nonparametric result document")
        return cls(
            times,
            curve_strata,
            strata_levels,
            risk,
            events,
            censor,
            survival,
            standard_error,
            lower,
            upper,
            confidence,
            observations,
        )

    @classmethod
    def from_json(cls, value: str) -> NonparametricSurvivalResult:
        """Reconstruct a Kaplan–Meier result from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="nonparametric result"))


def _cox_terms(
    beta: FloatVector,
    times: FloatVector,
    events: IntVector,
    features: FloatMatrix,
    method: CoxMethod,
    entry: FloatVector,
    strata: IntVector,
    weights: FloatVector,
    offsets: FloatVector,
) -> tuple[float, FloatVector, FloatMatrix]:
    predictor = features @ beta + offsets
    exponential = np.exp(
        np.clip(  # pyright: ignore[reportUnknownMemberType]
            predictor, -700.0, 700.0
        )
    )
    width = features.shape[1]
    log_likelihood = 0.0
    score = np.zeros(width, dtype=np.float64)
    hessian = np.zeros((width, width), dtype=np.float64)
    if np.all(entry == 0.0):  # pyright: ignore[reportUnknownMemberType]
        return _cox_terms_without_delayed_entry(
            predictor,
            exponential,
            times,
            events,
            features,
            method,
            strata,
            weights,
        )
    for stratum in range(int(np.max(strata)) + 1):
        stratum_mask = strata == stratum
        event_times = np.unique(  # pyright: ignore[reportUnknownMemberType]
            times[stratum_mask & (events == 1)]
        )
        for event_time in event_times:
            event_mask = stratum_mask & (times == event_time) & (events == 1)
            risk_mask = stratum_mask & (entry < event_time) & (times >= event_time)
            event_features = features[event_mask]
            event_weights = weights[event_mask]
            event_risk = exponential[event_mask] * event_weights
            risk_features = features[risk_mask]
            risk_weighted = exponential[risk_mask] * weights[risk_mask]
            event_count = int(
                np.count_nonzero(  # pyright: ignore[reportUnknownMemberType]
                    event_mask
                )
            )
            death_weight = float(np.sum(event_weights))
            risk_zero = float(np.sum(risk_weighted))
            risk_one = np.sum(risk_weighted[:, None] * risk_features, axis=0)
            risk_two = risk_features.T @ (risk_weighted[:, None] * risk_features)
            event_zero = float(np.sum(event_risk))
            event_one = np.sum(event_risk[:, None] * event_features, axis=0)
            event_two = event_features.T @ (event_risk[:, None] * event_features)
            log_likelihood += float(np.sum(event_weights * predictor[event_mask]))
            score += np.sum(event_weights[:, None] * event_features, axis=0)
            steps = event_count if method == "efron" else 1
            multiplier = (
                death_weight / event_count if method == "efron" else death_weight
            )
            for index in range(steps):
                fraction = index / event_count if method == "efron" else 0.0
                denominator = risk_zero - fraction * event_zero
                first = risk_one - fraction * event_one
                second = risk_two - fraction * event_two
                log_likelihood -= multiplier * math.log(denominator)
                mean = first / denominator
                score -= multiplier * mean
                hessian -= multiplier * (second / denominator - np.outer(mean, mean))
    return log_likelihood, score, hessian


def _cox_terms_without_delayed_entry(
    predictor: FloatVector,
    exponential: FloatVector,
    times: FloatVector,
    events: IntVector,
    features: FloatMatrix,
    method: CoxMethod,
    strata: IntVector,
    weights: FloatVector,
) -> tuple[float, FloatVector, FloatMatrix]:
    """Evaluate Cox terms from nested risk sets with bounded workspace.

    Small risk-moment arrays use vectorized suffix aggregates. Above the fixed
    workspace limit, a descending sweep keeps memory quadratic in predictor
    count rather than rows times predictor count squared. Delayed-entry fits
    retain the general implementation because their risk sets are not nested.
    """
    width = features.shape[1]
    if features.shape[0] * width * width <= 2_048:
        return _cox_terms_from_suffix_aggregates(
            predictor,
            exponential,
            times,
            events,
            features,
            method,
            strata,
            weights,
        )
    log_likelihood = 0.0
    score = np.zeros(width, dtype=np.float64)
    hessian = np.zeros((width, width), dtype=np.float64)
    for stratum in range(int(np.max(strata)) + 1):
        rows = np.flatnonzero(  # pyright: ignore[reportUnknownMemberType]
            strata == stratum
        )
        order = rows[
            np.argsort(  # pyright: ignore[reportUnknownMemberType]
                times[rows], kind="stable"
            )
        ][::-1]
        ordered_times = times[order]
        ordered_features = features[order]
        ordered_weights = weights[order]
        ordered_risk = exponential[order] * ordered_weights
        ordered_events = events[order]
        ordered_predictor = predictor[order]
        risk_zero = 0.0
        risk_one = np.zeros(width, dtype=np.float64)
        risk_two = np.zeros((width, width), dtype=np.float64)
        start = 0
        while start < ordered_times.size:
            stop = start + 1
            while (
                stop < ordered_times.size
                and ordered_times[stop] == ordered_times[start]
            ):
                stop += 1
            block_features = ordered_features[start:stop]
            block_risk = ordered_risk[start:stop]
            risk_zero += float(np.sum(block_risk))
            risk_one += np.sum(block_risk[:, None] * block_features, axis=0)
            risk_two += block_features.T @ (block_risk[:, None] * block_features)

            event_mask = ordered_events[start:stop] == 1
            event_count = int(
                np.count_nonzero(  # pyright: ignore[reportUnknownMemberType]
                    event_mask
                )
            )
            if event_count == 0:
                start = stop
                continue
            event_features = block_features[event_mask]
            event_weights = ordered_weights[start:stop][event_mask]
            event_risk = block_risk[event_mask]
            event_one = np.sum(event_risk[:, None] * event_features, axis=0)
            event_two = event_features.T @ (event_risk[:, None] * event_features)
            death_weight = float(np.sum(event_weights))
            event_zero = float(np.sum(event_risk))
            log_likelihood += float(
                np.sum(event_weights * ordered_predictor[start:stop][event_mask])
            )
            score += np.sum(event_weights[:, None] * event_features, axis=0)
            steps = event_count if method == "efron" else 1
            multiplier = (
                death_weight / event_count if method == "efron" else death_weight
            )
            for index in range(steps):
                fraction = index / event_count if method == "efron" else 0.0
                denominator = risk_zero - fraction * event_zero
                first = risk_one - fraction * event_one
                second = risk_two - fraction * event_two
                log_likelihood -= multiplier * math.log(denominator)
                mean = first / denominator
                score -= multiplier * mean
                hessian -= multiplier * (second / denominator - np.outer(mean, mean))
            start = stop
    return log_likelihood, score, hessian


def _cox_terms_from_suffix_aggregates(
    predictor: FloatVector,
    exponential: FloatVector,
    times: FloatVector,
    events: IntVector,
    features: FloatMatrix,
    method: CoxMethod,
    strata: IntVector,
    weights: FloatVector,
) -> tuple[float, FloatVector, FloatMatrix]:
    """Vectorize nested risk moments within the fixed workspace limit."""
    width = features.shape[1]
    log_likelihood = 0.0
    score = np.zeros(width, dtype=np.float64)
    hessian = np.zeros((width, width), dtype=np.float64)
    for stratum in range(int(np.max(strata)) + 1):
        rows = np.flatnonzero(  # pyright: ignore[reportUnknownMemberType]
            strata == stratum
        )
        order = rows[
            np.argsort(  # pyright: ignore[reportUnknownMemberType]
                times[rows], kind="stable"
            )
        ]
        ordered_times = times[order]
        ordered_features = features[order]
        ordered_weights = weights[order]
        ordered_risk = exponential[order] * ordered_weights
        risk_zero = np.cumsum(  # pyright: ignore[reportUnknownMemberType]
            ordered_risk[::-1]
        )[::-1]
        risk_one = np.cumsum(  # pyright: ignore[reportUnknownMemberType]
            (ordered_risk[:, None] * ordered_features)[::-1], axis=0
        )[::-1]
        weighted_outer = (
            ordered_risk[:, None, None]
            * ordered_features[:, :, None]
            * ordered_features[:, None, :]
        )
        risk_two = np.cumsum(  # pyright: ignore[reportUnknownMemberType]
            weighted_outer[::-1], axis=0
        )[::-1]

        event_positions = np.flatnonzero(  # pyright: ignore[reportUnknownMemberType]
            events[order] == 1
        )
        event_times, event_groups = np.unique(  # pyright: ignore[reportUnknownMemberType]
            ordered_times[event_positions], return_inverse=True
        )
        group_count = event_times.size
        event_count = np.bincount(event_groups, minlength=group_count)
        event_weights = ordered_weights[event_positions]
        event_risk = ordered_risk[event_positions]
        event_features = ordered_features[event_positions]
        death_weight = np.bincount(
            event_groups, weights=event_weights, minlength=group_count
        )
        event_zero = np.bincount(
            event_groups, weights=event_risk, minlength=group_count
        )
        event_one = np.zeros((group_count, width), dtype=np.float64)
        np.add.at(  # pyright: ignore[reportUnknownMemberType]
            event_one, event_groups, event_risk[:, None] * event_features
        )
        event_two = np.zeros((group_count, width, width), dtype=np.float64)
        np.add.at(  # pyright: ignore[reportUnknownMemberType]
            event_two,
            event_groups,
            event_risk[:, None, None]
            * event_features[:, :, None]
            * event_features[:, None, :],
        )

        log_likelihood += float(
            np.sum(event_weights * predictor[order[event_positions]])
        )
        score += np.sum(event_weights[:, None] * event_features, axis=0)
        for group, event_time in enumerate(_vector(event_times)):
            risk_start = int(
                np.searchsorted(  # pyright: ignore[reportUnknownMemberType]
                    ordered_times, event_time, side="left"
                )
            )
            steps = int(event_count[group]) if method == "efron" else 1
            multiplier = (
                float(death_weight[group]) / steps
                if method == "efron"
                else float(death_weight[group])
            )
            for index in range(steps):
                fraction = index / steps if method == "efron" else 0.0
                denominator = float(risk_zero[risk_start]) - (
                    fraction * float(event_zero[group])
                )
                first = risk_one[risk_start] - fraction * event_one[group]
                second = risk_two[risk_start] - fraction * event_two[group]
                log_likelihood -= multiplier * math.log(denominator)
                mean = first / denominator
                score -= multiplier * mean
                hessian -= multiplier * (second / denominator - np.outer(mean, mean))
    return log_likelihood, score, hessian


def _maximize_cox(
    times: FloatVector,
    events: IntVector,
    features: FloatMatrix,
    method: CoxMethod,
    entry: FloatVector,
    strata: IntVector,
    weights: FloatVector,
    offsets: FloatVector,
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[FloatVector, FloatMatrix, float, float, int]:
    beta = np.zeros(features.shape[1], dtype=np.float64)
    null_log_likelihood, _, _ = _cox_terms(
        beta, times, events, features, method, entry, strata, weights, offsets
    )
    log_likelihood = null_log_likelihood
    for iteration in range(1, max_iterations + 1):
        log_likelihood, score, hessian = _cox_terms(
            beta, times, events, features, method, entry, strata, weights, offsets
        )
        information = -hessian
        try:
            step = np.linalg.solve(information, score)
        except np.linalg.LinAlgError as error:
            raise RankDeficiencyError("Cox information matrix is singular") from error
        scale = 1.0
        accepted = False
        candidate = beta.copy()
        candidate_log_likelihood = log_likelihood
        while scale >= 2.0**-30:
            candidate = beta + scale * step
            candidate_log_likelihood, _, _ = _cox_terms(
                candidate,
                times,
                events,
                features,
                method,
                entry,
                strata,
                weights,
                offsets,
            )
            if candidate_log_likelihood >= log_likelihood:
                accepted = True
                break
            scale *= 0.5
        if not accepted:
            raise ConvergenceError("Cox step halving failed")
        relative_change = abs(
            (candidate_log_likelihood - log_likelihood) / max(abs(log_likelihood), 1.0)
        )
        if relative_change <= tolerance:
            try:
                covariance = np.linalg.inv(-hessian)
            except np.linalg.LinAlgError as error:
                raise RankDeficiencyError(
                    "Cox information matrix is singular"
                ) from error
            return beta, covariance, null_log_likelihood, log_likelihood, iteration
        beta = candidate
        log_likelihood = candidate_log_likelihood
    raise ConvergenceError("Cox fit did not converge")


def _cox_baseline(
    result_beta: FloatVector,
    times: FloatVector,
    events: IntVector,
    centered_features: FloatMatrix,
    method: CoxMethod,
    entry: FloatVector,
    strata: IntVector,
    strata_levels: tuple[str, ...],
    weights: FloatVector,
    offsets: FloatVector,
) -> tuple[tuple[str, ...], FloatVector, FloatVector, FloatVector]:
    predictor = centered_features @ result_beta + offsets
    exponential = np.exp(
        np.clip(  # pyright: ignore[reportUnknownMemberType]
            predictor, -700.0, 700.0
        )
    )
    labels: list[str] = []
    times_out: list[float] = []
    increments: list[float] = []
    cumulative: list[float] = []
    if np.all(entry == 0.0):  # pyright: ignore[reportUnknownMemberType]
        for stratum, label in enumerate(strata_levels):
            rows = np.flatnonzero(  # pyright: ignore[reportUnknownMemberType]
                strata == stratum
            )
            order = rows[
                np.argsort(  # pyright: ignore[reportUnknownMemberType]
                    times[rows], kind="stable"
                )
            ]
            ordered_times = times[order]
            ordered_risk = exponential[order] * weights[order]
            risk_zero = np.cumsum(  # pyright: ignore[reportUnknownMemberType]
                ordered_risk[::-1]
            )[::-1]
            event_positions = np.flatnonzero(  # pyright: ignore[reportUnknownMemberType]
                events[order] == 1
            )
            event_times, event_groups = np.unique(  # pyright: ignore[reportUnknownMemberType]
                ordered_times[event_positions], return_inverse=True
            )
            event_count = np.bincount(event_groups, minlength=event_times.size)
            death_weight = np.bincount(
                event_groups,
                weights=weights[order[event_positions]],
                minlength=event_times.size,
            )
            event_zero = np.bincount(
                event_groups,
                weights=ordered_risk[event_positions],
                minlength=event_times.size,
            )
            total = 0.0
            for group, event_time in enumerate(_vector(event_times)):
                risk_start = int(
                    np.searchsorted(  # pyright: ignore[reportUnknownMemberType]
                        ordered_times, event_time, side="left"
                    )
                )
                denominator = float(risk_zero[risk_start])
                deaths = int(event_count[group])
                if method == "breslow":
                    increment = float(death_weight[group]) / denominator
                else:
                    average_weight = float(death_weight[group]) / deaths
                    increment = sum(
                        average_weight
                        / (denominator - (index / deaths) * float(event_zero[group]))
                        for index in range(deaths)
                    )
                total += increment
                labels.append(label)
                times_out.append(float(event_time))
                increments.append(increment)
                cumulative.append(total)
        return (
            tuple(labels),
            np.asarray(times_out, dtype=np.float64),
            np.asarray(increments, dtype=np.float64),
            np.asarray(cumulative, dtype=np.float64),
        )
    for stratum, label in enumerate(strata_levels):
        stratum_mask = strata == stratum
        event_times = np.unique(  # pyright: ignore[reportUnknownMemberType]
            times[stratum_mask & (events == 1)]
        )
        total = 0.0
        for event_time in event_times:
            event_mask = stratum_mask & (times == event_time) & (events == 1)
            risk_mask = stratum_mask & (entry < event_time) & (times >= event_time)
            risk_zero = float(np.sum(exponential[risk_mask] * weights[risk_mask]))
            event_zero = float(np.sum(exponential[event_mask] * weights[event_mask]))
            event_count = int(
                np.count_nonzero(  # pyright: ignore[reportUnknownMemberType]
                    event_mask
                )
            )
            death_weight = float(np.sum(weights[event_mask]))
            if method == "breslow":
                increment = death_weight / risk_zero
            else:
                average_weight = death_weight / event_count
                increment = sum(
                    average_weight / (risk_zero - (index / event_count) * event_zero)
                    for index in range(event_count)
                )
            total += increment
            labels.append(label)
            times_out.append(float(event_time))
            increments.append(increment)
            cumulative.append(total)
    return (
        tuple(labels),
        np.asarray(times_out, dtype=np.float64),
        np.asarray(increments, dtype=np.float64),
        np.asarray(cumulative, dtype=np.float64),
    )


def fit_cph(
    times: Iterable[float],
    events: Iterable[int | bool],
    features: Iterable[Iterable[float]],
    *,
    method: CoxMethod = "efron",
    feature_names: Iterable[str] | None = None,
    entry_times: Iterable[float] | None = None,
    strata: Iterable[str] | None = None,
    weights: Iterable[float] | None = None,
    offsets: Iterable[float] | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-9,
) -> CoxResult:
    """Fit a weighted counting-process Cox model with optional strata/offsets."""
    if method not in {"efron", "breslow"}:
        raise InputValidationError("method must be 'efron' or 'breslow'")
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, Integral)
        or not 1 <= max_iterations <= 1_000_000
        or not _finite_number(tolerance)
        or not 0.0 < tolerance < 1.0
    ):
        raise InputValidationError("invalid Cox convergence controls")
    time_array, event_array = _as_times_events(times, events)
    feature_array = _as_features(features, time_array.size)
    names = _feature_names(feature_array.shape[1], feature_names)
    entry_array = _as_entry_times(entry_times, time_array)
    _, strata_levels, strata_codes = _as_strata(strata, time_array.size)
    weight_array = _as_optional_numeric(
        weights, time_array.size, name="weights", default=1.0, positive=True
    )
    offset_array = _as_optional_numeric(
        offsets, time_array.size, name="offsets", default=0.0
    )
    beta, covariance, null_log_likelihood, log_likelihood, iterations = _maximize_cox(
        time_array,
        event_array,
        feature_array,
        method,
        entry_array,
        strata_codes,
        weight_array,
        offset_array,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    # Match coxph/cph reference centering: case weights affect the likelihood,
    # while the reported linear-predictor origin uses the unweighted column means.
    means = np.mean(feature_array, axis=0)
    centered = feature_array - means
    baseline_strata, event_times, hazard, baseline = _cox_baseline(
        beta,
        time_array,
        event_array,
        centered,
        method,
        entry_array,
        strata_codes,
        strata_levels,
        weight_array,
        offset_array,
    )
    return CoxResult(
        method=method,
        feature_names=names,
        coefficients=_vector(beta),
        covariance=_matrix_rows(covariance),
        feature_means=_vector(means),
        linear_predictors=_vector(centered @ beta + offset_array),
        log_likelihood=(null_log_likelihood, log_likelihood),
        baseline_times=_vector(event_times),
        baseline_cumulative_hazard=_vector(baseline),
        baseline_strata=baseline_strata,
        baseline_hazard=_vector(hazard),
        baseline_survival=_vector(np.exp(-baseline)),
        strata_levels=strata_levels,
        iterations=iterations,
        n_observations=time_array.size,
    )


def _aft_endpoint_terms(
    log_time: FloatVector, location: FloatVector, scales: FloatVector
) -> tuple[
    FloatVector, FloatVector, FloatVector, FloatVector, FloatVector, FloatVector
]:
    """Return survival and first/second derivatives by location and log-scale."""
    z = (log_time - location) / scales
    hazard = np.exp(
        np.clip(z, -745.0, 100.0)  # pyright: ignore[reportUnknownMemberType]
    )
    survival = np.exp(-hazard)
    eta = survival * hazard / scales
    eta_eta = survival * (hazard * hazard - hazard) / (scales * scales)
    log_scale = survival * hazard * z
    log_scale_log_scale = survival * ((hazard * z) ** 2 - hazard * (z * z + z))
    eta_log_scale = survival * hazard * (hazard * z - z - 1.0) / scales
    return (
        survival,
        eta,
        eta_eta,
        log_scale,
        log_scale_log_scale,
        eta_log_scale,
    )


def _aft_terms(
    parameters: FloatVector,
    lower_log_times: FloatVector,
    upper_log_times: FloatVector,
    censoring: IntVector,
    design: FloatMatrix,
    distribution: ParametricDistribution,
    strata: IntVector,
    weights: FloatVector,
    offsets: FloatVector,
    scale_count: int,
) -> tuple[float, FloatVector, FloatMatrix]:
    width = design.shape[1]
    beta = parameters[:width]
    if distribution == "exponential":
        log_scales = np.zeros(1, dtype=np.float64)
    else:
        log_scales = parameters[width : width + scale_count]
    row_log_scales = log_scales[strata]
    scales = np.exp(row_log_scales)
    location = design @ beta + offsets
    row_log_likelihood = np.empty(design.shape[0], dtype=np.float64)
    eta_score = np.empty(design.shape[0], dtype=np.float64)
    eta_hessian = np.empty(design.shape[0], dtype=np.float64)
    scale_score = np.empty(design.shape[0], dtype=np.float64)
    scale_hessian = np.empty(design.shape[0], dtype=np.float64)
    eta_scale_hessian = np.empty(design.shape[0], dtype=np.float64)

    exact = censoring == EXACT_CENSORING
    if bool(np.any(exact)):  # pyright: ignore[reportUnknownMemberType]
        log_time = lower_log_times[exact]
        row_scale = scales[exact]
        z = (log_time - location[exact]) / row_scale
        hazard = np.exp(
            np.clip(z, -745.0, 100.0)  # pyright: ignore[reportUnknownMemberType]
        )
        row_log_likelihood[exact] = z - row_log_scales[exact] - log_time - hazard
        eta_score[exact] = (hazard - 1.0) / row_scale
        eta_hessian[exact] = -hazard / (row_scale * row_scale)
        scale_score[exact] = -z - 1.0 + hazard * z
        scale_hessian[exact] = z - hazard * (z * z + z)
        eta_scale_hessian[exact] = (1.0 - hazard * (1.0 + z)) / row_scale

    right = censoring == RIGHT_CENSORING
    if bool(np.any(right)):  # pyright: ignore[reportUnknownMemberType]
        row_scale = scales[right]
        z = (lower_log_times[right] - location[right]) / row_scale
        hazard = np.exp(
            np.clip(z, -745.0, 100.0)  # pyright: ignore[reportUnknownMemberType]
        )
        row_log_likelihood[right] = -hazard
        eta_score[right] = hazard / row_scale
        eta_hessian[right] = -hazard / (row_scale * row_scale)
        scale_score[right] = hazard * z
        scale_hessian[right] = -hazard * (z * z + z)
        eta_scale_hessian[right] = -hazard * (1.0 + z) / row_scale

    tiny = np.finfo(np.float64).tiny
    left = censoring == LEFT_CENSORING
    if bool(np.any(left)):  # pyright: ignore[reportUnknownMemberType]
        endpoint = _aft_endpoint_terms(
            upper_log_times[left], location[left], scales[left]
        )
        survival, s_eta, s_eta_eta, s_scale, s_scale_scale, s_eta_scale = endpoint
        probability = np.maximum(1.0 - survival, tiny)
        p_eta = -s_eta
        p_eta_eta = -s_eta_eta
        p_scale = -s_scale
        p_scale_scale = -s_scale_scale
        p_eta_scale = -s_eta_scale
        row_log_likelihood[left] = np.log(probability)
        eta_score[left] = p_eta / probability
        eta_hessian[left] = p_eta_eta / probability - (p_eta / probability) ** 2
        scale_score[left] = p_scale / probability
        scale_hessian[left] = p_scale_scale / probability - (p_scale / probability) ** 2
        eta_scale_hessian[left] = p_eta_scale / probability - p_eta * p_scale / (
            probability * probability
        )

    interval = censoring == INTERVAL_CENSORING
    if bool(np.any(interval)):  # pyright: ignore[reportUnknownMemberType]
        lower_endpoint = _aft_endpoint_terms(
            lower_log_times[interval], location[interval], scales[interval]
        )
        upper_endpoint = _aft_endpoint_terms(
            upper_log_times[interval], location[interval], scales[interval]
        )
        probability = np.maximum(lower_endpoint[0] - upper_endpoint[0], tiny)
        p_eta = lower_endpoint[1] - upper_endpoint[1]
        p_eta_eta = lower_endpoint[2] - upper_endpoint[2]
        p_scale = lower_endpoint[3] - upper_endpoint[3]
        p_scale_scale = lower_endpoint[4] - upper_endpoint[4]
        p_eta_scale = lower_endpoint[5] - upper_endpoint[5]
        row_log_likelihood[interval] = np.log(probability)
        eta_score[interval] = p_eta / probability
        eta_hessian[interval] = p_eta_eta / probability - (p_eta / probability) ** 2
        scale_score[interval] = p_scale / probability
        scale_hessian[interval] = (
            p_scale_scale / probability - (p_scale / probability) ** 2
        )
        eta_scale_hessian[interval] = p_eta_scale / probability - p_eta * p_scale / (
            probability * probability
        )

    log_likelihood = float(np.sum(weights * row_log_likelihood))
    score_beta = design.T @ (weights * eta_score)
    hessian_beta = design.T @ ((weights * eta_hessian)[:, None] * design)
    if distribution == "exponential":
        return log_likelihood, score_beta, hessian_beta
    score_scales = np.zeros(scale_count, dtype=np.float64)
    cross = np.zeros((width, scale_count), dtype=np.float64)
    hessian_scales = np.zeros(scale_count, dtype=np.float64)
    for stratum in range(scale_count):
        mask = strata == stratum
        score_scales[stratum] = float(np.sum(weights[mask] * scale_score[mask]))
        cross[:, stratum] = design[mask].T @ (weights[mask] * eta_scale_hessian[mask])
        hessian_scales[stratum] = float(np.sum(weights[mask] * scale_hessian[mask]))
    score = np.concatenate(  # pyright: ignore[reportUnknownMemberType]
        (score_beta, score_scales)
    )
    hessian = np.zeros((width + scale_count, width + scale_count), dtype=np.float64)
    hessian[:width, :width] = hessian_beta
    hessian[:width, width:] = cross
    hessian[width:, :width] = cross.T
    hessian[width:, width:] = np.diag(  # pyright: ignore[reportUnknownMemberType]
        hessian_scales
    )
    return log_likelihood, score, hessian


def _maximize_aft(
    lower_log_times: FloatVector,
    upper_log_times: FloatVector,
    representative_log_times: FloatVector,
    censoring: IntVector,
    design: FloatMatrix,
    distribution: ParametricDistribution,
    strata: IntVector,
    weights: FloatVector,
    offsets: FloatVector,
    scale_count: int,
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[FloatVector, FloatMatrix, float, int]:
    weighted_design = design * np.sqrt(weights)[:, None]
    weighted_response = (representative_log_times - offsets) * np.sqrt(weights)
    initial_beta, _, _, _ = np.linalg.lstsq(
        weighted_design, weighted_response, rcond=None
    )
    if distribution == "exponential":
        parameters = initial_beta
    else:
        residual = representative_log_times - design @ initial_beta - offsets
        initial_scales = tuple(
            max(
                math.sqrt(
                    float(
                        np.average(
                            residual[strata == stratum] ** 2,
                            weights=weights[strata == stratum],
                        )
                    )
                ),
                0.25,
            )
            for stratum in range(scale_count)
        )
        parameters = np.concatenate(  # pyright: ignore[reportUnknownMemberType]
            (initial_beta, np.log(np.asarray(initial_scales, dtype=np.float64)))
        )
    log_likelihood = -math.inf
    for iteration in range(1, max_iterations + 1):
        current, score, hessian = _aft_terms(
            parameters,
            lower_log_times,
            upper_log_times,
            censoring,
            design,
            distribution,
            strata,
            weights,
            offsets,
            scale_count,
        )
        information = -hessian
        minimum_eigenvalue = float(np.min(np.linalg.eigvalsh(information)))
        if minimum_eigenvalue <= 0.0:
            diagonal_scale = max(
                float(
                    np.max(
                        np.abs(
                            np.diag(  # pyright: ignore[reportUnknownMemberType]
                                information
                            )
                        )
                    )
                ),
                1.0,
            )
            information = information + np.eye(information.shape[0]) * (
                -minimum_eigenvalue + 1e-8 * diagonal_scale
            )
        try:
            step = np.linalg.solve(information, score)
        except np.linalg.LinAlgError as error:
            raise RankDeficiencyError(
                "parametric information matrix is singular"
            ) from error
        if float(np.max(np.abs(step))) <= tolerance:
            try:
                covariance = np.linalg.inv(-hessian)
            except np.linalg.LinAlgError as error:
                raise RankDeficiencyError(
                    "parametric information matrix is singular"
                ) from error
            return parameters, covariance, current, iteration
        scale = 1.0
        accepted = False
        while scale >= 2.0**-30:
            candidate = parameters + scale * step
            if np.any(  # pyright: ignore[reportUnknownMemberType]
                np.abs(candidate) > 1e6
            ):
                scale *= 0.5
                continue
            if (
                distribution == "weibull"
                and np.any(  # pyright: ignore[reportUnknownMemberType]
                    np.abs(candidate[design.shape[1] :]) > 30.0
                )
            ):
                scale *= 0.5
                continue
            candidate_log_likelihood, _, _ = _aft_terms(
                candidate,
                lower_log_times,
                upper_log_times,
                censoring,
                design,
                distribution,
                strata,
                weights,
                offsets,
                scale_count,
            )
            if math.isfinite(candidate_log_likelihood) and (
                candidate_log_likelihood >= current
            ):
                parameters = candidate
                log_likelihood = candidate_log_likelihood
                accepted = True
                break
            scale *= 0.5
        if not accepted:
            raise ConvergenceError("parametric survival step halving failed")
        if float(np.max(np.abs(scale * step))) <= tolerance:
            _, _, final_hessian = _aft_terms(
                parameters,
                lower_log_times,
                upper_log_times,
                censoring,
                design,
                distribution,
                strata,
                weights,
                offsets,
                scale_count,
            )
            try:
                covariance = np.linalg.inv(-final_hessian)
            except np.linalg.LinAlgError as error:
                raise RankDeficiencyError(
                    "parametric information matrix is singular"
                ) from error
            return parameters, covariance, log_likelihood, iteration
    raise ConvergenceError("parametric survival fit did not converge")


def _aft_response_contract(
    response: SurvivalResponse,
) -> tuple[FloatVector, FloatVector, FloatVector, IntVector]:
    lower_log: list[float] = []
    upper_log: list[float] = []
    representative: list[float] = []
    codes: list[int] = []
    code_by_type = {
        "exact": EXACT_CENSORING,
        "left": LEFT_CENSORING,
        "right": RIGHT_CENSORING,
        "interval": INTERVAL_CENSORING,
    }
    for lower, upper, kind in zip(
        response.lower, response.upper, response.censoring_types, strict=True
    ):
        logged_lower = -math.inf if lower == -math.inf else math.log(lower)
        logged_upper = math.inf if upper == math.inf else math.log(upper)
        lower_log.append(logged_lower)
        upper_log.append(logged_upper)
        if kind == "left":
            representative.append(logged_upper)
        elif kind == "interval":
            representative.append((logged_lower + logged_upper) / 2.0)
        else:
            representative.append(logged_lower)
        codes.append(code_by_type[kind])
    return (
        np.asarray(lower_log, dtype=np.float64),
        np.asarray(upper_log, dtype=np.float64),
        np.asarray(representative, dtype=np.float64),
        np.asarray(codes, dtype=np.int64),
    )


@overload
def fit_psm(
    times: Iterable[float],
    events: Iterable[int | bool],
    features: Iterable[Iterable[float]],
    *,
    distribution: ParametricDistribution = "weibull",
    feature_names: Iterable[str] | None = None,
    strata: Iterable[str] | None = None,
    weights: Iterable[float] | None = None,
    offsets: Iterable[float] | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-10,
) -> ParametricSurvivalResult: ...


@overload
def fit_psm(
    times: SurvivalResponse,
    events: Iterable[Iterable[float]],
    features: None = None,
    *,
    distribution: ParametricDistribution = "weibull",
    feature_names: Iterable[str] | None = None,
    strata: Iterable[str] | None = None,
    weights: Iterable[float] | None = None,
    offsets: Iterable[float] | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-10,
) -> ParametricSurvivalResult: ...


def fit_psm(
    times: Iterable[float] | SurvivalResponse,
    events: Iterable[int | bool] | Iterable[Iterable[float]],
    features: Iterable[Iterable[float]] | None = None,
    *,
    distribution: ParametricDistribution = "weibull",
    feature_names: Iterable[str] | None = None,
    strata: Iterable[str] | None = None,
    weights: Iterable[float] | None = None,
    offsets: Iterable[float] | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-10,
) -> ParametricSurvivalResult:
    """Fit a weighted exact/right or general interval-censored AFT model."""
    if distribution not in {"weibull", "exponential"}:
        raise InputValidationError("unsupported parametric survival distribution")
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, Integral)
        or not 1 <= max_iterations <= 1_000_000
        or not _finite_number(tolerance)
        or not 0.0 < tolerance < 1.0
    ):
        raise InputValidationError("invalid parametric convergence controls")
    if isinstance(times, SurvivalResponse):
        if features is not None:
            raise InputValidationError(
                "interval-censored fit accepts features as its second argument"
            )
        response = times
        feature_values = cast(Iterable[Iterable[float]], events)
    else:
        if features is None:
            raise InputValidationError(
                "right-censored fit requires times, events, and features"
            )
        time_array, event_array = _as_times_events(
            times, cast(Iterable[int | bool], events)
        )
        response = SurvivalResponse.from_intervals(
            time_array,
            tuple(
                float(time) if event else math.inf
                for time, event in zip(time_array, event_array, strict=True)
            ),
        )
        feature_values = features
    lower_log, upper_log, representative_log, censoring = _aft_response_contract(
        response
    )
    row_count = lower_log.size
    feature_array = _as_features(feature_values, row_count)
    names = _feature_names(feature_array.shape[1], feature_names)
    _, strata_levels, strata_codes = _as_strata(strata, row_count)
    if distribution == "exponential" and len(strata_levels) > 1:
        raise InputValidationError(
            "exponential models have fixed scale and do not support scale strata"
        )
    scale_count = 1 if distribution == "exponential" else len(strata_levels)
    weight_array = _as_optional_numeric(
        weights, row_count, name="weights", default=1.0, positive=True
    )
    offset_array = _as_optional_numeric(offsets, row_count, name="offsets", default=0.0)
    design = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
        (np.ones(row_count), feature_array)
    )
    if np.linalg.matrix_rank(design) < design.shape[1]:
        raise RankDeficiencyError("parametric design must have full column rank")
    parameters, covariance, log_likelihood, iterations = _maximize_aft(
        lower_log,
        upper_log,
        representative_log,
        censoring,
        design,
        distribution,
        strata_codes,
        weight_array,
        offset_array,
        scale_count,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    null_parameters, _, null_log_likelihood, _ = _maximize_aft(
        lower_log,
        upper_log,
        representative_log,
        censoring,
        np.ones((row_count, 1), dtype=np.float64),
        distribution,
        strata_codes,
        weight_array,
        offset_array,
        scale_count,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    del null_parameters
    coefficients = parameters[: design.shape[1]]
    scales = (
        (1.0,)
        if distribution == "exponential"
        else tuple(math.exp(float(value)) for value in parameters[design.shape[1] :])
    )
    scale = scales[0] if len(scales) == 1 else None
    return ParametricSurvivalResult(
        distribution=distribution,
        coefficient_names=("(Intercept)", *names),
        coefficients=_vector(coefficients),
        covariance=_matrix_rows(covariance[: design.shape[1], : design.shape[1]]),
        scale=scale,
        strata_levels=strata_levels,
        scales=scales,
        linear_predictors=_vector(design @ coefficients + offset_array),
        log_likelihood=(null_log_likelihood, log_likelihood),
        iterations=iterations,
        n_observations=row_count,
    )


def fit_npsurv(
    times: Iterable[float],
    events: Iterable[int | bool],
    *,
    confidence_level: float = 0.95,
    entry_times: Iterable[float] | None = None,
    strata: Iterable[str] | None = None,
    weights: Iterable[float] | None = None,
) -> NonparametricSurvivalResult:
    """Compute weighted, stratified Kaplan–Meier counting-process curves."""
    if not 0.0 < confidence_level < 1.0:
        raise InputValidationError("confidence_level must be between zero and one")
    time_array, event_array = _as_times_events(times, events)
    entry_array = _as_entry_times(entry_times, time_array)
    _, strata_levels, strata_codes = _as_strata(strata, time_array.size)
    weight_array = _as_optional_numeric(
        weights, time_array.size, name="weights", default=1.0, positive=True
    )
    z_value = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    curve_strata: list[str] = []
    time_values: list[float] = []
    risk_values: list[float] = []
    event_values: list[float] = []
    censor_values: list[float] = []
    survival_values: list[float] = []
    standard_errors: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    for stratum, label in enumerate(strata_levels):
        stratum_mask = strata_codes == stratum
        unique_times = np.unique(  # pyright: ignore[reportUnknownMemberType]
            time_array[stratum_mask]
        )
        survival = 1.0
        greenwood = 0.0
        for value in unique_times:
            risk_mask = stratum_mask & (entry_array < value) & (time_array >= value)
            at_time = stratum_mask & (time_array == value)
            at_risk = float(np.sum(weight_array[risk_mask]))
            observed = float(np.sum(weight_array[at_time & (event_array == 1)]))
            censored = float(np.sum(weight_array[at_time & (event_array == 0)]))
            if observed:
                survival *= 1.0 - observed / at_risk
                if observed < at_risk:
                    greenwood += observed / (at_risk * (at_risk - observed))
                else:
                    greenwood = 0.0
            standard_error = math.sqrt(greenwood)
            if survival == 0.0:
                low = high = 0.0
            else:
                low = survival * math.exp(-z_value * standard_error)
                high = min(1.0, survival * math.exp(z_value * standard_error))
            curve_strata.append(label)
            time_values.append(float(value))
            risk_values.append(at_risk)
            event_values.append(observed)
            censor_values.append(censored)
            survival_values.append(survival)
            standard_errors.append(standard_error)
            lower.append(low)
            upper.append(high)
    return NonparametricSurvivalResult(
        time=tuple(time_values),
        strata=tuple(curve_strata),
        strata_levels=strata_levels,
        n_risk=tuple(risk_values),
        n_event=tuple(event_values),
        n_censor=tuple(censor_values),
        survival=tuple(survival_values),
        standard_error=tuple(standard_errors),
        lower=tuple(lower),
        upper=tuple(upper),
        confidence_level=float(confidence_level),
        n_observations=time_array.size,
    )


def survival_residuals(
    result: CoxResult | ParametricSurvivalResult,
    times: Iterable[float],
    events: Iterable[int | bool],
    *,
    kind: SurvivalResidualKind = "martingale",
    entry_times: Iterable[float] | None = None,
    strata: Iterable[str] | None = None,
) -> SurvivalResidualResult:
    """Compute supported survival residuals in original training-row order."""
    time_array, event_array = _as_times_events(times, events)
    if time_array.size != result.n_observations:
        raise InputValidationError("residual response must match the fitted row count")
    labels = _prediction_strata(strata, time_array.size, result.strata_levels)
    if isinstance(result, CoxResult):
        if kind not in {"martingale", "deviance"}:
            raise InputValidationError("Cox residuals support martingale and deviance")
        entry_array = _as_entry_times(entry_times, time_array)
        expected: list[float] = []
        for index, label in enumerate(labels):
            stop = np.asarray([time_array[index]], dtype=np.float64)
            start = np.asarray([entry_array[index]], dtype=np.float64)
            cumulative = float(
                result._baseline_at(  # pyright: ignore[reportPrivateUsage]
                    stop, label, result.baseline_cumulative_hazard
                )[0]
                - result._baseline_at(  # pyright: ignore[reportPrivateUsage]
                    start, label, result.baseline_cumulative_hazard
                )[0]
            )
            expected.append(cumulative * math.exp(result.linear_predictors[index]))
        martingale = tuple(
            float(event) - value
            for event, value in zip(event_array, expected, strict=True)
        )
    else:
        if entry_times is not None:
            raise InputValidationError("parametric residuals do not accept entry_times")
        if kind not in {"normalized", "response", "martingale", "deviance"}:
            raise InputValidationError("unsupported parametric survival residual kind")
        scales_by_stratum = dict(zip(result.strata_levels, result.scales, strict=True))
        normalized = tuple(
            (math.log(float(time)) - predictor) / scales_by_stratum[label]
            for time, predictor, label in zip(
                time_array, result.linear_predictors, labels, strict=True
            )
        )
        if kind == "normalized":
            return SurvivalResidualResult(kind, normalized)
        if kind == "response":
            response = tuple(
                math.log(float(time)) - predictor
                for time, predictor in zip(
                    time_array, result.linear_predictors, strict=True
                )
            )
            return SurvivalResidualResult(kind, response)
        martingale = tuple(
            float(event) - math.exp(value)
            for event, value in zip(event_array, normalized, strict=True)
        )
    if kind == "martingale":
        return SurvivalResidualResult(kind, martingale)
    deviance = tuple(
        _deviance_residual(int(event), value)
        for event, value in zip(event_array, martingale, strict=True)
    )
    return SurvivalResidualResult(kind, deviance)


def _valid_stratified_curve(
    times: tuple[float, ...],
    cumulative: tuple[float, ...],
    strata: tuple[str, ...],
    *,
    survival: tuple[float, ...] | None = None,
    increments: tuple[float, ...] | None = None,
) -> bool:
    for label in tuple(dict.fromkeys(strata)):
        indices = tuple(index for index, value in enumerate(strata) if value == label)
        stratum_times = tuple(times[index] for index in indices)
        stratum_cumulative = tuple(cumulative[index] for index in indices)
        if any(
            right <= left
            for left, right in zip(stratum_times[:-1], stratum_times[1:], strict=True)
        ) or any(
            right < left
            for left, right in zip(
                stratum_cumulative[:-1], stratum_cumulative[1:], strict=True
            )
        ):
            return False
        if survival is not None and any(
            not math.isclose(
                survival[index],
                math.exp(-cumulative[index]),
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
            for index in indices
        ):
            return False
        if increments is not None:
            previous = 0.0
            for index in indices:
                if not math.isclose(
                    cumulative[index] - previous,
                    increments[index],
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                ):
                    return False
                previous = cumulative[index]
    return True


def _migrate_cox_v1(data: dict[str, object]) -> dict[str, object]:
    migrated = dict(data)
    cumulative = tuple(
        float(cast(Real, value))
        for value in cast(list[object], data["baseline_cumulative_hazard"])
    )
    previous = 0.0
    increments: list[float] = []
    for value in cumulative:
        increments.append(value - previous)
        previous = value
    migrated.update(
        schema_version=COX_SCHEMA_VERSION,
        baseline_strata=[BASELINE_STRATUM] * len(cumulative),
        baseline_hazard=increments,
        baseline_survival=[math.exp(-value) for value in cumulative],
        strata_levels=[BASELINE_STRATUM],
    )
    return migrated


def _migrate_parametric_v1(data: dict[str, object]) -> dict[str, object]:
    migrated = dict(data)
    scale = data["scale"]
    migrated.update(
        schema_version=PARAMETRIC_SCHEMA_VERSION,
        strata_levels=[BASELINE_STRATUM],
        scales=[scale],
    )
    return migrated


def _migrate_nonparametric_v1(data: dict[str, object]) -> dict[str, object]:
    migrated = dict(data)
    times = cast(list[object], data["time"])
    migrated.update(
        schema_version=NONPARAMETRIC_SCHEMA_VERSION,
        strata=[BASELINE_STRATUM] * len(times),
        strata_levels=[BASELINE_STRATUM],
    )
    return migrated


def _result_object_any(
    document: object, schema_versions: set[str]
) -> dict[str, object]:
    if not isinstance(document, dict):
        raise InputValidationError("result document must be an object")
    result = cast(dict[str, object], document)
    if result.get("schema_version") not in schema_versions:
        raise InputValidationError("unsupported result schema version")
    return result


def _exact_keys(document: dict[str, object], expected: set[str]) -> None:
    if set(document) != expected:
        raise InputValidationError("result document has missing or unknown fields")


def _read_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise InputValidationError("coefficient names must be a nonempty array")
    raw_names = cast(list[object], value)
    if any(not isinstance(name, str) or not name for name in raw_names):
        raise InputValidationError("coefficient names must be non-empty and unique")
    names = tuple(cast(str, name) for name in raw_names)
    if len(set(names)) != len(names):
        raise InputValidationError("coefficient names must be non-empty and unique")
    return names


def _read_names_with_duplicates(value: object, size: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InputValidationError("string vector has the wrong shape")
    raw = cast(list[object], value)
    if len(raw) != size:
        raise InputValidationError("string vector has the wrong shape")
    if any(not isinstance(item, str) or not item for item in raw):
        raise InputValidationError("string vector must contain non-empty strings")
    return tuple(cast(str, item) for item in raw)


def _read_vector(value: object, size: int | None = None) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise InputValidationError("numeric vector has the wrong shape")
    raw_values = cast(list[object], value)
    if size is not None and len(raw_values) != size:
        raise InputValidationError("numeric vector has the wrong shape")
    if not raw_values or not all(_finite_number(item) for item in raw_values):
        raise InputValidationError("numeric vector must be nonempty and finite")
    return tuple(float(cast(Real, item)) for item in raw_values)


def _read_nonnegative_vector(value: object, size: int) -> tuple[float, ...]:
    result = _read_vector(value, size)
    if any(item < 0.0 for item in result):
        raise InputValidationError("numeric vector must be nonnegative")
    return result


def _read_matrix(value: object, size: int) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, list):
        raise InputValidationError("covariance matrix has the wrong shape")
    raw_rows = cast(list[object], value)
    if len(raw_rows) != size:
        raise InputValidationError("covariance matrix has the wrong shape")
    rows = tuple(_read_vector(row, size) for row in raw_rows)
    array = np.asarray(rows, dtype=np.float64)
    if not np.allclose(  # pyright: ignore[reportUnknownMemberType]
        array, array.T, atol=1e-12, rtol=1e-12
    ):
        raise InputValidationError("covariance matrix must be symmetric")
    return rows


def _read_positive_number(value: object) -> float:
    if not _finite_number(value) or float(cast(Real, value)) <= 0.0:
        raise InputValidationError("value must be finite and positive")
    return float(cast(Real, value))


def _read_probability(value: object) -> float:
    result = _read_positive_number(value)
    if result >= 1.0:
        raise InputValidationError("probability must be below one")
    return result


def _read_positive_integer(value: object, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise InputValidationError("count must be a supported integer")
    return value
