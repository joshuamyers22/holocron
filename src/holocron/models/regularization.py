"""Quadratic penalties and alternative covariance estimators."""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Literal, TypeAlias, cast

import numpy as np
import numpy.typing as npt

from holocron.design import DesignMatrix
from holocron.exceptions import (
    ConvergenceError,
    InputValidationError,
    NumericalError,
    RankDeficiencyError,
)
from holocron.models.glm import fit_glm, fit_lrm
from holocron.models.linear import OlsResult, fit_ols
from holocron.models.logistic import BinaryLogisticResult

FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]
ModelResult: TypeAlias = OlsResult | BinaryLogisticResult

MAX_OBSERVATIONS = 1_000_000
MAX_PARAMETERS = 257
MAX_BOOTSTRAP_REPLICATES = 10_000


@dataclass(frozen=True, slots=True)
class PenalizedResult:
    """A quadratic-penalty fit with explicit effective degrees of freedom."""

    model_type: Literal["ols", "lrm-binary"]
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    linear_predictors: tuple[float, ...]
    fitted_values: tuple[float, ...]
    residuals: tuple[float, ...]
    penalty_weights: tuple[float, ...]
    effective_degrees_of_freedom: float
    residual_degrees_of_freedom: float | None
    residual_scale: float | None
    iterations: int | None
    n_observations: int
    n_features: int
    includes_intercept: bool
    design_fingerprint: str | None

    def predict_linear(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> tuple[float, ...]:
        """Predict on the linear scale while enforcing design identity."""
        matrix = _prediction_design(self, features)
        values = matrix @ np.asarray(self.coefficients, dtype=np.float64)
        return tuple(float(value) for value in values)

    def predict_response(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> tuple[float, ...]:
        """Predict fitted means: Gaussian means or binary probabilities."""
        linear = np.asarray(self.predict_linear(features), dtype=np.float64)
        if self.model_type == "lrm-binary":
            linear = _expit(linear)
        return tuple(float(value) for value in linear)


@dataclass(frozen=True, slots=True)
class CovarianceEstimate:
    """A named robust or bootstrap covariance estimate."""

    method: Literal["robust", "bootstrap"]
    coefficient_names: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]
    cluster_count: int | None
    replicate_count: int | None
    seed: int | None
    coefficient_mean: tuple[float, ...] | None


def _numeric_vector(values: Iterable[float], *, name: str) -> FloatVector:
    try:
        items = tuple(float(value) for value in values)
    except (TypeError, ValueError) as error:
        raise InputValidationError(f"{name} must be numeric") from error
    if not items or len(items) > MAX_OBSERVATIONS:
        raise InputValidationError(f"{name} has an unsupported length")
    if not all(math.isfinite(value) for value in items):
        raise InputValidationError(f"{name} must contain only finite values")
    return np.asarray(items, dtype=np.float64)


def _binary_vector(values: Iterable[int | float]) -> FloatVector:
    raw = tuple(values)
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or float(value) not in {0.0, 1.0}
        for value in raw
    ):
        raise InputValidationError("binary response must contain only numeric 0 and 1")
    response = _numeric_vector(raw, name="response")
    if len(set(float(value) for value in response)) != 2:
        raise InputValidationError("binary response must contain both 0 and 1")
    return response


def _numeric_matrix(
    values: Iterable[Iterable[float]], *, name: str = "features"
) -> FloatMatrix:
    try:
        rows = tuple(tuple(float(value) for value in row) for row in values)
    except (TypeError, ValueError) as error:
        raise InputValidationError(f"{name} must be numeric") from error
    if not rows or not rows[0]:
        raise InputValidationError(f"{name} must contain rows and columns")
    width = len(rows[0])
    if (
        len(rows) > MAX_OBSERVATIONS
        or width >= MAX_PARAMETERS
        or any(len(row) != width for row in rows)
    ):
        raise InputValidationError(f"{name} has an unsupported shape")
    if not all(math.isfinite(value) for row in rows for value in row):
        raise InputValidationError(f"{name} must contain only finite values")
    return np.asarray(rows, dtype=np.float64)


