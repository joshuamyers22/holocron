"""Owned cumulative-link ordinal regression and censored-response contracts."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Real
from typing import Literal, TypeAlias, cast

import numpy as np
import numpy.typing as npt

from holocron._serialization import canonical_json, parse_json_object, validate_sha256
from holocron.design import DesignMatrix
from holocron.exceptions import (
    ConvergenceError,
    InputValidationError,
    NumericalError,
    RankDeficiencyError,
)

FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]
IntVector = npt.NDArray[np.int64]
OrdinalFamily = Literal["logistic", "probit", "loglog", "cloglog", "cauchit"]
OrdinalEstimator = Literal["orm", "lrm"]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

SCHEMA_VERSION = "holocron-ordinal-result/v1"
MAX_OBSERVATIONS = 1_000_000
MAX_PARAMETERS = 1024
MIN_PROBABILITY = 1e-300


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, Real)
        and math.isfinite(float(value))
    )


def _bounded_integer(value: object, *, lower: int, upper: int) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and lower <= value <= upper
    )


def _as_feature_matrix(
    values: Iterable[Iterable[float]], *, allow_zero_columns: bool = False
) -> FloatMatrix:
    rows = tuple(tuple(float(value) for value in row) for row in values)
    if not rows:
        raise InputValidationError("features must contain at least one row")
    width = len(rows[0])
    if width == 0 and not allow_zero_columns:
        raise InputValidationError("features must contain at least one column")
    if len(rows) > MAX_OBSERVATIONS or width >= MAX_PARAMETERS:
        raise InputValidationError("features exceeds the supported shape limit")
    if any(len(row) != width for row in rows):
        raise InputValidationError("features rows must have equal lengths")
    if not all(math.isfinite(value) for row in rows for value in row):
        raise InputValidationError("features must contain only finite values")
    return np.asarray(rows, dtype=np.float64).reshape((len(rows), width))


def _feature_names(width: int, names: Iterable[str] | None) -> tuple[str, ...]:
    result = (
        tuple(names)
        if names is not None
        else tuple(f"x{index + 1}" for index in range(width))
    )
    if len(result) != width:
        raise InputValidationError(
            "feature_names must match the number of feature columns"
        )
    if any(not name for name in result) or len(set(result)) != width:
        raise InputValidationError("feature_names must be non-empty and unique")
    return result


def _expit(values: FloatVector) -> FloatVector:
    result = np.empty_like(values)
    positive = values >= 0.0
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponent = np.exp(values[~positive])
    result[~positive] = exponent / (1.0 + exponent)
    return result


def _family_values(
    values: FloatVector, family: OrdinalFamily
) -> tuple[FloatVector, FloatVector, FloatVector]:
    """Return cumulative probability and its first two derivatives."""
    x = values.clip(-700.0, 700.0)  # pyright: ignore[reportUnknownMemberType]
    if family == "logistic":
        probability = _expit(x)
        derivative = probability * (1.0 - probability)
        second = derivative * (1.0 - 2.0 * probability)
    elif family == "probit":
        probability = np.fromiter(
            (0.5 * math.erfc(-float(value) / math.sqrt(2.0)) for value in x),
            dtype=np.float64,
            count=x.size,
        )
        derivative = np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)
        second = -x * derivative
    elif family == "loglog":
        exponential = np.exp(  # pyright: ignore[reportUnknownMemberType]
            (-x).clip(-700.0, 700.0)  # pyright: ignore[reportUnknownMemberType]
        )
        probability = np.exp(-exponential)
        derivative = np.exp(  # pyright: ignore[reportUnknownMemberType]
            (-x - exponential).clip(  # pyright: ignore[reportUnknownMemberType]
                -745.0, 700.0
            )
        )
        second = derivative * (-1.0 + exponential)
    elif family == "cloglog":
        exponential = np.exp(  # pyright: ignore[reportUnknownMemberType]
            x.clip(-700.0, 700.0)  # pyright: ignore[reportUnknownMemberType]
        )
        probability = -np.expm1(-exponential)
        derivative = np.exp(  # pyright: ignore[reportUnknownMemberType]
            (x - exponential).clip(  # pyright: ignore[reportUnknownMemberType]
                -745.0, 700.0
            )
        )
        second = derivative * (1.0 - exponential)
    else:
        probability = 0.5 + np.arctan(x) / math.pi
        denominator = 1.0 + x * x
        derivative = 1.0 / (math.pi * denominator)
        second = -2.0 * x / (math.pi * denominator * denominator)
    return probability, derivative, second


def _inverse_family(probability: float, family: OrdinalFamily) -> float:
    if not 0.0 < probability < 1.0:
        raise InputValidationError("ordinal cumulative probabilities must be interior")
    if family == "logistic":
        return math.log(probability / (1.0 - probability))
    if family == "loglog":
        return -math.log(-math.log(probability))
    if family == "cloglog":
        return math.log(-math.log1p(-probability))
    if family == "cauchit":
        return math.tan(math.pi * (probability - 0.5))
    lower = -9.0
    upper = 9.0
    for _ in range(80):
        middle = (lower + upper) * 0.5
        value = 0.5 * math.erfc(-middle / math.sqrt(2.0))
        if value < probability:
            lower = middle
        else:
            upper = middle
    return (lower + upper) * 0.5


@dataclass(frozen=True, slots=True)
class TurnbullResult:
    """Maximal intersections and their self-consistent probability masses."""

    lower: tuple[float, ...]
    upper: tuple[float, ...]
    first: tuple[int, ...]
    last: tuple[int, ...]
    probabilities: tuple[float, ...]
    survival: tuple[float, ...]
    iterations: int
    converged: bool


@dataclass(frozen=True, slots=True)
class OrdinalTest:
    """A likelihood-ratio or joint Wald chi-square test."""

    kind: Literal["likelihood-ratio", "wald"]
    coefficient_names: tuple[str, ...]
    statistic: float
    degrees_of_freedom: int
    p_value: float


@dataclass(frozen=True, slots=True)
class OrdinalDiagnostics:
    """Numerical and fitted-probability diagnostics for an ordinal fit."""

    iterations: int
    covariance_condition: float
    minimum_fitted_probability: float
    maximum_simplex_error: float


@dataclass(frozen=True, slots=True)
class CensoredResponse:
    """Validated exact, left-, right-, interval-, or mixed-censored response."""

    lower: tuple[float, ...]
    upper: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.lower or len(self.lower) != len(self.upper):
            raise InputValidationError(
                "censoring endpoints must have equal nonzero length"
            )
        if len(self.lower) > MAX_OBSERVATIONS:
            raise InputValidationError(
                "censored response exceeds the observation limit"
            )
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
            ):
                raise InputValidationError("invalid censoring interval")
        if not any(
            math.isfinite(lower) and lower == upper
            for lower, upper in zip(self.lower, self.upper, strict=True)
        ):
            raise InputValidationError("at least one exact response is required")

    @classmethod
    def from_intervals(
        cls, lower: Iterable[float], upper: Iterable[float] | None = None
    ) -> CensoredResponse:
        """Construct a response; omitted upper endpoints declare exact values."""
        lower_values = tuple(float(value) for value in lower)
        upper_values = (
            lower_values if upper is None else tuple(float(value) for value in upper)
        )
        return cls(lower_values, upper_values)

    @property
    def censoring_types(self) -> tuple[str, ...]:
        """Return the exact censoring kind for each observation."""
        result: list[str] = []
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

    def turnbull(
        self,
        *,
        precision: int = 7,
        max_iterations: int = 10_000,
        tolerance: float = 1e-8,
    ) -> TurnbullResult:
        """Compute exact-grid maximal intersections and the Turnbull NPMLE.

        Finite interval endpoints are inclusive.  The finite endpoint of a
        one-sided interval is open, matching ``Ocens2ord``: ``(-inf, b)``
        excludes ``b`` and ``(a, inf)`` excludes ``a``.
        """
        if isinstance(precision, bool) or not 0 <= precision <= 15:
            raise InputValidationError("precision must be an integer from 0 to 15")
        if isinstance(max_iterations, bool) or not 1 <= max_iterations <= 1_000_000:
            raise InputValidationError("max_iterations is outside the supported range")
        if not _finite_number(tolerance) or not 0.0 < tolerance < 1.0:
            raise InputValidationError("tolerance must be finite and between 0 and 1")

        finite = tuple(
            value for value in (*self.lower, *self.upper) if math.isfinite(value)
        )
        multiplier = (
            float(10**precision) if any(value % 1.0 != 0.0 for value in finite) else 1.0
        )
        lower_grid = [
            value if not math.isfinite(value) else float(round(value * multiplier))
            for value in self.lower
        ]
        upper_grid = [
            value if not math.isfinite(value) else float(round(value * multiplier))
            for value in self.upper
        ]
        for index, (lower, upper) in enumerate(
            zip(lower_grid, upper_grid, strict=True)
        ):
            if lower == -math.inf:
                upper_grid[index] = upper - 1.0
            elif upper == math.inf:
                lower_grid[index] = lower + 1.0
            if lower_grid[index] > upper_grid[index]:
                raise InputValidationError(
                    "a one-sided censoring interval contains no exact-grid value"
                )
        typed = sorted(
            ((value, 0) for value in lower_grid),
            key=lambda item: (item[0], item[1]),
        ) + sorted(
            ((value, 1) for value in upper_grid),
            key=lambda item: (item[0], item[1]),
        )
        typed.sort(key=lambda item: (item[0], item[1]))
        intersections: list[tuple[float, float]] = []
        for left, right in zip(typed, typed[1:], strict=False):
            if left[1] == 0 and right[1] == 1:
                candidate = (float(left[0]), float(right[0]))
                if not intersections or candidate != intersections[-1]:
                    intersections.append(candidate)
        if not intersections:
            raise InputValidationError(
                "censoring intervals have no maximal intersection"
            )

        first: list[int] = []
        last: list[int] = []
        for lower, upper in zip(lower_grid, upper_grid, strict=True):
            contained = [
                index
                for index, (left, right) in enumerate(intersections)
                if left >= lower and right <= upper
            ]
            if not contained:
                raise InputValidationError(
                    "a censoring interval contains no maximal intersection"
                )
            first.append(contained[0])
            last.append(contained[-1])

        count = len(intersections)
        probabilities = np.full(count, 1.0 / count, dtype=np.float64)
        converged = False
        completed = 0
        for iteration in range(1, max_iterations + 1):
            completed = iteration
            updated = np.zeros(count, dtype=np.float64)
            for start, stop in zip(first, last, strict=True):
                denominator = float(np.sum(probabilities[start : stop + 1]))
                if denominator <= 0.0:
                    raise NumericalError("Turnbull clique probability became zero")
                updated[start : stop + 1] += (
                    probabilities[start : stop + 1] / denominator
                )
            updated /= len(first)
            if float(np.max(np.abs(updated - probabilities))) < tolerance:
                converged = True
                probabilities = updated
                break
            probabilities = updated
        cumulative = np.empty(count + 1, dtype=np.float64)
        cumulative[0] = 0.0
        cumulative[1:] = np.cumsum(  # pyright: ignore[reportUnknownMemberType]
            probabilities
        )
        gradient = np.zeros(count, dtype=np.float64)
        for start, stop in zip(first, last, strict=True):
            denominator = float(cumulative[stop + 1] - cumulative[start])
            gradient[start : stop + 1] += 1.0 / denominator
        support = (probabilities >= 1e-5) | (gradient >= len(first) * (1.0 - 1e-6))
        if not bool(support.all()):
            supported_before = np.cumsum(  # pyright: ignore[reportUnknownMemberType]
                support.astype(np.int64)
            )
            cluster_count = int(supported_before[-1])
            if cluster_count == 0:
                raise NumericalError("Turnbull NPMLE has no supported intersection")
            upward = np.where(  # pyright: ignore[reportUnknownMemberType]
                support, supported_before - 1, supported_before
            )
            remapped_first = [int(upward[index]) for index in first]
            remapped_last = [int(supported_before[index] - 1) for index in last]
            if any(
                start > stop or start >= cluster_count or stop < 0
                for start, stop in zip(remapped_first, remapped_last, strict=True)
            ):
                raise NumericalError(
                    "censoring interval is incompatible with supported intersections"
                )
            labels = np.minimum(np.maximum(upward, 0), cluster_count - 1)
            consolidated: list[tuple[float, float]] = []
            consolidated_probability: list[float] = []
            for label in range(cluster_count):
                selected = labels == label
                consolidated.append(
                    (
                        min(
                            intersections[index][0]
                            for index in range(count)
                            if bool(selected[index])
                        ),
                        max(
                            intersections[index][1]
                            for index in range(count)
                            if bool(selected[index])
                        ),
                    )
                )
                consolidated_probability.append(float(np.sum(probabilities[selected])))
            intersections = consolidated
            probabilities = np.asarray(consolidated_probability, dtype=np.float64)
            first = remapped_first
            last = remapped_last
        survival = probabilities[::-1].cumsum()[::-1]
        return TurnbullResult(
            lower=tuple(item[0] / multiplier for item in intersections),
            upper=tuple(item[1] / multiplier for item in intersections),
            first=tuple(first),
            last=tuple(last),
            probabilities=tuple(float(value) for value in probabilities),
            survival=tuple(float(value) for value in survival),
            iterations=completed,
            converged=converged,
        )


@dataclass(frozen=True, slots=True)
class OrdinalResult:
    """Immutable fitted result for a cumulative-link ordinal model."""

    estimator: OrdinalEstimator
    family: OrdinalFamily
    response_levels: tuple[float, ...]
    threshold_names: tuple[str, ...]
    feature_names: tuple[str, ...]
    thresholds: tuple[float, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    linear_predictors: tuple[float, ...]
    fitted_probabilities: tuple[tuple[float, ...], ...]
    deviance: tuple[float, float]
    iterations: int
    n_observations: int
    design_fingerprint: str | None = None
    censored: bool = False

    def __post_init__(self) -> None:
        if self.estimator not in {"orm", "lrm"}:
            raise InputValidationError("ordinal estimator is invalid")
        if self.family not in {"logistic", "probit", "loglog", "cloglog", "cauchit"}:
            raise InputValidationError("ordinal family is invalid")
        level_count = len(self.response_levels)
        threshold_count = level_count - 1
        if level_count < 3 or len(set(self.response_levels)) != level_count:
            raise InputValidationError("ordinal result requires ordered unique levels")
        if tuple(sorted(self.response_levels)) != self.response_levels:
            raise InputValidationError("response levels must be increasing")
        if (
            len(self.threshold_names) != threshold_count
            or len(self.thresholds) != threshold_count
        ):
            raise InputValidationError(
                "threshold metadata differs from response levels"
            )
        if (
            any(not name for name in self.threshold_names)
            or len(set(self.threshold_names)) != threshold_count
        ):
            raise InputValidationError("threshold names must be non-empty and unique")
        if any(not _finite_number(value) for value in self.thresholds):
            raise InputValidationError("ordinal thresholds must be finite")
        if any(
            left <= right
            for left, right in zip(self.thresholds, self.thresholds[1:], strict=False)
        ):
            raise InputValidationError("ordinal thresholds must be strictly decreasing")
        if not self.coefficients or len(self.feature_names) != len(self.coefficients):
            raise InputValidationError("ordinal coefficient metadata differs")
        if (
            any(not name for name in self.feature_names)
            or len(set(self.feature_names)) != len(self.feature_names)
            or any(not _finite_number(value) for value in self.coefficients)
        ):
            raise InputValidationError(
                "ordinal coefficients require finite values and unique names"
            )
        parameter_count = threshold_count + len(self.coefficients)
        if parameter_count > MAX_PARAMETERS or len(self.covariance) != parameter_count:
            raise InputValidationError("ordinal covariance has invalid dimensions")
        if any(len(row) != parameter_count for row in self.covariance):
            raise InputValidationError("ordinal covariance must be square")
        if (
            not _bounded_integer(self.iterations, lower=1, upper=10_000)
            or not _bounded_integer(
                self.n_observations, lower=1, upper=MAX_OBSERVATIONS
            )
            or type(self.censored) is not bool
        ):
            raise InputValidationError(
                "ordinal iteration or observation metadata is invalid"
            )
        if (
            len(self.linear_predictors) != self.n_observations
            or len(self.fitted_probabilities) != self.n_observations
        ):
            raise InputValidationError(
                "ordinal fitted values differ from observation count"
            )
        if any(len(row) != level_count for row in self.fitted_probabilities):
            raise InputValidationError(
                "ordinal probabilities differ from response levels"
            )
        numeric = (
            *self.response_levels,
            *self.thresholds,
            *self.coefficients,
            *(value for row in self.covariance for value in row),
            *self.linear_predictors,
            *(value for row in self.fitted_probabilities for value in row),
            *self.deviance,
        )
        if any(not _finite_number(value) for value in numeric):
            raise InputValidationError("ordinal result contains non-finite values")
        if any(
            not math.isclose(sum(row), 1.0, rel_tol=1e-10, abs_tol=1e-10)
            or any(value < 0.0 or value > 1.0 for value in row)
            for row in self.fitted_probabilities
        ):
            raise InputValidationError("ordinal probabilities must be a simplex")
        if len(self.deviance) != 2 or any(value < 0.0 for value in self.deviance):
            raise InputValidationError("ordinal deviance is invalid")
        validate_sha256(
            self.design_fingerprint, role="design_fingerprint", nullable=True
        )

    @property
    def coefficient_names(self) -> tuple[str, ...]:
        """Return thresholds followed by slope names."""
        return (*self.threshold_names, *self.feature_names)

    @property
    def parameter_values(self) -> tuple[float, ...]:
        """Return thresholds followed by slopes."""
        return (*self.thresholds, *self.coefficients)

    def _matrix(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> FloatMatrix:
        if isinstance(features, DesignMatrix):
            if (
                self.design_fingerprint is not None
                and features.specification_fingerprint != self.design_fingerprint
            ):
                raise InputValidationError(
                    "prediction design fingerprint differs from the fitted design"
                )
            values = features.rows
        else:
            values = features
        matrix = _as_feature_matrix(values)
        if matrix.shape[1] != len(self.coefficients):
            raise InputValidationError(
                f"features has {matrix.shape[1]} columns; "
                f"expected {len(self.coefficients)}"
            )
        return matrix

    def predict_linear(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> tuple[float, ...]:
        """Predict the first-threshold linear predictor used by rms."""
        matrix = self._matrix(features)
        values = self.thresholds[0] + matrix @ np.asarray(self.coefficients)
        return tuple(float(value) for value in values)

    def predict_probabilities(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> tuple[tuple[float, ...], ...]:
        """Predict mutually exclusive probabilities in response-level order."""
        matrix = self._matrix(features)
        return _probability_rows(
            np.asarray(self.thresholds),
            matrix @ np.asarray(self.coefficients),
            self.family,
        )

    def predict_mean(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> tuple[float, ...]:
        """Predict the response mean using numeric response-level scores."""
        levels = np.asarray(self.response_levels)
        return tuple(
            float(np.asarray(row) @ levels)
            for row in self.predict_probabilities(features)
        )

    def predict_quantile(
        self,
        features: Iterable[Iterable[float]] | DesignMatrix,
        *,
        probability: float = 0.5,
    ) -> tuple[float, ...]:
        """Predict the smallest response level whose CDF reaches probability."""
        if not _finite_number(probability) or not 0.0 <= probability <= 1.0:
            raise InputValidationError("probability must be finite and between 0 and 1")
        result: list[float] = []
        for row in self.predict_probabilities(features):
            cumulative = 0.0
            selected = self.response_levels[-1]
            for level, value in zip(self.response_levels, row, strict=True):
                cumulative += value
                if cumulative >= probability:
                    selected = level
                    break
            result.append(selected)
        return tuple(result)

    def predict_exceedance(
        self, features: Iterable[Iterable[float]] | DesignMatrix, *, level: float
    ) -> tuple[float, ...]:
        """Predict P(Y >= level) for an official fitted response level."""
        if level not in self.response_levels:
            raise InputValidationError(
                "level must be an official fitted response level"
            )
        index = self.response_levels.index(level)
        return tuple(
            float(sum(row[index:])) for row in self.predict_probabilities(features)
        )

    def likelihood_ratio_test(self) -> OrdinalTest:
        """Test all slope coefficients against the fitted intercept-only model."""
        statistic = max(0.0, self.deviance[0] - self.deviance[1])
        degrees_of_freedom = len(self.coefficients)
        return OrdinalTest(
            kind="likelihood-ratio",
            coefficient_names=self.feature_names,
            statistic=statistic,
            degrees_of_freedom=degrees_of_freedom,
            p_value=_chi_square_survival(statistic, degrees_of_freedom),
        )

    def wald_test(self, names: Iterable[str] | None = None) -> OrdinalTest:
        """Jointly test named thresholds or slopes against zero."""
        selected = self.feature_names if names is None else tuple(names)
        if not selected or len(set(selected)) != len(selected):
            raise InputValidationError(
                "Wald coefficient names must be unique and nonempty"
            )
        unknown = tuple(name for name in selected if name not in self.coefficient_names)
        if unknown:
            raise InputValidationError(f"unknown ordinal coefficients: {unknown}")
        indices = tuple(self.coefficient_names.index(name) for name in selected)
        values = np.asarray([self.parameter_values[index] for index in indices])
        covariance = np.asarray(
            [[self.covariance[row][column] for column in indices] for row in indices],
            dtype=np.float64,
        )
        try:
            statistic = float(values @ np.linalg.solve(covariance, values))
        except np.linalg.LinAlgError as error:
            raise NumericalError("ordinal Wald covariance is singular") from error
        statistic = max(0.0, statistic)
        return OrdinalTest(
            kind="wald",
            coefficient_names=selected,
            statistic=statistic,
            degrees_of_freedom=len(indices),
            p_value=_chi_square_survival(statistic, len(indices)),
        )

    def diagnostics(self) -> OrdinalDiagnostics:
        """Return bounded conditioning and probability-simplex diagnostics."""
        covariance = np.asarray(self.covariance, dtype=np.float64)
        condition = float(np.linalg.cond(covariance))
        minimum = min(value for row in self.fitted_probabilities for value in row)
        simplex_error = max(
            abs(math.fsum(row) - 1.0) for row in self.fitted_probabilities
        )
        return OrdinalDiagnostics(
            iterations=self.iterations,
            covariance_condition=condition,
            minimum_fitted_probability=minimum,
            maximum_simplex_error=simplex_error,
        )

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the versioned ordinal result document."""
        return {
            "schema_version": SCHEMA_VERSION,
            "result_type": "ordinal",
            "estimator": self.estimator,
            "family": self.family,
            "response_levels": list(self.response_levels),
            "threshold_names": list(self.threshold_names),
            "feature_names": list(self.feature_names),
            "thresholds": list(self.thresholds),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "linear_predictors": list(self.linear_predictors),
            "fitted_probabilities": [list(row) for row in self.fitted_probabilities],
            "deviance": list(self.deviance),
            "iterations": self.iterations,
            "n_observations": self.n_observations,
            "design_fingerprint": self.design_fingerprint,
            "censored": self.censored,
        }

    def to_json(self) -> str:
        """Serialize this result as canonical non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical result document."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> OrdinalResult:
        """Reconstruct an ordinal result from an exact-version document."""
        if not isinstance(document, dict):
            raise InputValidationError("ordinal result document must be an object")
        raw = cast(dict[str, object], document)
        required = {
            "schema_version",
            "result_type",
            "estimator",
            "family",
            "response_levels",
            "threshold_names",
            "feature_names",
            "thresholds",
            "coefficients",
            "covariance",
            "linear_predictors",
            "fitted_probabilities",
            "deviance",
            "iterations",
            "n_observations",
            "design_fingerprint",
            "censored",
        }
        if (
            set(raw) != required
            or raw["schema_version"] != SCHEMA_VERSION
            or raw["result_type"] != "ordinal"
        ):
            raise InputValidationError(
                "ordinal result document fields or version differ"
            )
        arrays = required - {
            "schema_version",
            "result_type",
            "estimator",
            "family",
            "iterations",
            "n_observations",
            "design_fingerprint",
            "censored",
        }
        if any(not isinstance(raw[name], list) for name in arrays):
            raise InputValidationError("ordinal result arrays are malformed")
        covariance = cast(list[object], raw["covariance"])
        fitted = cast(list[object], raw["fitted_probabilities"])
        if any(not isinstance(row, list) for row in (*covariance, *fitted)):
            raise InputValidationError("ordinal result matrix rows are malformed")
        try:
            return cls(
                estimator=cast(OrdinalEstimator, raw["estimator"]),
                family=cast(OrdinalFamily, raw["family"]),
                response_levels=tuple(cast(list[float], raw["response_levels"])),
                threshold_names=tuple(cast(list[str], raw["threshold_names"])),
                feature_names=tuple(cast(list[str], raw["feature_names"])),
                thresholds=tuple(cast(list[float], raw["thresholds"])),
                coefficients=tuple(cast(list[float], raw["coefficients"])),
                covariance=tuple(tuple(cast(list[float], row)) for row in covariance),
                linear_predictors=tuple(cast(list[float], raw["linear_predictors"])),
                fitted_probabilities=tuple(
                    tuple(cast(list[float], row)) for row in fitted
                ),
                deviance=cast(
                    tuple[float, float], tuple(cast(list[float], raw["deviance"]))
                ),
                iterations=cast(int, raw["iterations"]),
                n_observations=cast(int, raw["n_observations"]),
                design_fingerprint=cast(str | None, raw["design_fingerprint"]),
                censored=cast(bool, raw["censored"]),
            )
        except (IndexError, TypeError, ValueError) as error:
            if isinstance(error, InputValidationError):
                raise
            raise InputValidationError(
                "ordinal result document is malformed"
            ) from error

    @classmethod
    def from_json(cls, value: str) -> OrdinalResult:
        """Reconstruct an ordinal result from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="ordinal result"))


