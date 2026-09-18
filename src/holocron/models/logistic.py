"""Owned binary-logistic estimation for the initial lrm/Glm envelope."""

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
    RankDeficiencyError,
    SeparationError,
)

FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]
Estimator = Literal["glm", "lrm"]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

SCHEMA_VERSION = "holocron-binary-logistic-result/v1"
MAX_OBSERVATIONS = 1_000_000
MAX_PARAMETERS = 257
DEFAULT_MAX_ITERATIONS = 100
DEFAULT_TOLERANCE = 1e-10
MIN_WEIGHT = 1e-15
SEPARATION_COEFFICIENT_NORM = 30.0


def _as_binary_vector(values: Iterable[int | float]) -> FloatVector:
    items = tuple(values)
    if not items:
        raise InputValidationError("response must not be empty")
    if len(items) > MAX_OBSERVATIONS:
        raise InputValidationError(
            f"response exceeds the {MAX_OBSERVATIONS}-value limit"
        )
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or float(value) not in {0.0, 1.0}
        for value in items
    ):
        raise InputValidationError("binary response must contain only numeric 0 and 1")
    result = np.asarray(items, dtype=np.float64)
    if len({float(value) for value in result}) == 1:
        raise InputValidationError("binary response must contain both 0 and 1")
    return result


def _as_matrix(values: Iterable[Iterable[float]]) -> FloatMatrix:
    rows = tuple(tuple(float(value) for value in row) for row in values)
    if not rows:
        raise InputValidationError("features must contain at least one row")
    width = len(rows[0])
    if width == 0:
        raise InputValidationError("features must contain at least one column")
    if len(rows) > MAX_OBSERVATIONS or width >= MAX_PARAMETERS:
        raise InputValidationError("features exceeds the supported shape limit")
    if any(len(row) != width for row in rows):
        raise InputValidationError("features rows must have equal lengths")
    if not all(math.isfinite(value) for row in rows for value in row):
        raise InputValidationError("features must contain only finite values")
    return np.asarray(rows, dtype=np.float64)


def _with_intercept(features: FloatMatrix) -> FloatMatrix:
    design: FloatMatrix = np.empty(
        (features.shape[0], features.shape[1] + 1), dtype=np.float64
    )
    design[:, 0] = 1.0
    design[:, 1:] = features
    return design


def _expit(values: FloatVector) -> FloatVector:
    result = np.empty_like(values)
    positive = values >= 0.0
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponent = np.exp(values[~positive])
    result[~positive] = exponent / (1.0 + exponent)
    return result


def _log_likelihood(response: FloatVector, linear_predictors: FloatVector) -> float:
    return float(
        np.sum(response * linear_predictors - np.logaddexp(0.0, linear_predictors))
    )


def _deviance(response: FloatVector, linear_predictors: FloatVector) -> float:
    return -2.0 * _log_likelihood(response, linear_predictors)


def _null_deviance(response: FloatVector) -> float:
    prevalence = float(np.mean(response))
    return -2.0 * float(
        np.sum(
            response * math.log(prevalence) + (1.0 - response) * math.log1p(-prevalence)
        )
    )


def _validated_controls(max_iterations: int, tolerance: float) -> None:
    raw_max_iterations = cast(object, max_iterations)
    if isinstance(raw_max_iterations, bool) or not isinstance(raw_max_iterations, int):
        raise InputValidationError("max_iterations must be an integer")
    if not 1 <= max_iterations <= 10_000:
        raise InputValidationError("max_iterations must be between 1 and 10000")
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, Real)
        or not math.isfinite(float(tolerance))
        or not 0.0 < float(tolerance) < 1.0
    ):
        raise InputValidationError("tolerance must be finite and between 0 and 1")


