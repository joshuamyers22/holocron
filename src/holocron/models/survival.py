"""Owned right-censored survival estimators and result contracts."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Integral, Real
from statistics import NormalDist
from typing import Literal, TypeAlias, cast

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
class SurvivalResidualResult:
    """A named survival residual vector in original training-row order."""

    kind: SurvivalResidualKind
    values: tuple[float, ...]


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


def _aft_terms(
    parameters: FloatVector,
    log_times: FloatVector,
    times: FloatVector,
    events: IntVector,
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
    z = (log_times - design @ beta - offsets) / scales
    hazard = np.exp(
        np.clip(z, -745.0, 600.0)  # pyright: ignore[reportUnknownMemberType]
    )
    observed = events.astype(np.float64)
    log_likelihood = float(
        np.sum(weights * (observed * (z - row_log_scales - np.log(times)) - hazard))
    )
    score_beta = design.T @ (weights * (hazard - observed) / scales)
    hessian_beta = -(
        design.T @ ((weights * hazard / (scales * scales))[:, None] * design)
    )
    if distribution == "exponential":
        return log_likelihood, score_beta, hessian_beta
    score_scales = np.zeros(scale_count, dtype=np.float64)
    cross = np.zeros((width, scale_count), dtype=np.float64)
    hessian_scales = np.zeros(scale_count, dtype=np.float64)
    for stratum in range(scale_count):
        mask = strata == stratum
        score_scales[stratum] = float(
            np.sum(
                weights[mask]
                * (observed[mask] * (-z[mask] - 1.0) + hazard[mask] * z[mask])
            )
        )
        cross[:, stratum] = design[mask].T @ (
            weights[mask]
            * (observed[mask] - hazard[mask] * (1.0 + z[mask]))
            / scales[mask]
        )
        hessian_scales[stratum] = float(
            np.sum(
                weights[mask]
                * (observed[mask] * z[mask] - hazard[mask] * (z[mask] ** 2 + z[mask]))
            )
        )
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
    times: FloatVector,
    events: IntVector,
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
    log_times = np.log(times)
    weighted_design = design * np.sqrt(weights)[:, None]
    weighted_response = (log_times - offsets) * np.sqrt(weights)
    initial_beta, _, _, _ = np.linalg.lstsq(
        weighted_design, weighted_response, rcond=None
    )
    if distribution == "exponential":
        parameters = initial_beta
    else:
        residual = log_times - design @ initial_beta - offsets
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
            log_times,
            times,
            events,
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
                log_times,
                times,
                events,
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
                log_times,
                times,
                events,
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
) -> ParametricSurvivalResult:
    """Fit a weighted right-censored AFT model with offsets and scale strata."""
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
    time_array, event_array = _as_times_events(times, events)
    feature_array = _as_features(features, time_array.size)
    names = _feature_names(feature_array.shape[1], feature_names)
    _, strata_levels, strata_codes = _as_strata(strata, time_array.size)
    if distribution == "exponential" and len(strata_levels) > 1:
        raise InputValidationError(
            "exponential models have fixed scale and do not support scale strata"
        )
    scale_count = 1 if distribution == "exponential" else len(strata_levels)
    weight_array = _as_optional_numeric(
        weights, time_array.size, name="weights", default=1.0, positive=True
    )
    offset_array = _as_optional_numeric(
        offsets, time_array.size, name="offsets", default=0.0
    )
    design = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
        (np.ones(time_array.size), feature_array)
    )
    if np.linalg.matrix_rank(design) < design.shape[1]:
        raise RankDeficiencyError("parametric design must have full column rank")
    parameters, covariance, log_likelihood, iterations = _maximize_aft(
        time_array,
        event_array,
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
        time_array,
        event_array,
        np.ones((time_array.size, 1), dtype=np.float64),
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
        n_observations=time_array.size,
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