def _fit_inputs(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    feature_names: Iterable[str] | None,
    include_intercept: bool | None,
    design_fingerprint: str | None,
) -> tuple[FloatVector, FloatMatrix, tuple[str, ...], bool, str | None]:
    y = _numeric_vector(response, name="response")
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
        names = features.column_names
        include = features.include_intercept
        fingerprint = features.specification_fingerprint
    else:
        feature_values = features
        include = True if include_intercept is None else include_intercept
        if not isinstance(cast(object, include), bool):
            raise InputValidationError("include_intercept must be boolean")
        matrix_for_names = _numeric_matrix(feature_values)
        feature_values = tuple(
            tuple(float(value) for value in row) for row in matrix_for_names
        )
        names = (
            tuple(feature_names)
            if feature_names is not None
            else tuple(f"x{index + 1}" for index in range(matrix_for_names.shape[1]))
        )
        fingerprint = design_fingerprint
    matrix = _numeric_matrix(feature_values)
    if matrix.shape[0] != y.size:
        raise InputValidationError("response and features must have the same row count")
    if len(names) != matrix.shape[1] or any(not name for name in names):
        raise InputValidationError("feature names must match columns and be non-empty")
    if len(set(names)) != len(names):
        raise InputValidationError("feature names must be unique")
    return y, matrix, names, include, fingerprint


def _penalty_weights(
    penalty: float | Mapping[str, float], names: tuple[str, ...]
) -> FloatVector:
    if isinstance(penalty, Mapping):
        untyped_penalty = cast(Mapping[object, object], penalty)
        if any(not isinstance(key, str) for key in untyped_penalty):
            raise InputValidationError("penalty coefficient names must be strings")
        unknown = sorted(set(penalty) - set(names))
        if unknown:
            raise InputValidationError(
                f"unknown penalty coefficients: {', '.join(unknown)}"
            )
        raw = tuple(penalty.get(name, 0.0) for name in names)
    else:
        raw = (penalty,) * len(names)
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or float(value) < 0.0
        for value in raw
    ):
        raise InputValidationError("penalty weights must be finite and non-negative")
    result = np.asarray(raw, dtype=np.float64)
    if not any(float(value) > 0.0 for value in result):
        raise InputValidationError("at least one penalty weight must be positive")
    return result


def _design_with_intercept(features: FloatMatrix, include: bool) -> FloatMatrix:
    if not include:
        return features
    return np.column_stack(  # pyright: ignore[reportUnknownMemberType]
        (np.ones(features.shape[0], dtype=np.float64), features)
    )


def _full_penalty(weights: FloatVector, include: bool) -> FloatMatrix:
    size = len(weights) + int(include)
    result = np.zeros((size, size), dtype=np.float64)
    offset = int(include)
    for index, value in enumerate(weights):
        result[offset + index, offset + index] = value
    return result


def _matrix_tuple(matrix: FloatMatrix) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(value) for value in row) for row in matrix)


