"""Ordinary least-squares estimation for the rms-compatible model layer."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Real
from typing import TypeAlias, cast

import numpy as np
import numpy.typing as npt

from holocron._serialization import (
    canonical_json,
    parse_json_object,
    validate_sha256,
)
from holocron.design import DesignMatrix
from holocron.exceptions import InputValidationError, RankDeficiencyError

FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

SCHEMA_VERSION = "holocron-ols-result/v1"
MAX_RESULT_OBSERVATIONS = 1_000_000
MAX_RESULT_PARAMETERS = 257


def _as_vector(values: Iterable[float], *, name: str) -> FloatVector:
    items = tuple(float(value) for value in values)
    if not items:
        raise InputValidationError(f"{name} must not be empty")
    if not all(math.isfinite(value) for value in items):
        raise InputValidationError(f"{name} must contain only finite values")
    if len(items) > MAX_RESULT_OBSERVATIONS:
        raise InputValidationError(
            f"{name} exceeds the {MAX_RESULT_OBSERVATIONS}-value limit"
        )
    return np.asarray(items, dtype=np.float64)


def _as_matrix(values: Iterable[Iterable[float]], *, name: str) -> FloatMatrix:
    rows = tuple(tuple(float(value) for value in row) for row in values)
    if not rows:
        raise InputValidationError(f"{name} must contain at least one row")
    width = len(rows[0])
    if width == 0:
        raise InputValidationError(f"{name} must contain at least one column")
    if len(rows) > MAX_RESULT_OBSERVATIONS or width > MAX_RESULT_PARAMETERS:
        raise InputValidationError(f"{name} exceeds the supported shape limit")
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
    design_fingerprint: str | None = None

    def __post_init__(self) -> None:
        tuple_fields = {
            "coefficient_names": self.coefficient_names,
            "coefficients": self.coefficients,
            "covariance": self.covariance,
            "fitted_values": self.fitted_values,
            "residuals": self.residuals,
        }
        if any(
            not isinstance(cast(object, value), tuple)
            for value in tuple_fields.values()
        ):
            raise InputValidationError("OLS result array fields must be tuples")
        raw_intercept = cast(object, self.includes_intercept)
        if not isinstance(raw_intercept, bool):
            raise InputValidationError("includes_intercept must be boolean")
        for name, value in (
            ("residual_degrees_of_freedom", self.residual_degrees_of_freedom),
            ("rank", self.rank),
            ("n_observations", self.n_observations),
            ("n_features", self.n_features),
        ):
            raw_value = cast(object, value)
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                raise InputValidationError(f"{name} must be an integer")
        if not 1 <= self.n_observations <= MAX_RESULT_OBSERVATIONS:
            raise InputValidationError(
                f"n_observations must be between 1 and {MAX_RESULT_OBSERVATIONS}"
            )
        if self.n_features < 1:
            raise InputValidationError("n_features must be positive")
        parameter_count = self.n_features + int(self.includes_intercept)
        if parameter_count > MAX_RESULT_PARAMETERS:
            raise InputValidationError(
                f"OLS result exceeds the {MAX_RESULT_PARAMETERS}-parameter limit"
            )
        if self.rank != parameter_count:
            raise InputValidationError("OLS result must represent a full-rank fit")
        if self.residual_degrees_of_freedom != self.n_observations - self.rank:
            raise InputValidationError(
                "residual degrees of freedom must equal observations minus rank"
            )
        if self.residual_degrees_of_freedom <= 0:
            raise InputValidationError("OLS result requires positive residual freedom")
        raw_names = cast(tuple[object, ...], cast(object, self.coefficient_names))
        if len(self.coefficient_names) != parameter_count or any(
            not isinstance(name, str) or not name for name in raw_names
        ):
            raise InputValidationError(
                "coefficient names must match the non-empty parameter vector"
            )
        if len(set(self.coefficient_names)) != parameter_count:
            raise InputValidationError("coefficient names must be unique")
        if len(self.coefficients) != parameter_count:
            raise InputValidationError("coefficients must match the parameter count")
        if len(self.covariance) != parameter_count or any(
            not isinstance(cast(object, row), tuple) or len(row) != parameter_count
            for row in self.covariance
        ):
            raise InputValidationError("covariance must be square by parameter")
        if (
            len(self.fitted_values) != self.n_observations
            or len(self.residuals) != self.n_observations
        ):
            raise InputValidationError(
                "fitted values and residuals must match n_observations"
            )
        numeric_values = (
            *self.coefficients,
            *(value for row in self.covariance for value in row),
            *self.fitted_values,
            *self.residuals,
            self.residual_scale,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            for value in numeric_values
        ):
            raise InputValidationError("OLS result values must be finite numbers")
        if self.residual_scale < 0:
            raise InputValidationError("residual_scale must be non-negative")
        for row_index, row in enumerate(self.covariance):
            for column_index in range(row_index):
                if not math.isclose(
                    row[column_index],
                    self.covariance[column_index][row_index],
                    rel_tol=1e-12,
                    abs_tol=1e-15,
                ):
                    raise InputValidationError("covariance must be symmetric")
        validate_sha256(
            self.design_fingerprint,
            role="design_fingerprint",
            nullable=True,
        )

    def predict(
        self, features: Iterable[Iterable[float]] | DesignMatrix
    ) -> tuple[float, ...]:
        """Predict from feature columns in the original fitted order."""
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
        feature_matrix = _as_matrix(feature_values, name="features")
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

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the versioned fitted-result document."""
        return {
            "schema_version": SCHEMA_VERSION,
            "result_type": "ordinary_least_squares",
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "fitted_values": list(self.fitted_values),
            "residuals": list(self.residuals),
            "residual_degrees_of_freedom": self.residual_degrees_of_freedom,
            "residual_scale": self.residual_scale,
            "rank": self.rank,
            "n_observations": self.n_observations,
            "n_features": self.n_features,
            "includes_intercept": self.includes_intercept,
            "design_fingerprint": self.design_fingerprint,
        }

    def to_json(self) -> str:
        """Serialize the fitted result as canonical non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical result document."""
        return hashlib.sha256(self.to_json().encode()).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> OlsResult:
        """Reconstruct an OLS result from a strictly versioned document."""
        if not isinstance(document, dict):
            raise InputValidationError("OLS result document must be an object")
        raw = cast(dict[str, object], document)
        required = {
            "schema_version",
            "result_type",
            "coefficient_names",
            "coefficients",
            "covariance",
            "fitted_values",
            "residuals",
            "residual_degrees_of_freedom",
            "residual_scale",
            "rank",
            "n_observations",
            "n_features",
            "includes_intercept",
            "design_fingerprint",
        }
        if set(raw) != required:
            raise InputValidationError("OLS result document fields differ")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported OLS result schema version")
        if raw["result_type"] != "ordinary_least_squares":
            raise InputValidationError("unsupported fitted result type")
        array_names = (
            "coefficient_names",
            "coefficients",
            "covariance",
            "fitted_values",
            "residuals",
        )
        if any(not isinstance(raw[name], list) for name in array_names):
            raise InputValidationError("OLS result arrays are malformed")
        raw_names = cast(list[object], raw["coefficient_names"])
        raw_coefficients = cast(list[object], raw["coefficients"])
        raw_covariance = cast(list[object], raw["covariance"])
        raw_fitted = cast(list[object], raw["fitted_values"])
        raw_residuals = cast(list[object], raw["residuals"])
        if any(not isinstance(row, list) for row in raw_covariance):
            raise InputValidationError("covariance rows must be arrays")
        return cls(
            coefficient_names=tuple(cast(str, value) for value in raw_names),
            coefficients=tuple(cast(float, value) for value in raw_coefficients),
            covariance=tuple(
                tuple(cast(float, value) for value in cast(list[object], row))
                for row in raw_covariance
            ),
            fitted_values=tuple(cast(float, value) for value in raw_fitted),
            residuals=tuple(cast(float, value) for value in raw_residuals),
            residual_degrees_of_freedom=cast(int, raw["residual_degrees_of_freedom"]),
            residual_scale=cast(float, raw["residual_scale"]),
            rank=cast(int, raw["rank"]),
            n_observations=cast(int, raw["n_observations"]),
            n_features=cast(int, raw["n_features"]),
            includes_intercept=cast(bool, raw["includes_intercept"]),
            design_fingerprint=cast(str | None, raw["design_fingerprint"]),
        )

    @classmethod
    def from_json(cls, value: str) -> OlsResult:
        """Reconstruct an OLS result from strict bounded JSON."""
        return cls.from_dict(parse_json_object(value, role="OLS result"))


def fit_ols(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
) -> OlsResult:
    """Fit a full-rank ordinary least-squares model using QR factorization.

    This deliberately narrow first slice accepts an already constructed design
    matrix. Rank-deficient fits are rejected instead of silently dropping
    columns; an explicit alias policy will be added before formula-level OLS is
    declared complete.
    """
    if include_intercept is not None and not isinstance(
        cast(object, include_intercept), bool
    ):
        raise InputValidationError("include_intercept must be boolean")
    y = _as_vector(response, name="response")
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
    feature_matrix = _as_matrix(feature_values, name="features")
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
        design_fingerprint=design_fingerprint,
    )