def _probability_rows(
    thresholds: FloatVector, predictor: FloatVector, family: OrdinalFamily
) -> tuple[tuple[float, ...], ...]:
    cumulative, _, _ = _family_values(
        (thresholds[:, None] + predictor[None, :]).reshape(-1), family
    )
    cumulative = cumulative.reshape((thresholds.size, predictor.size)).T
    result = np.empty((predictor.size, thresholds.size + 1), dtype=np.float64)
    result[:, 0] = 1.0 - cumulative[:, 0]
    if thresholds.size > 1:
        result[:, 1:-1] = cumulative[:, :-1] - cumulative[:, 1:]
    result[:, -1] = cumulative[:, -1]
    result = np.maximum(result, 0.0)
    result /= np.sum(result, axis=1)[:, None]
    return tuple(tuple(float(value) for value in row) for row in result)


def _chi_square_survival(statistic: float, degrees_of_freedom: int) -> float:
    if degrees_of_freedom < 1 or statistic < 0.0:
        raise NumericalError("invalid chi-square arguments")
    shape = degrees_of_freedom / 2.0
    value = statistic / 2.0
    if value == 0.0:
        return 1.0
    epsilon = 3e-14
    if value < shape + 1.0:
        term = 1.0 / shape
        total = term
        shifted = shape
        for _ in range(1, 1001):
            shifted += 1.0
            term *= value / shifted
            total += term
            if abs(term) <= abs(total) * epsilon:
                lower = total * math.exp(
                    -value + shape * math.log(value) - math.lgamma(shape)
                )
                return max(0.0, min(1.0, 1.0 - lower))
        raise NumericalError("chi-square series did not converge")
    tiny = 1e-300
    shifted = value + 1.0 - shape
    c_value = 1.0 / tiny
    d_value = 1.0 / shifted
    result = d_value
    for iteration in range(1, 1001):
        numerator = -iteration * (iteration - shape)
        shifted += 2.0
        d_value = numerator * d_value + shifted
        if abs(d_value) < tiny:
            d_value = tiny
        c_value = shifted + numerator / c_value
        if abs(c_value) < tiny:
            c_value = tiny
        d_value = 1.0 / d_value
        change = d_value * c_value
        result *= change
        if abs(change - 1.0) <= epsilon:
            upper = (
                math.exp(-value + shape * math.log(value) - math.lgamma(shape)) * result
            )
            return max(0.0, min(1.0, upper))
    raise NumericalError("chi-square fraction did not converge")


