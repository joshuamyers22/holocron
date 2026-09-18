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
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

MAX_OBSERVATIONS = 1_000_000
MAX_PARAMETERS = 1024
COX_SCHEMA_VERSION = "holocron-cox-result/v1"
PARAMETRIC_SCHEMA_VERSION = "holocron-parametric-survival-result/v1"
NONPARAMETRIC_SCHEMA_VERSION = "holocron-nonparametric-survival-result/v1"


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
    iterations: int
    n_observations: int

    @property
    def coefficient_names(self) -> tuple[str, ...]:
        """Return names in coefficient and covariance order."""
        return self.feature_names

    def predict_linear(self, features: Iterable[Iterable[float]]) -> tuple[float, ...]:
        """Predict mean-centered log relative hazards."""
        matrix = _validate_prediction_features(features, len(self.coefficients))
        return _vector(
            (matrix - np.asarray(self.feature_means, dtype=np.float64))
            @ np.asarray(self.coefficients, dtype=np.float64)
        )

    def predict_survival(
        self, features: Iterable[Iterable[float]], times: Iterable[float]
    ) -> tuple[tuple[float, ...], ...]:
        """Predict survival at each requested time for every feature row."""
        predictors = np.asarray(self.predict_linear(features), dtype=np.float64)
        requested = _validate_prediction_times(times)
        baseline_times = np.asarray(self.baseline_times, dtype=np.float64)
        baseline_hazard = np.asarray(self.baseline_cumulative_hazard, dtype=np.float64)
        indices = (
            np.searchsorted(  # pyright: ignore[reportUnknownMemberType]
                baseline_times, requested, side="right"
            )
            - 1
        )
        cumulative = np.where(  # pyright: ignore[reportUnknownMemberType]
            indices >= 0, baseline_hazard[np.maximum(indices, 0)], 0.0
        )
        values = np.exp(-np.exp(predictors[:, None]) * cumulative[None, :])
        return _matrix_rows(values)

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
        data = _result_object(document, COX_SCHEMA_VERSION)
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
        iterations = _read_positive_integer(data["iterations"], allow_zero=True)
        observations = _read_positive_integer(data["n_observations"])
        if (
            len(linear) != observations
            or any(value <= 0.0 for value in baseline_times)
            or any(value < 0.0 for value in baseline_hazard)
            or any(
                right <= left
                for left, right in zip(
                    baseline_times[:-1], baseline_times[1:], strict=True
                )
            )
            or any(
                right < left
                for left, right in zip(
                    baseline_hazard[:-1], baseline_hazard[1:], strict=True
                )
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
    scale: float
    linear_predictors: tuple[float, ...]
    log_likelihood: tuple[float, float]
    iterations: int
    n_observations: int

    def predict_linear(self, features: Iterable[Iterable[float]]) -> tuple[float, ...]:
        """Predict log survival-time location."""
        matrix = _validate_prediction_features(features, len(self.coefficients) - 1)
        return _vector(
            self.coefficients[0]
            + matrix @ np.asarray(self.coefficients[1:], dtype=np.float64)
        )

    def predict_survival(
        self, features: Iterable[Iterable[float]], times: Iterable[float]
    ) -> tuple[tuple[float, ...], ...]:
        """Predict survival at each strictly positive requested time."""
        predictors = np.asarray(self.predict_linear(features), dtype=np.float64)
        requested = _validate_prediction_times(times)
        if np.any(  # pyright: ignore[reportUnknownMemberType]
            requested <= 0.0
        ):
            raise InputValidationError("parametric prediction times must be positive")
        exponent = (np.log(requested)[None, :] - predictors[:, None]) / self.scale
        values = np.exp(
            -np.exp(
                np.clip(  # pyright: ignore[reportUnknownMemberType]
                    exponent, -745.0, 700.0
                )
            )
        )
        return _matrix_rows(values)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned result document."""
        return {
            "schema_version": PARAMETRIC_SCHEMA_VERSION,
            "distribution": self.distribution,
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "scale": self.scale,
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
        data = _result_object(document, PARAMETRIC_SCHEMA_VERSION)
        required = {
            "schema_version",
            "distribution",
            "coefficient_names",
            "coefficients",
            "covariance",
            "scale",
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
        scale = _read_positive_number(data["scale"])
        linear = _read_vector(data["linear_predictors"])
        log_likelihood = _read_vector(data["log_likelihood"], 2)
        iterations = _read_positive_integer(data["iterations"], allow_zero=True)
        observations = _read_positive_integer(data["n_observations"])
        if (
            len(linear) != observations
            or names[0] != "(Intercept)"
            or (distribution == "exponential" and scale != 1.0)
        ):
            raise InputValidationError("inconsistent parametric result document")
        return cls(
            cast(ParametricDistribution, distribution),
            names,
            coefficients,
            covariance,
            scale,
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
    n_risk: tuple[int, ...]
    n_event: tuple[int, ...]
    n_censor: tuple[int, ...]
    survival: tuple[float, ...]
    standard_error: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    confidence_level: float
    n_observations: int

    def predict(self, times: Iterable[float]) -> tuple[float, ...]:
        """Evaluate the right-continuous Kaplan–Meier step function."""
        requested = _validate_prediction_times(times)
        observed = np.asarray(self.time, dtype=np.float64)
        survival = np.asarray(self.survival, dtype=np.float64)
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
        data = _result_object(document, NONPARAMETRIC_SCHEMA_VERSION)
        required = {
            "schema_version",
            "estimator",
            "time",
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
        risk = _read_integer_vector(data["n_risk"], size)
        events = _read_integer_vector(data["n_event"], size)
        censor = _read_integer_vector(data["n_censor"], size)
        survival = _read_vector(data["survival"], size)
        standard_error = _read_vector(data["standard_error"], size)
        lower = _read_vector(data["lower"], size)
        upper = _read_vector(data["upper"], size)
        confidence = _read_probability(data["confidence_level"])
        observations = _read_positive_integer(data["n_observations"])
        if (
            risk[0] != observations
            or any(value <= 0.0 for value in times)
            or any(value < 0.0 for value in standard_error)
            or any(
                right <= left for left, right in zip(times[:-1], times[1:], strict=True)
            )
            or any(
                right >= left for left, right in zip(risk[:-1], risk[1:], strict=True)
            )
            or any(
                observed + censored > at_risk
                for at_risk, observed, censored in zip(
                    risk, events, censor, strict=True
                )
            )
            or any(
                later > earlier
                for earlier, later in zip(survival[:-1], survival[1:], strict=True)
            )
            or any(
                not 0.0 <= low <= value <= high <= 1.0
                for low, value, high in zip(lower, survival, upper, strict=True)
            )
        ):
            raise InputValidationError("inconsistent nonparametric result document")
        return cls(
            times,
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
) -> tuple[float, FloatVector, FloatMatrix]:
    predictor = features @ beta
    exponential = np.exp(
        np.clip(  # pyright: ignore[reportUnknownMemberType]
            predictor, -700.0, 700.0
        )
    )
    width = features.shape[1]
    log_likelihood = 0.0
    score = np.zeros(width, dtype=np.float64)
    hessian = np.zeros((width, width), dtype=np.float64)
    event_times = np.unique(  # pyright: ignore[reportUnknownMemberType]
        times[events == 1]
    )
    for event_time in event_times:
        event_mask = (times == event_time) & (events == 1)
        risk_mask = times >= event_time
        event_features = features[event_mask]
        event_exponential = exponential[event_mask]
        risk_features = features[risk_mask]
        risk_exponential = exponential[risk_mask]
        event_count = int(
            np.count_nonzero(event_mask)  # pyright: ignore[reportUnknownMemberType]
        )
        risk_zero = float(np.sum(risk_exponential))
        risk_one = np.sum(risk_exponential[:, None] * risk_features, axis=0)
        risk_two = risk_features.T @ (risk_exponential[:, None] * risk_features)
        event_zero = float(np.sum(event_exponential))
        event_one = np.sum(event_exponential[:, None] * event_features, axis=0)
        event_two = event_features.T @ (event_exponential[:, None] * event_features)
        log_likelihood += float(np.sum(predictor[event_mask]))
        score += np.sum(event_features, axis=0)
        steps = event_count if method == "efron" else 1
        multiplier = 1.0 if method == "efron" else float(event_count)
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
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[FloatVector, FloatMatrix, float, float, int]:
    beta = np.zeros(features.shape[1], dtype=np.float64)
    null_log_likelihood, _, _ = _cox_terms(beta, times, events, features, method)
    log_likelihood = null_log_likelihood
    for iteration in range(1, max_iterations + 1):
        log_likelihood, score, hessian = _cox_terms(
            beta, times, events, features, method
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
                candidate, times, events, features, method
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
) -> tuple[FloatVector, FloatVector]:
    predictor = centered_features @ result_beta
    exponential = np.exp(
        np.clip(  # pyright: ignore[reportUnknownMemberType]
            predictor, -700.0, 700.0
        )
    )
    event_times = np.unique(  # pyright: ignore[reportUnknownMemberType]
        times[events == 1]
    )
    increments: list[float] = []
    for event_time in event_times:
        event_mask = (times == event_time) & (events == 1)
        risk_zero = float(np.sum(exponential[times >= event_time]))
        event_zero = float(np.sum(exponential[event_mask]))
        event_count = int(
            np.count_nonzero(event_mask)  # pyright: ignore[reportUnknownMemberType]
        )
        if method == "breslow":
            increment = event_count / risk_zero
        else:
            increment = sum(
                1.0 / (risk_zero - (index / event_count) * event_zero)
                for index in range(event_count)
            )
        increments.append(increment)
    return event_times, np.cumsum(  # pyright: ignore[reportUnknownMemberType]
        np.asarray(increments, dtype=np.float64)
    )


def fit_cph(
    times: Iterable[float],
    events: Iterable[int | bool],
    features: Iterable[Iterable[float]],
    *,
    method: CoxMethod = "efron",
    feature_names: Iterable[str] | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-9,
) -> CoxResult:
    """Fit a right-censored Cox model with Efron or Breslow ties."""
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
    beta, covariance, null_log_likelihood, log_likelihood, iterations = _maximize_cox(
        time_array,
        event_array,
        feature_array,
        method,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    means = np.mean(feature_array, axis=0)
    centered = feature_array - means
    event_times, baseline = _cox_baseline(
        beta, time_array, event_array, centered, method
    )
    return CoxResult(
        method=method,
        feature_names=names,
        coefficients=_vector(beta),
        covariance=_matrix_rows(covariance),
        feature_means=_vector(means),
        linear_predictors=_vector(centered @ beta),
        log_likelihood=(null_log_likelihood, log_likelihood),
        baseline_times=_vector(event_times),
        baseline_cumulative_hazard=_vector(baseline),
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
) -> tuple[float, FloatVector, FloatMatrix]:
    width = design.shape[1]
    beta = parameters[:width]
    log_scale = 0.0 if distribution == "exponential" else float(parameters[-1])
    scale = math.exp(log_scale)
    z = (log_times - design @ beta) / scale
    hazard = np.exp(
        np.clip(z, -745.0, 700.0)  # pyright: ignore[reportUnknownMemberType]
    )
    observed = events.astype(np.float64)
    log_likelihood = float(np.sum(observed * (z - log_scale - np.log(times)) - hazard))
    score_beta = design.T @ (hazard - observed) / scale
    hessian_beta = -(design.T @ (hazard[:, None] * design)) / (scale * scale)
    if distribution == "exponential":
        return log_likelihood, score_beta, hessian_beta
    score_scale = float(np.sum(observed * (-z - 1.0) + hazard * z))
    cross = design.T @ (observed - hazard * (1.0 + z)) / scale
    hessian_scale = float(np.sum(observed * z - hazard * (z * z + z)))
    score = np.concatenate(  # pyright: ignore[reportUnknownMemberType]
        (score_beta, np.asarray([score_scale]))
    )
    hessian = np.empty((width + 1, width + 1), dtype=np.float64)
    hessian[:width, :width] = hessian_beta
    hessian[:width, width] = cross
    hessian[width, :width] = cross
    hessian[width, width] = hessian_scale
    return log_likelihood, score, hessian


def _maximize_aft(
    times: FloatVector,
    events: IntVector,
    design: FloatMatrix,
    distribution: ParametricDistribution,
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[FloatVector, FloatMatrix, float, int]:
    log_times = np.log(times)
    initial_beta, _, _, _ = np.linalg.lstsq(design, log_times, rcond=None)
    if distribution == "exponential":
        parameters = initial_beta
    else:
        residual = log_times - design @ initial_beta
        initial_scale = max(float(np.std(residual)), 0.25)
        parameters = np.concatenate(  # pyright: ignore[reportUnknownMemberType]
            (initial_beta, np.asarray([math.log(initial_scale)]))
        )
    log_likelihood = -math.inf
    for iteration in range(1, max_iterations + 1):
        current, score, hessian = _aft_terms(
            parameters, log_times, times, events, design, distribution
        )
        try:
            step = np.linalg.solve(-hessian, score)
        except np.linalg.LinAlgError as error:
            raise RankDeficiencyError(
                "parametric information matrix is singular"
            ) from error
        scale = 1.0
        accepted = False
        while scale >= 2.0**-30:
            candidate = parameters + scale * step
            candidate_log_likelihood, _, _ = _aft_terms(
                candidate, log_times, times, events, design, distribution
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
                parameters, log_times, times, events, design, distribution
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
    max_iterations: int = 100,
    tolerance: float = 1e-10,
) -> ParametricSurvivalResult:
    """Fit a right-censored Weibull or exponential AFT model."""
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
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    null_parameters, _, null_log_likelihood, _ = _maximize_aft(
        time_array,
        event_array,
        np.ones((time_array.size, 1), dtype=np.float64),
        distribution,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    del null_parameters
    coefficients = parameters[: design.shape[1]]
    scale = 1.0 if distribution == "exponential" else math.exp(float(parameters[-1]))
    return ParametricSurvivalResult(
        distribution=distribution,
        coefficient_names=("(Intercept)", *names),
        coefficients=_vector(coefficients),
        covariance=_matrix_rows(covariance[: design.shape[1], : design.shape[1]]),
        scale=scale,
        linear_predictors=_vector(design @ coefficients),
        log_likelihood=(null_log_likelihood, log_likelihood),
        iterations=iterations,
        n_observations=time_array.size,
    )


def fit_npsurv(
    times: Iterable[float],
    events: Iterable[int | bool],
    *,
    confidence_level: float = 0.95,
) -> NonparametricSurvivalResult:
    """Compute a Kaplan–Meier curve and log-scale Greenwood intervals."""
    if not 0.0 < confidence_level < 1.0:
        raise InputValidationError("confidence_level must be between zero and one")
    time_array, event_array = _as_times_events(times, events)
    unique_times = np.unique(  # pyright: ignore[reportUnknownMemberType]
        time_array
    )
    survival = 1.0
    greenwood = 0.0
    z_value = NormalDist().inv_cdf(0.5 + confidence_level / 2.0)
    risk_values: list[int] = []
    event_values: list[int] = []
    censor_values: list[int] = []
    survival_values: list[float] = []
    standard_errors: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    for value in unique_times:
        at_risk = int(
            np.count_nonzero(  # pyright: ignore[reportUnknownMemberType]
                time_array >= value
            )
        )
        at_time = time_array == value
        observed = int(
            np.count_nonzero(  # pyright: ignore[reportUnknownMemberType]
                at_time & (event_array == 1)
            )
        )
        censored = int(
            np.count_nonzero(  # pyright: ignore[reportUnknownMemberType]
                at_time & (event_array == 0)
            )
        )
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
        risk_values.append(at_risk)
        event_values.append(observed)
        censor_values.append(censored)
        survival_values.append(survival)
        standard_errors.append(standard_error)
        lower.append(low)
        upper.append(high)
    return NonparametricSurvivalResult(
        time=_vector(unique_times),
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


def _result_object(document: object, schema_version: str) -> dict[str, object]:
    if not isinstance(document, dict):
        raise InputValidationError("result document must be an object")
    result = cast(dict[str, object], document)
    if result.get("schema_version") != schema_version:
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


def _read_vector(value: object, size: int | None = None) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise InputValidationError("numeric vector has the wrong shape")
    raw_values = cast(list[object], value)
    if size is not None and len(raw_values) != size:
        raise InputValidationError("numeric vector has the wrong shape")
    if not raw_values or not all(_finite_number(item) for item in raw_values):
        raise InputValidationError("numeric vector must be nonempty and finite")
    return tuple(float(cast(Real, item)) for item in raw_values)


def _read_integer_vector(value: object, size: int) -> tuple[int, ...]:
    raw_values = cast(list[object], value) if isinstance(value, list) else []
    if (
        not isinstance(value, list)
        or len(raw_values) != size
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in raw_values
        )
    ):
        raise InputValidationError("count vector is invalid")
    return tuple(cast(int, item) for item in raw_values)


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