def _coefficient_names(
    feature_count: int,
    feature_names: Iterable[str] | None,
    *,
    include_intercept: bool,
) -> tuple[str, ...]:
    names = (
        tuple(feature_names)
        if feature_names is not None
        else tuple(f"x{index + 1}" for index in range(feature_count))
    )
    if len(names) != feature_count:
        raise InputValidationError(
            "feature_names must match the number of feature columns"
        )
    if any(not name for name in names):
        raise InputValidationError("feature_names must not contain empty names")
    result = ("Intercept", *names) if include_intercept else names
    if len(set(result)) != len(result):
        raise InputValidationError("coefficient names must be unique")
    return result


def _validate_symmetric(matrix: tuple[tuple[float, ...], ...]) -> None:
    for row_index, row in enumerate(matrix):
        for column_index in range(row_index):
            if not math.isclose(
                row[column_index],
                matrix[column_index][row_index],
                rel_tol=1e-12,
                abs_tol=1e-15,
            ):
                raise InputValidationError("covariance must be symmetric")


@dataclass(frozen=True, slots=True)
class BinaryLogisticResult:
    """Immutable maximum-likelihood result for a binary logit model."""

    estimator: Estimator
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    linear_predictors: tuple[float, ...]
    fitted_probabilities: tuple[float, ...]
    deviance: tuple[float, float]
    iterations: int
    rank: int
    n_observations: int
    n_features: int
    includes_intercept: bool
    design_fingerprint: str | None = None

    def __post_init__(self) -> None:
        tuple_fields = {
            "coefficient_names": self.coefficient_names,
            "coefficients": self.coefficients,
            "covariance": self.covariance,
            "linear_predictors": self.linear_predictors,
            "fitted_probabilities": self.fitted_probabilities,
            "deviance": self.deviance,
        }
        if any(
            not isinstance(cast(object, value), tuple)
            for value in tuple_fields.values()
        ):
            raise InputValidationError("binary result array fields must be tuples")
        if self.estimator not in {"glm", "lrm"}:
            raise InputValidationError("binary estimator must be 'glm' or 'lrm'")
        for name, value in (
            ("iterations", self.iterations),
            ("rank", self.rank),
            ("n_observations", self.n_observations),
            ("n_features", self.n_features),
        ):
            raw_value = cast(object, value)
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                raise InputValidationError(f"{name} must be an integer")
        if not 1 <= self.n_observations <= MAX_OBSERVATIONS:
            raise InputValidationError("n_observations is outside the supported range")
        if self.n_features < 1 or not 1 <= self.iterations <= 10_000:
            raise InputValidationError("result dimensions or iterations are invalid")
        if not isinstance(cast(object, self.includes_intercept), bool):
            raise InputValidationError("includes_intercept must be boolean")
        parameter_count = self.n_features + int(self.includes_intercept)
        if parameter_count > MAX_PARAMETERS or self.rank != parameter_count:
            raise InputValidationError(
                "result must represent a supported full-rank fit"
            )
        if (
            len(self.coefficient_names) != parameter_count
            or len(set(self.coefficient_names)) != parameter_count
            or any(not name for name in self.coefficient_names)
        ):
            raise InputValidationError("coefficient names must be non-empty and unique")
        if len(self.coefficients) != parameter_count:
            raise InputValidationError("coefficients must match the parameter count")
        if len(self.covariance) != parameter_count or any(
            not isinstance(cast(object, row), tuple) or len(row) != parameter_count
            for row in self.covariance
        ):
            raise InputValidationError("covariance must be square by parameter")
        if (
            len(self.linear_predictors) != self.n_observations
            or len(self.fitted_probabilities) != self.n_observations
        ):
            raise InputValidationError("fitted values must match n_observations")
        numeric_values = (
            *self.coefficients,
            *(value for row in self.covariance for value in row),
            *self.linear_predictors,
            *self.fitted_probabilities,
            *self.deviance,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            for value in numeric_values
        ):
            raise InputValidationError("binary result values must be finite numbers")
        if any(not 0.0 <= value <= 1.0 for value in self.fitted_probabilities):
            raise InputValidationError("fitted probabilities must be between 0 and 1")
        if len(self.deviance) != 2 or any(value < 0.0 for value in self.deviance):
            raise InputValidationError("deviance must contain two non-negative values")
        _validate_symmetric(self.covariance)
        validate_sha256(
            self.design_fingerprint, role="design_fingerprint", nullable=True
        )

    def _feature_matrix(
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
            feature_values = features.rows
        else:
            feature_values = features
        matrix = _as_matrix(feature_values)
        if matrix.shape[1] != self.n_features:
            raise InputValidationError(
                f"features has {matrix.shape[1]} columns; expected {self.n_features}"
            )
        return matrix

    def predict_linear(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> tuple[float, ...]:
        """Predict the linear log-odds in fitted feature order."""
        matrix = self._feature_matrix(features)
        design = _with_intercept(matrix) if self.includes_intercept else matrix
        predictions = design @ np.asarray(self.coefficients, dtype=np.float64)
        return tuple(float(value) for value in predictions)

    def predict_probability(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> tuple[float, ...]:
        """Predict event probabilities in fitted feature order."""
        linear = np.asarray(self.predict_linear(features), dtype=np.float64)
        return tuple(float(value) for value in _expit(linear))

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the versioned binary-logistic result document."""
        return {
            "schema_version": SCHEMA_VERSION,
            "result_type": "binary_logistic",
            "estimator": self.estimator,
            "family": "binomial",
            "link": "logit",
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "linear_predictors": list(self.linear_predictors),
            "fitted_probabilities": list(self.fitted_probabilities),
            "deviance": list(self.deviance),
            "iterations": self.iterations,
            "rank": self.rank,
            "n_observations": self.n_observations,
            "n_features": self.n_features,
            "includes_intercept": self.includes_intercept,
            "design_fingerprint": self.design_fingerprint,
        }

    def to_json(self) -> str:
        """Serialize this result as canonical non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical result document."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> BinaryLogisticResult:
        """Reconstruct a binary result from an exact-version document."""
        if not isinstance(document, dict):
            raise InputValidationError("binary result document must be an object")
        raw = cast(dict[str, object], document)
        required = {
            "schema_version",
            "result_type",
            "estimator",
            "family",
            "link",
            "coefficient_names",
            "coefficients",
            "covariance",
            "linear_predictors",
            "fitted_probabilities",
            "deviance",
            "iterations",
            "rank",
            "n_observations",
            "n_features",
            "includes_intercept",
            "design_fingerprint",
        }
        if set(raw) != required:
            raise InputValidationError("binary result document fields differ")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported binary result schema version")
        if raw["result_type"] != "binary_logistic":
            raise InputValidationError("unsupported binary result type")
        if raw["family"] != "binomial" or raw["link"] != "logit":
            raise InputValidationError("unsupported binary family or link")
        array_names = (
            "coefficient_names",
            "coefficients",
            "covariance",
            "linear_predictors",
            "fitted_probabilities",
            "deviance",
        )
        if any(not isinstance(raw[name], list) for name in array_names):
            raise InputValidationError("binary result arrays are malformed")
        covariance = cast(list[object], raw["covariance"])
        if any(not isinstance(row, list) for row in covariance):
            raise InputValidationError("covariance rows must be arrays")
        return cls(
            estimator=cast(Estimator, raw["estimator"]),
            coefficient_names=tuple(cast(list[str], raw["coefficient_names"])),
            coefficients=tuple(cast(list[float], raw["coefficients"])),
            covariance=tuple(tuple(cast(list[float], row)) for row in covariance),
            linear_predictors=tuple(cast(list[float], raw["linear_predictors"])),
            fitted_probabilities=tuple(cast(list[float], raw["fitted_probabilities"])),
            deviance=cast(
                tuple[float, float], tuple(cast(list[float], raw["deviance"]))
            ),
            iterations=cast(int, raw["iterations"]),
            rank=cast(int, raw["rank"]),
            n_observations=cast(int, raw["n_observations"]),
            n_features=cast(int, raw["n_features"]),
            includes_intercept=cast(bool, raw["includes_intercept"]),
            design_fingerprint=cast(str | None, raw["design_fingerprint"]),
        )

    @classmethod
    def from_json(cls, value: str) -> BinaryLogisticResult:
        """Reconstruct a binary result from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="binary logistic result"))


def _separation_check(coefficients: FloatVector, probabilities: FloatVector) -> None:
    weights = probabilities * (1.0 - probabilities)
    if (
        float(np.max(np.abs(coefficients))) >= SEPARATION_COEFFICIENT_NORM
        or float(np.min(weights)) <= MIN_WEIGHT
    ):
        raise SeparationError(
            "binary response appears completely or quasi-completely separated"
        )


def _glm_irls(
    response: FloatVector,
    design: FloatMatrix,
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[FloatVector, FloatVector, FloatVector, FloatMatrix, int]:
    """Match stats::glm.fit's binomial/logit initialization and stop rule."""
    probabilities = (response + 0.5) / 2.0
    linear_predictors = np.log(probabilities / (1.0 - probabilities))
    previous_deviance = _deviance(response, linear_predictors)
    parameter_count = design.shape[1]
    information = np.empty((parameter_count, parameter_count), dtype=np.float64)
    coefficients = np.zeros(parameter_count, dtype=np.float64)
    for iteration in range(1, max_iterations + 1):
        weights = probabilities * (1.0 - probabilities)
        working_response = linear_predictors + (response - probabilities) / weights
        information = design.T @ (weights[:, None] * design)
        right_hand_side = design.T @ (weights * working_response)
        try:
            coefficients = np.linalg.solve(information, right_hand_side)
        except np.linalg.LinAlgError as error:
            raise SeparationError(
                "binary logistic information matrix became singular; "
                "separation is likely"
            ) from error
        linear_predictors = design @ coefficients
        probabilities = _expit(linear_predictors)
        deviance = _deviance(response, linear_predictors)
        if abs(deviance - previous_deviance) / (0.1 + abs(deviance)) < tolerance:
            _separation_check(coefficients, probabilities)
            covariance = np.linalg.solve(
                information, np.eye(parameter_count, dtype=np.float64)
            )
            covariance = (covariance + covariance.T) * 0.5
            return (
                coefficients,
                linear_predictors,
                probabilities,
                covariance,
                iteration,
            )
        previous_deviance = deviance
    _separation_check(coefficients, probabilities)
    raise ConvergenceError(
        f"binary logistic fit did not converge in {max_iterations} iterations"
    )


def fit_binary_logistic(
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    estimator: Estimator,
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    tolerance: float = DEFAULT_TOLERANCE,
) -> BinaryLogisticResult:
    """Fit a full-rank, unpenalized binary logit model by Newton/IRLS."""
    _validated_controls(max_iterations, tolerance)
    response_vector = _as_binary_vector(response)
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
        if (
            include_intercept is not None
            and include_intercept != features.include_intercept
        ):
            raise InputValidationError(
                "include_intercept must match the DesignMatrix specification"
            )
        feature_values = features.rows
        feature_names = features.column_names
        design_fingerprint = features.specification_fingerprint
        include_intercept = features.include_intercept
    else:
        feature_values = features
        include_intercept = True if include_intercept is None else include_intercept
    if not isinstance(cast(object, include_intercept), bool):
        raise InputValidationError("include_intercept must be boolean")
    feature_matrix = _as_matrix(feature_values)
    if feature_matrix.shape[0] != response_vector.size:
        raise InputValidationError(
            "response and features must have the same number of rows"
        )
    design = _with_intercept(feature_matrix) if include_intercept else feature_matrix
    parameter_count = design.shape[1]
    if response_vector.size <= parameter_count:
        raise InputValidationError(
            "binary logistic fit requires more observations than parameters"
        )
    rank = int(np.linalg.matrix_rank(design))
    if rank != parameter_count:
        raise RankDeficiencyError(
            "binary logistic design matrix must have full column rank"
        )
    coefficient_names = _coefficient_names(
        feature_matrix.shape[1], feature_names, include_intercept=include_intercept
    )

    if estimator == "glm":
        (
            coefficients,
            linear_predictors,
            probabilities,
            covariance_array,
            completed_iterations,
        ) = _glm_irls(
            response_vector,
            design,
            max_iterations=max_iterations,
            tolerance=tolerance,
        )
    else:
        coefficients = np.zeros(parameter_count, dtype=np.float64)
        if include_intercept:
            prevalence = float(np.mean(response_vector))
            coefficients[0] = math.log(prevalence / (1.0 - prevalence))
        linear_predictors = design @ coefficients
        log_likelihood = _log_likelihood(response_vector, linear_predictors)
        converged = False
        completed_iterations = 0
        for current_iteration in range(1, max_iterations + 1):
            completed_iterations = current_iteration
            probabilities = _expit(linear_predictors)
            weights = probabilities * (1.0 - probabilities)
            information = design.T @ (weights[:, None] * design)
            score = design.T @ (response_vector - probabilities)
            try:
                step = np.linalg.solve(information, score)
            except np.linalg.LinAlgError as error:
                raise SeparationError(
                    "binary logistic information matrix became singular; "
                    "separation is likely"
                ) from error
            step_scale = 1.0
            accepted = False
            candidate = coefficients
            candidate_linear = linear_predictors
            candidate_log_likelihood = log_likelihood
            for _ in range(60):
                candidate = coefficients + step_scale * step
                candidate_linear = design @ candidate
                candidate_log_likelihood = _log_likelihood(
                    response_vector, candidate_linear
                )
                if (
                    math.isfinite(candidate_log_likelihood)
                    and candidate_log_likelihood >= log_likelihood - 1e-12
                ):
                    accepted = True
                    break
                step_scale *= 0.5
            if not accepted:
                raise ConvergenceError("binary logistic step halving failed")
            applied_step = step_scale * step
            likelihood_change = abs(candidate_log_likelihood - log_likelihood)
            coefficients = candidate
            linear_predictors = candidate_linear
            log_likelihood = candidate_log_likelihood
            coefficient_scale = 1.0 + float(np.max(np.abs(coefficients)))
            if float(
                np.max(np.abs(applied_step))
            ) <= tolerance * coefficient_scale and likelihood_change <= tolerance * (
                1.0 + abs(log_likelihood)
            ):
                converged = True
                break
        probabilities = _expit(linear_predictors)
        if not converged:
            _separation_check(coefficients, probabilities)
            raise ConvergenceError(
                f"binary logistic fit did not converge in {max_iterations} iterations"
            )
        _separation_check(coefficients, probabilities)
        weights = probabilities * (1.0 - probabilities)
        information = design.T @ (weights[:, None] * design)
        try:
            covariance_array = np.linalg.solve(
                information, np.eye(parameter_count, dtype=np.float64)
            )
        except np.linalg.LinAlgError as error:
            raise SeparationError(
                "binary logistic covariance is singular; separation is likely"
            ) from error
        covariance_array = (covariance_array + covariance_array.T) * 0.5
    return BinaryLogisticResult(
        estimator=estimator,
        coefficient_names=coefficient_names,
        coefficients=tuple(float(value) for value in coefficients),
        covariance=tuple(
            tuple(float(value) for value in row) for row in covariance_array
        ),
        linear_predictors=tuple(float(value) for value in linear_predictors),
        fitted_probabilities=tuple(float(value) for value in probabilities),
        deviance=(
            _null_deviance(response_vector),
            _deviance(response_vector, linear_predictors),
        ),
        iterations=completed_iterations,
        rank=rank,
        n_observations=int(response_vector.size),
        n_features=feature_matrix.shape[1],
        includes_intercept=include_intercept,
        design_fingerprint=design_fingerprint,
    )


__all__ = ["BinaryLogisticResult", "fit_binary_logistic"]