def _expit(values: FloatVector) -> FloatVector:
    output = np.empty_like(values)
    positive = values >= 0.0
    output[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponential = np.exp(values[~positive])
    output[~positive] = exponential / (1.0 + exponential)
    return output


def fit_penalized_ols(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    penalty: float | Mapping[str, float],
    variance: Literal["simple", "sandwich"] = "simple",
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
) -> PenalizedResult:
    """Fit diagonal quadratic-penalty OLS with the rms variance choices."""
    if variance not in {"simple", "sandwich"}:
        raise InputValidationError("variance must be 'simple' or 'sandwich'")
    y, feature_matrix, names, include, fingerprint = _fit_inputs(
        response,
        features,
        feature_names=feature_names,
        include_intercept=include_intercept,
        design_fingerprint=design_fingerprint,
    )
    design = _design_with_intercept(feature_matrix, include)
    if y.size <= design.shape[1]:
        raise InputValidationError("penalized OLS requires more rows than parameters")
    weights = _penalty_weights(penalty, names)
    penalty_matrix = _full_penalty(weights, include)
    crossproduct = design.T @ design
    penalized_crossproduct = crossproduct + penalty_matrix
    try:
        inverse = np.linalg.solve(
            penalized_crossproduct,
            np.eye(penalized_crossproduct.shape[0], dtype=np.float64),
        )
    except np.linalg.LinAlgError as error:
        raise RankDeficiencyError("penalty does not identify the OLS design") from error
    coefficients = inverse @ design.T @ y
    fitted = design @ coefficients
    residual_values = y - fitted
    sum_squares = float(residual_values @ residual_values)
    penalized_variance = float(
        (sum_squares + coefficients @ penalty_matrix @ coefficients) / y.size
    )
    if penalized_variance <= 0.0:
        raise NumericalError("penalized OLS residual variance is zero")
    covariance = (
        penalized_variance * inverse
        if variance == "simple"
        else penalized_variance * inverse @ crossproduct @ inverse
    )
    covariance = (covariance + covariance.T) * 0.5
    unpenalized_variance = sum_squares / y.size
    effective_diagonal = np.diag(  # pyright: ignore[reportUnknownMemberType]
        (crossproduct / unpenalized_variance) @ (penalized_variance * inverse)
    )
    effective_df = float(np.sum(effective_diagonal))
    coefficient_names = ("Intercept", *names) if include else names
    return PenalizedResult(
        model_type="ols",
        coefficient_names=coefficient_names,
        coefficients=tuple(float(value) for value in coefficients),
        covariance=_matrix_tuple(covariance),
        linear_predictors=tuple(float(value) for value in fitted),
        fitted_values=tuple(float(value) for value in fitted),
        residuals=tuple(float(value) for value in residual_values),
        penalty_weights=tuple(float(value) for value in weights),
        effective_degrees_of_freedom=effective_df,
        residual_degrees_of_freedom=float(y.size - effective_df),
        residual_scale=math.sqrt(penalized_variance),
        iterations=None,
        n_observations=int(y.size),
        n_features=feature_matrix.shape[1],
        includes_intercept=include,
        design_fingerprint=fingerprint,
    )


def fit_penalized_lrm(
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    penalty: float | Mapping[str, float],
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-10,
) -> PenalizedResult:
    """Fit binary lrm with a diagonal quadratic penalty on slopes."""
    if (
        isinstance(cast(object, max_iterations), bool)
        or not isinstance(max_iterations, Integral)
        or not 1 <= max_iterations <= 10_000
    ):
        raise InputValidationError("max_iterations must be between 1 and 10000")
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, Real)
        or not math.isfinite(float(tolerance))
        or not 0.0 < float(tolerance) < 1.0
    ):
        raise InputValidationError("tolerance must be finite and between 0 and 1")
    raw_response = tuple(response)
    y, feature_matrix, names, include, fingerprint = _fit_inputs(
        raw_response,
        features,
        feature_names=feature_names,
        include_intercept=include_intercept,
        design_fingerprint=design_fingerprint,
    )
    y = _binary_vector(raw_response)
    if not include:
        raise InputValidationError("binary lrm requires an intercept")
    design = _design_with_intercept(feature_matrix, include)
    if y.size <= design.shape[1]:
        raise InputValidationError("penalized lrm requires more rows than parameters")
    weights = _penalty_weights(penalty, names)
    penalty_matrix = _full_penalty(weights, include)
    coefficients = np.zeros(design.shape[1], dtype=np.float64)
    prevalence = float(np.mean(y))
    coefficients[0] = math.log(prevalence / (1.0 - prevalence))

    def objective(candidate: FloatVector) -> float:
        linear = design @ candidate
        log_likelihood = float(np.sum(y * linear - np.logaddexp(0.0, linear)))
        return log_likelihood - 0.5 * float(candidate @ penalty_matrix @ candidate)

    current_objective = objective(coefficients)
    completed = 0
    for iteration in range(1, max_iterations + 1):
        completed = iteration
        linear = design @ coefficients
        probabilities = _expit(linear)
        information = (
            design.T @ ((probabilities * (1.0 - probabilities))[:, None] * design)
            + penalty_matrix
        )
        score = design.T @ (y - probabilities) - penalty_matrix @ coefficients
        try:
            step = np.linalg.solve(information, score)
        except np.linalg.LinAlgError as error:
            raise NumericalError(
                "penalized lrm information matrix is singular"
            ) from error
        step_scale = 1.0
        accepted = False
        candidate = coefficients
        candidate_objective = current_objective
        for _ in range(60):
            proposed = coefficients + step_scale * step
            proposed_objective = objective(proposed)
            if (
                math.isfinite(proposed_objective)
                and proposed_objective >= current_objective
            ):
                candidate = proposed
                candidate_objective = proposed_objective
                accepted = True
                break
            step_scale *= 0.5
        if not accepted:
            raise ConvergenceError("penalized lrm step-halving failed")
        change = abs(candidate_objective - current_objective)
        coefficients = candidate
        current_objective = candidate_objective
        if change / (0.1 + abs(current_objective)) < tolerance:
            break
    else:
        raise ConvergenceError(
            f"penalized lrm fit did not converge in {max_iterations} iterations"
        )
    linear = design @ coefficients
    probabilities = _expit(linear)
    working_weights = probabilities * (1.0 - probabilities)
    unpenalized_information = design.T @ (working_weights[:, None] * design)
    penalized_information = unpenalized_information + penalty_matrix
    try:
        covariance = np.linalg.solve(
            penalized_information,
            np.eye(penalized_information.shape[0], dtype=np.float64),
        )
    except np.linalg.LinAlgError as error:
        raise NumericalError("penalized lrm covariance is singular") from error
    covariance = (covariance + covariance.T) * 0.5
    effective_df = float(
        np.trace(  # pyright: ignore[reportUnknownMemberType]
            unpenalized_information @ covariance
        )
    )
    return PenalizedResult(
        model_type="lrm-binary",
        coefficient_names=("Intercept", *names),
        coefficients=tuple(float(value) for value in coefficients),
        covariance=_matrix_tuple(covariance),
        linear_predictors=tuple(float(value) for value in linear),
        fitted_values=tuple(float(value) for value in probabilities),
        residuals=tuple(float(value) for value in y - probabilities),
        penalty_weights=tuple(float(value) for value in weights),
        effective_degrees_of_freedom=effective_df,
        residual_degrees_of_freedom=None,
        residual_scale=None,
        iterations=completed,
        n_observations=int(y.size),
        n_features=feature_matrix.shape[1],
        includes_intercept=True,
        design_fingerprint=fingerprint,
    )