def _likelihood_terms(
    parameters: FloatVector,
    features: FloatMatrix,
    first: IntVector,
    last: IntVector,
    family: OrdinalFamily,
    threshold_count: int,
) -> tuple[float, FloatVector, FloatMatrix]:
    thresholds = parameters[:threshold_count]
    slopes = parameters[threshold_count:]
    predictor = features @ slopes
    count = parameters.size
    score = np.zeros(count, dtype=np.float64)
    hessian = np.zeros((count, count), dtype=np.float64)
    log_likelihood = 0.0
    for row_index, (start, stop) in enumerate(zip(first, last, strict=True)):
        derivative = np.zeros(count, dtype=np.float64)
        second = np.zeros((count, count), dtype=np.float64)
        upper_probability = 1.0
        lower_probability = 0.0
        if start > 0:
            boundary = start - 1
            z = np.asarray([thresholds[boundary] + predictor[row_index]])
            upper, density, curvature = _family_values(z, family)
            upper_probability = float(upper[0])
            vector = np.zeros(count, dtype=np.float64)
            vector[boundary] = 1.0
            vector[threshold_count:] = features[row_index]
            derivative += float(density[0]) * vector
            second += float(curvature[0]) * np.outer(vector, vector)
        if stop < threshold_count:
            boundary = stop
            z = np.asarray([thresholds[boundary] + predictor[row_index]])
            lower, density, curvature = _family_values(z, family)
            lower_probability = float(lower[0])
            vector = np.zeros(count, dtype=np.float64)
            vector[boundary] = 1.0
            vector[threshold_count:] = features[row_index]
            derivative -= float(density[0]) * vector
            second -= float(curvature[0]) * np.outer(vector, vector)
        probability = upper_probability - lower_probability
        if not math.isfinite(probability) or probability <= MIN_PROBABILITY:
            return -math.inf, score, hessian
        log_likelihood += math.log(probability)
        score += derivative / probability
        hessian += second / probability - np.outer(derivative, derivative) / (
            probability * probability
        )
    return log_likelihood, score, hessian


