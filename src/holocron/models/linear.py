"""Ordinary least-squares estimation for the rms-compatible model layer."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from holocron.exceptions import InputValidationError, RankDeficiencyError

FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]


def _as_vector(values: Iterable[float], *, name: str) -> FloatVector:
    items = tuple(float(value) for value in values)
    if not items:
        raise InputValidationError(f"{name} must not be empty")
    if not all(math.isfinite(value) for value in items):
        raise InputValidationError(f"{name} must contain only finite values")
    return np.asarray(items, dtype=np.float64)


def _as_matrix(values: Iterable[Iterable[float]], *, name: str) -> FloatMatrix:
    rows = tuple(tuple(float(value) for value in row) for row in values)
    if not rows:
        raise InputValidationError(f"{name} must contain at least one row")
    width = len(rows[0])
    if width == 0:
        raise InputValidationError(f"{name} must contain at least one column")
    if any(len(row) != width for row in rows):
        raise InputValidationError(f"{name} rows must have equal lengths")
    if not all(math.isfinite(value) for row in rows for value in row):
        raise InputValidationError(f"{name} must contain only finite values")
    return np.asarray(rows, dtype=np.float64)


def _with_intercept(features: FloatMatrix) -> FloatMatrix:
    design: FloatMatrix = np.empty(
        (features.shape[0], features.shape[1] + 1), dtype=np.float64
    )
    design[:, 0] = 1.0
    design[:, 1:] = features
    return design


@dataclass(frozen=True, slots=True)
class OlsResult:
    """An immutable ordinary least-squares result.

    The covariance matrix uses the classical unbiased residual variance
    estimator, matching the initial supported behavior of ``rms::ols``.
    """

    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    fitted_values: tuple[float, ...]
    residuals: tuple[float, ...]
    residual_degrees_of_freedom: int
    residual_scale: float
    rank: int
    n_observations: int
    n_features: int
    includes_intercept: bool

    def predict(self, features: Iterable[Iterable[float]]) -> tuple[float, ...]:
        """Predict from feature columns in the original fitted order."""
        feature_matrix = _as_matrix(features, name="features")
        if feature_matrix.shape[1] != self.n_features:
            raise InputValidationError(
                f"features has {feature_matrix.shape[1]} columns; "
                f"expected {self.n_features}"
            )
        design = (
            _with_intercept(feature_matrix)
            if self.includes_intercept
            else feature_matrix
        )
        coefficients = np.asarray(self.coefficients, dtype=np.float64)
        predictions = design @ coefficients
        return tuple(float(value) for value in predictions)


def fit_ols(
    response: Iterable[float],
    features: Iterable[Iterable[float]],
    *,
    feature_names: Iterable[str] | None = None,
    include_intercept: bool = True,
) -> OlsResult:
    """Fit a full-rank ordinary least-squares model using QR factorization.

    This deliberately narrow first slice accepts an already constructed design
    matrix. Rank-deficient fits are rejected instead of silently dropping
    columns; an explicit alias policy will be added before formula-level OLS is
    declared complete.
    """
    y = _as_vector(response, name="response")
    feature_matrix = _as_matrix(features, name="features")
    if feature_matrix.shape[0] != y.size:
        raise InputValidationError(
            "response and features must have the same number of rows"
        )

    names = (
        tuple(feature_names)
        if feature_names is not None
        else tuple(f"x{index + 1}" for index in range(feature_matrix.shape[1]))
    )
    if len(names) != feature_matrix.shape[1]:
        raise InputValidationError(
            "feature_names must match the number of feature columns"
        )
    if any(not name for name in names):
        raise InputValidationError("feature_names must not contain empty names")
    if len(set(names)) != len(names):
        raise InputValidationError("feature_names must be unique")

    design = _with_intercept(feature_matrix) if include_intercept else feature_matrix
    parameter_count = design.shape[1]
    if y.size <= parameter_count:
        raise InputValidationError("OLS requires positive residual degrees of freedom")

    rank = int(np.linalg.matrix_rank(design))
    if rank != parameter_count:
        raise RankDeficiencyError("OLS design matrix must have full column rank")

    q_matrix, r_matrix = np.linalg.qr(design, mode="reduced")
    coefficients = np.linalg.solve(r_matrix, q_matrix.T @ y)
    fitted_values = design @ coefficients
    residuals = y - fitted_values
    residual_degrees_of_freedom = int(y.size - parameter_count)
    residual_sum_of_squares = sum(float(value) ** 2 for value in residuals)
    residual_variance = residual_sum_of_squares / residual_degrees_of_freedom
    residual_scale = math.sqrt(residual_variance)

    inverse_r = np.linalg.solve(r_matrix, np.eye(parameter_count, dtype=np.float64))
    covariance = residual_variance * (inverse_r @ inverse_r.T)
    coefficient_names = ("Intercept", *names) if include_intercept else names

    return OlsResult(
        coefficient_names=coefficient_names,
        coefficients=tuple(float(value) for value in coefficients),
        covariance=tuple(tuple(float(value) for value in row) for row in covariance),
        fitted_values=tuple(float(value) for value in fitted_values),
        residuals=tuple(float(value) for value in residuals),
        residual_degrees_of_freedom=residual_degrees_of_freedom,
        residual_scale=residual_scale,
        rank=rank,
        n_observations=int(y.size),
        n_features=feature_matrix.shape[1],
        includes_intercept=include_intercept,
    )