def _prediction_design(
    result: PenalizedResult,
    features: Iterable[Iterable[float]] | DesignMatrix,
) -> FloatMatrix:
    if isinstance(features, DesignMatrix):
        if (
            result.design_fingerprint is not None
            and features.specification_fingerprint != result.design_fingerprint
        ):
            raise InputValidationError(
                "prediction design fingerprint differs from the fitted design"
            )
        values = features.rows
    else:
        values = features
    matrix = _numeric_matrix(values)
    if matrix.shape[1] != result.n_features:
        raise InputValidationError(
            f"features has {matrix.shape[1]} columns; expected {result.n_features}"
        )
    return _design_with_intercept(matrix, result.includes_intercept)


def _analysis_design(
    result: ModelResult,
    features: Iterable[Iterable[float]] | DesignMatrix,
) -> FloatMatrix:
    if isinstance(features, DesignMatrix):
        if (
            result.design_fingerprint is not None
            and features.specification_fingerprint != result.design_fingerprint
        ):
            raise InputValidationError(
                "analysis design fingerprint differs from the fitted design"
            )
        raw = features.rows
    else:
        raw = features
    matrix = _numeric_matrix(raw)
    if matrix.shape != (result.n_observations, result.n_features):
        raise InputValidationError("analysis features must match the fitted dimensions")
    design = _design_with_intercept(matrix, result.includes_intercept)
    reconstructed = design @ np.asarray(result.coefficients, dtype=np.float64)
    expected = np.asarray(
        result.fitted_values
        if isinstance(result, OlsResult)
        else result.linear_predictors,
        dtype=np.float64,
    )
    scale = 1.0 + float(np.max(np.abs(expected)))
    if float(np.max(np.abs(reconstructed - expected))) > 1e-10 * scale:
        raise InputValidationError("analysis features differ from the fitted design")
    return design