def _tridiagonal_solve(
    matrix: FloatMatrix, right_hand_side: FloatMatrix
) -> FloatMatrix:
    """Solve a positive tridiagonal system without materializing a factor."""
    count = matrix.shape[0]
    diagonal = np.asarray(matrix.diagonal(), dtype=np.float64).copy()
    upper = np.asarray(
        [matrix[index, index + 1] for index in range(count - 1)],
        dtype=np.float64,
    )
    lower = upper.copy()
    result = right_hand_side.copy()
    for index in range(1, count):
        if abs(float(diagonal[index - 1])) <= 1e-14:
            raise RankDeficiencyError("ordinal information matrix is singular")
        multiplier = lower[index - 1] / diagonal[index - 1]
        diagonal[index] -= multiplier * upper[index - 1]
        result[index] -= multiplier * result[index - 1]
    if abs(float(diagonal[-1])) <= 1e-14:
        raise RankDeficiencyError("ordinal information matrix is singular")
    result[-1] /= diagonal[-1]
    for index in range(count - 2, -1, -1):
        result[index] = (result[index] - upper[index] * result[index + 1]) / diagonal[
            index
        ]
    return result


def _information_step(
    information: FloatMatrix, score: FloatVector, threshold_count: int
) -> FloatVector:
    """Use the exact-response bordered tridiagonal structure when available."""
    threshold_block = information[:threshold_count, :threshold_count]
    has_off_band = any(
        abs(float(threshold_block[row, column])) > 1e-12
        for row in range(threshold_count)
        for column in range(threshold_count)
        if abs(row - column) > 1
    )
    if has_off_band:
        try:
            return np.asarray(np.linalg.solve(information, score), dtype=np.float64)
        except np.linalg.LinAlgError as error:
            raise RankDeficiencyError(
                "ordinal information matrix is singular"
            ) from error
    slope_count = information.shape[0] - threshold_count
    threshold_score = score[:threshold_count, None]
    cross = information[:threshold_count, threshold_count:]
    right_hand_side = np.empty((threshold_count, slope_count + 1), dtype=np.float64)
    right_hand_side[:, :1] = threshold_score
    right_hand_side[:, 1:] = cross
    solved = _tridiagonal_solve(threshold_block, right_hand_side)
    threshold_solution = solved[:, 0]
    if slope_count == 0:
        return threshold_solution
    inverse_cross = solved[:, 1:]
    slope_information = information[threshold_count:, threshold_count:]
    schur = slope_information - cross.T @ inverse_cross
    slope_score = score[threshold_count:] - cross.T @ threshold_solution
    try:
        slope_solution = np.asarray(
            np.linalg.solve(schur, slope_score), dtype=np.float64
        )
    except np.linalg.LinAlgError as error:
        raise RankDeficiencyError("ordinal information matrix is singular") from error
    result = np.empty(information.shape[0], dtype=np.float64)
    result[:threshold_count] = threshold_solution - inverse_cross @ slope_solution
    result[threshold_count:] = slope_solution
    return result