def _analysis_response(
    result: ModelResult, response: Iterable[int | float]
) -> FloatVector:
    raw = tuple(response)
    if isinstance(result, OlsResult):
        values = _numeric_vector(raw, name="response")
        if values.size != result.n_observations:
            raise InputValidationError(
                "response must match the fitted observation count"
            )
        reconstructed = np.asarray(result.fitted_values) + np.asarray(result.residuals)
        scale = 1.0 + float(np.max(np.abs(reconstructed)))
        if float(np.max(np.abs(values - reconstructed))) > 1e-10 * scale:
            raise InputValidationError("response differs from the fitted OLS response")
        return values
    values = _binary_vector(raw)
    if values.size != result.n_observations:
        raise InputValidationError("response must match the fitted observation count")
    linear = np.asarray(result.linear_predictors, dtype=np.float64)
    deviance = -2.0 * float(np.sum(values * linear - np.logaddexp(0.0, linear)))
    residual_deviance = result.deviance[1]
    scale = 1.0 + abs(residual_deviance)
    if abs(deviance - residual_deviance) > 1e-10 * scale:
        raise InputValidationError("response differs from the fitted binary response")
    return values


def _clusters(
    values: Iterable[Hashable] | None, count: int
) -> tuple[tuple[int, ...], ...]:
    raw = tuple(range(count)) if values is None else tuple(values)
    if len(raw) != count:
        raise InputValidationError("clusters must match the fitted observation count")
    groups: dict[Hashable, list[int]] = {}
    try:
        for index, value in enumerate(raw):
            if value is None or (isinstance(value, float) and math.isnan(value)):
                raise InputValidationError("clusters must not contain missing values")
            groups.setdefault(value, []).append(index)
    except TypeError as error:
        raise InputValidationError("cluster labels must be hashable") from error
    if len(groups) < 2:
        raise InputValidationError("robust covariance requires at least two clusters")
    return tuple(tuple(indices) for indices in groups.values())


def _glm_score_residuals(
    response: FloatVector, design: FloatMatrix, target: FloatVector
) -> FloatVector:
    """Reproduce the working-weight score retained by the accepted Glm fit."""
    probabilities = (response + 0.5) / 2.0
    linear = np.log(probabilities / (1.0 - probabilities))
    for _ in range(100):
        old_weights = probabilities * (1.0 - probabilities)
        working = linear + (response - probabilities) / old_weights
        information = design.T @ (old_weights[:, None] * design)
        coefficients = np.linalg.solve(information, design.T @ (old_weights * working))
        linear = design @ coefficients
        probabilities = _expit(linear)
        scale = 1.0 + float(np.max(np.abs(target)))
        if float(np.max(np.abs(coefficients - target))) <= 1e-10 * scale:
            final_weights = probabilities * (1.0 - probabilities)
            return (response - probabilities) * old_weights / final_weights
    raise NumericalError("could not reconstruct Glm score residuals")


def robust_covariance(
    result: ModelResult,
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    clusters: Iterable[Hashable] | None = None,
) -> CovarianceEstimate:
    """Compute the uncorrected Huber cluster-sandwich covariance."""
    design = _analysis_design(result, features)
    y = _analysis_response(result, response)
    if y.size != result.n_observations:
        raise InputValidationError("response must match the fitted observation count")
    if isinstance(result, OlsResult):
        residual_values = np.asarray(result.residuals, dtype=np.float64)
        try:
            bread = np.linalg.solve(
                design.T @ design,
                np.eye(design.shape[1], dtype=np.float64),
            )
        except np.linalg.LinAlgError as error:
            raise RankDeficiencyError("robust covariance design is singular") from error
    else:
        probabilities = np.asarray(result.fitted_probabilities, dtype=np.float64)
        if result.estimator == "glm":
            residual_values = _glm_score_residuals(
                y, design, np.asarray(result.coefficients, dtype=np.float64)
            )
        else:
            residual_values = y - probabilities
        bread = np.asarray(result.covariance, dtype=np.float64)
    score_rows = design * residual_values[:, None]
    grouped = _clusters(clusters, result.n_observations)
    meat = np.zeros((design.shape[1], design.shape[1]), dtype=np.float64)
    for indices in grouped:
        score = np.sum(score_rows[np.asarray(indices, dtype=np.int64), :], axis=0)
        meat += np.outer(score, score)
    estimate = bread @ meat @ bread
    estimate = (estimate + estimate.T) * 0.5
    return CovarianceEstimate(
        method="robust",
        coefficient_names=result.coefficient_names,
        matrix=_matrix_tuple(estimate),
        cluster_count=len(grouped),
        replicate_count=None,
        seed=None,
        coefficient_mean=None,
    )


def _bootstrap_schedule(
    count: int,
    replicates: int,
    seed: int,
    resample_indices: Iterable[Iterable[int]] | None,
) -> tuple[tuple[int, ...], ...]:
    if (
        isinstance(cast(object, replicates), bool)
        or not isinstance(replicates, Integral)
        or not 2 <= replicates <= MAX_BOOTSTRAP_REPLICATES
    ):
        raise InputValidationError(
            f"replicates must be between 2 and {MAX_BOOTSTRAP_REPLICATES}"
        )
    if (
        isinstance(cast(object, seed), bool)
        or not isinstance(seed, Integral)
        or not 0 <= seed < 2**63
    ):
        raise InputValidationError("seed must be an integer between 0 and 2^63 - 1")
    if resample_indices is None:
        generator = np.random.default_rng(seed)
        generated = generator.integers(0, count, size=(replicates, count))
        return tuple(tuple(int(value) for value in row) for row in generated)
    schedule = tuple(tuple(row) for row in resample_indices)
    if len(schedule) != replicates or any(len(row) != count for row in schedule):
        raise InputValidationError(
            "resample schedule must be replicates by observations"
        )
    if any(
        isinstance(cast(object, value), bool)
        or not isinstance(value, Integral)
        or not 0 <= value < count
        for row in schedule
        for value in row
    ):
        raise InputValidationError("resample indices are outside the observation range")
    return schedule


def bootstrap_covariance(
    result: ModelResult,
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    replicates: int = 200,
    seed: int = 1,
    resample_indices: Iterable[Iterable[int]] | None = None,
) -> CovarianceEstimate:
    """Compute iid nonparametric bootstrap covariance by refitting every sample."""
    design = _analysis_design(result, features)
    feature_matrix = design[:, int(result.includes_intercept) :]
    y = _analysis_response(result, response)
    if y.size != result.n_observations:
        raise InputValidationError("response must match the fitted observation count")
    schedule = _bootstrap_schedule(
        result.n_observations, replicates, seed, resample_indices
    )
    estimates: list[tuple[float, ...]] = []
    for number, indices in enumerate(schedule, start=1):
        selected = np.asarray(indices, dtype=np.int64)
        sample_y = tuple(float(value) for value in y[selected])
        sample_x = tuple(
            tuple(float(value) for value in row) for row in feature_matrix[selected, :]
        )
        try:
            if isinstance(result, OlsResult):
                fitted: ModelResult = fit_ols(
                    sample_y,
                    sample_x,
                    feature_names=result.coefficient_names[
                        int(result.includes_intercept) :
                    ],
                    include_intercept=result.includes_intercept,
                )
            elif result.estimator == "glm":
                fitted = fit_glm(
                    sample_y,
                    sample_x,
                    family="binomial",
                    feature_names=result.coefficient_names[
                        int(result.includes_intercept) :
                    ],
                    include_intercept=result.includes_intercept,
                )
            else:
                fitted = fit_lrm(
                    sample_y,
                    sample_x,
                    feature_names=result.coefficient_names[1:],
                    include_intercept=True,
                )
        except Exception as error:
            raise NumericalError(f"bootstrap refit {number} failed") from error
        estimates.append(fitted.coefficients)
    coefficient_array = np.asarray(estimates, dtype=np.float64)
    covariance = np.asarray(
        np.cov(coefficient_array, rowvar=False, ddof=1), dtype=np.float64
    )
    mean = np.mean(coefficient_array, axis=0)
    return CovarianceEstimate(
        method="bootstrap",
        coefficient_names=result.coefficient_names,
        matrix=_matrix_tuple(covariance),
        cluster_count=None,
        replicate_count=replicates,
        seed=seed,
        coefficient_mean=tuple(float(value) for value in mean),
    )


__all__ = [
    "CovarianceEstimate",
    "PenalizedResult",
    "bootstrap_covariance",
    "fit_penalized_lrm",
    "fit_penalized_ols",
    "robust_covariance",
]