def _fit_parameters(
    features: FloatMatrix,
    first: IntVector,
    last: IntVector,
    level_count: int,
    family: OrdinalFamily,
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[FloatVector, FloatMatrix, int, float]:
    threshold_count = level_count - 1
    exact = first == last
    starts = np.asarray(first)
    thresholds = np.empty(threshold_count, dtype=np.float64)
    for index in range(threshold_count):
        if bool(exact.all()):
            probability = float(np.mean(starts >= index + 1))
        else:
            definitely_above = float(np.mean(first >= index + 1))
            possibly_above = float(np.mean(last >= index + 1))
            probability = (definitely_above + possibly_above) * 0.5
        probability = min(max(probability, 1e-6), 1.0 - 1e-6)
        thresholds[index] = _inverse_family(probability, family)
    for index in range(1, threshold_count):
        thresholds[index] = min(thresholds[index], thresholds[index - 1] - 1e-4)
    parameters = np.empty(threshold_count + features.shape[1], dtype=np.float64)
    parameters[:threshold_count] = thresholds
    parameters[threshold_count:] = 0.0
    log_likelihood, score, hessian = _likelihood_terms(
        parameters, features, first, last, family, threshold_count
    )
    if not math.isfinite(log_likelihood):
        raise NumericalError("ordinal likelihood is not finite at initialization")
    for iteration in range(1, max_iterations + 1):
        information = -hessian
        step = _information_step(information, score, threshold_count)
        scale = 1.0
        accepted = False
        candidate = parameters
        candidate_likelihood = log_likelihood
        candidate_score = score
        candidate_hessian = hessian
        for _ in range(80):
            candidate = parameters + scale * step
            candidate_thresholds = candidate[:threshold_count]
            if bool((candidate_thresholds[:-1] > candidate_thresholds[1:]).all()):
                trial = _likelihood_terms(
                    candidate, features, first, last, family, threshold_count
                )
                if math.isfinite(trial[0]) and trial[0] >= log_likelihood - 1e-12:
                    candidate_likelihood, candidate_score, candidate_hessian = trial
                    accepted = True
                    break
            scale *= 0.5
        if not accepted:
            raise ConvergenceError("ordinal step halving failed")
        applied = scale * step
        likelihood_change = abs(candidate_likelihood - log_likelihood)
        parameters = candidate
        log_likelihood = candidate_likelihood
        score = candidate_score
        hessian = candidate_hessian
        if float(np.max(np.abs(applied))) <= tolerance * (
            1.0 + float(np.max(np.abs(parameters)))
        ) and likelihood_change <= tolerance * (1.0 + abs(log_likelihood)):
            information = -hessian
            try:
                covariance = np.linalg.solve(information, np.eye(parameters.size))
            except np.linalg.LinAlgError as error:
                raise RankDeficiencyError(
                    "ordinal information matrix is singular"
                ) from error
            covariance = (covariance + covariance.T) * 0.5
            return parameters, covariance, iteration, log_likelihood
    raise ConvergenceError(
        f"ordinal fit did not converge in {max_iterations} iterations"
    )


def _response_contract(
    response: Iterable[int | float] | CensoredResponse,
) -> tuple[tuple[float, ...], IntVector, IntVector, bool]:
    if isinstance(response, CensoredResponse):
        turnbull = response.turnbull()
        if not turnbull.converged:
            raise ConvergenceError("Turnbull self-consistency did not converge")
        levels = tuple(
            float((left + right) * 0.5)
            if math.isfinite(left) and math.isfinite(right)
            else float(right if left == -math.inf else left)
            for left, right in zip(turnbull.lower, turnbull.upper, strict=True)
        )
        if len(levels) < 3:
            raise InputValidationError(
                "censored ordinal response requires at least three estimable intervals"
            )
        return (
            levels,
            np.asarray(turnbull.first, dtype=np.int64),
            np.asarray(turnbull.last, dtype=np.int64),
            True,
        )
    values = tuple(response)
    if (
        not values
        or len(values) > MAX_OBSERVATIONS
        or any(not _finite_number(value) for value in values)
    ):
        raise InputValidationError(
            "ordinal response must contain finite numeric values"
        )
    levels = tuple(sorted({float(value) for value in values}))
    if len(levels) < 3:
        raise InputValidationError(
            "ordinal response must contain at least three levels"
        )
    mapping = {value: index for index, value in enumerate(levels)}
    indices = np.asarray([mapping[float(value)] for value in values], dtype=np.int64)
    return levels, indices, indices.copy(), False


def fit_orm(
    response: Iterable[int | float] | CensoredResponse,
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    family: OrdinalFamily = "logistic",
    feature_names: Iterable[str] | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-10,
    estimator: OrdinalEstimator = "orm",
) -> OrdinalResult:
    """Fit an unpenalized cumulative-link model, including interval outcomes."""
    if family not in {"logistic", "probit", "loglog", "cloglog", "cauchit"}:
        raise InputValidationError(f"unsupported ordinal family: {family!r}")
    if isinstance(max_iterations, bool) or not 1 <= max_iterations <= 10_000:
        raise InputValidationError("max_iterations must be between 1 and 10000")
    if not _finite_number(tolerance) or not 0.0 < tolerance < 1.0:
        raise InputValidationError("tolerance must be finite and between 0 and 1")
    levels, first, last, censored = _response_contract(response)
    if isinstance(features, DesignMatrix):
        if feature_names is not None and tuple(feature_names) != features.column_names:
            raise InputValidationError(
                "feature_names must match DesignMatrix column identity"
            )
        if (
            design_fingerprint is not None
            and design_fingerprint != features.specification_fingerprint
        ):
            raise InputValidationError(
                "design_fingerprint must match the DesignMatrix specification"
            )
        values = features.rows
        feature_names = features.column_names
        design_fingerprint = features.specification_fingerprint
    else:
        values = features
    matrix = _as_feature_matrix(values)
    if matrix.shape[0] != first.size:
        raise InputValidationError(
            "response and features must have the same number of rows"
        )
    if matrix.shape[1] + len(levels) - 1 > MAX_PARAMETERS:
        raise InputValidationError("ordinal fit exceeds the parameter limit")
    if matrix.shape[0] <= matrix.shape[1] + len(levels) - 1:
        raise InputValidationError(
            "ordinal fit requires more observations than parameters"
        )
    if int(np.linalg.matrix_rank(matrix)) != matrix.shape[1]:
        raise RankDeficiencyError("ordinal design matrix must have full column rank")
    names = _feature_names(matrix.shape[1], feature_names)
    parameters, covariance, iterations, log_likelihood = _fit_parameters(
        matrix,
        first,
        last,
        len(levels),
        family,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    null_features = np.empty((matrix.shape[0], 0), dtype=np.float64)
    _, _, _, null_log_likelihood = _fit_parameters(
        null_features,
        first,
        last,
        len(levels),
        family,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    threshold_count = len(levels) - 1
    thresholds = parameters[:threshold_count]
    slopes = parameters[threshold_count:]
    predictor = matrix @ slopes
    threshold_names = tuple(f"y>={level:g}" for level in levels[1:])
    probabilities = _probability_rows(thresholds, predictor, family)
    return OrdinalResult(
        estimator=estimator,
        family=family,
        response_levels=levels,
        threshold_names=threshold_names,
        feature_names=names,
        thresholds=tuple(float(value) for value in thresholds),
        coefficients=tuple(float(value) for value in slopes),
        covariance=tuple(tuple(float(value) for value in row) for row in covariance),
        linear_predictors=tuple(float(thresholds[0] + value) for value in predictor),
        fitted_probabilities=probabilities,
        deviance=(-2.0 * null_log_likelihood, -2.0 * log_likelihood),
        iterations=iterations,
        n_observations=matrix.shape[0],
        design_fingerprint=design_fingerprint,
        censored=censored,
    )


def fit_ordinal_lrm(
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    feature_names: Iterable[str] | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-10,
) -> OrdinalResult:
    """Fit the multi-intercept proportional-odds subset of ``lrm``."""
    if isinstance(response, CensoredResponse):
        raise InputValidationError("ordinal lrm does not accept censored responses")
    return fit_orm(
        response,
        features,
        family="logistic",
        feature_names=feature_names,
        design_fingerprint=design_fingerprint,
        max_iterations=max_iterations,
        tolerance=tolerance,
        estimator="lrm",
    )


__all__ = [
    "CensoredResponse",
    "OrdinalDiagnostics",
    "OrdinalResult",
    "OrdinalTest",
    "TurnbullResult",
    "fit_ordinal_lrm",
    "fit_orm",
]
