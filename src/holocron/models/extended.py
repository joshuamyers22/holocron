"""Bounded Phase 8 model-family replacements for selected rms exports."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Integral, Real
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
    UnsupportedFeatureError,
)
from holocron.models.survival import ParametricSurvivalResult

FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]
GlsMethod = Literal["ml", "reml"]
BuckleyJamesLink = Literal["identity", "log"]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

GLS_SCHEMA_VERSION = "holocron-gls-result/v1"
QUANTILE_SCHEMA_VERSION = "holocron-quantile-regression-result/v1"
BUCKLEY_JAMES_SCHEMA_VERSION = "holocron-buckley-james-result/v1"
PROPORTIONAL_HAZARDS_SCHEMA_VERSION = "holocron-proportional-hazards-result/v1"
MAX_OBSERVATIONS = 1_000_000
MAX_GLS_OBSERVATIONS = 5_000
MAX_PARAMETERS = 257


def _finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, Real)
        and math.isfinite(float(value))
    )


def _vector(values: Iterable[float], *, name: str) -> FloatVector:
    raw = tuple(values)
    if not raw or len(raw) > MAX_OBSERVATIONS:
        raise InputValidationError(f"{name} must have 1-{MAX_OBSERVATIONS} values")
    if not all(_finite(value) for value in raw):
        raise InputValidationError(f"{name} must contain only finite values")
    return np.asarray(tuple(float(value) for value in raw), dtype=np.float64)


def _matrix(
    values: Iterable[Iterable[float]], *, name: str, expected_rows: int | None = None
) -> FloatMatrix:
    rows = tuple(tuple(row) for row in values)
    if (
        not rows
        or len(rows) > MAX_OBSERVATIONS
        or (expected_rows is not None and len(rows) != expected_rows)
    ):
        raise InputValidationError(f"{name} must contain one row per observation")
    width = len(rows[0])
    if width < 1 or width >= MAX_PARAMETERS:
        raise InputValidationError(f"{name} has an unsupported column count")
    if any(len(row) != width for row in rows):
        raise InputValidationError(f"{name} rows must have equal lengths")
    if not all(_finite(value) for row in rows for value in row):
        raise InputValidationError(f"{name} must contain only finite values")
    return np.asarray(
        tuple(tuple(float(value) for value in row) for row in rows), dtype=np.float64
    )


def _names(width: int, values: Iterable[str] | None) -> tuple[str, ...]:
    result = (
        tuple(values)
        if values is not None
        else tuple(f"x{index + 1}" for index in range(width))
    )
    if (
        len(result) != width
        or any(
            not isinstance(name, str) or not name
            for name in cast(tuple[object, ...], cast(object, result))
        )
        or len(set(result)) != width
    ):
        raise InputValidationError(
            "feature_names must match the columns and be non-empty and unique"
        )
    return result


def _design(
    features: Iterable[Iterable[float]] | DesignMatrix,
    rows: int,
    *,
    feature_names: Iterable[str] | None,
    include_intercept: bool | None,
    design_fingerprint: str | None,
) -> tuple[FloatMatrix, tuple[str, ...], bool, str | None, int]:
    if include_intercept is not None and not isinstance(
        cast(object, include_intercept), bool
    ):
        raise InputValidationError("include_intercept must be boolean")
    if isinstance(features, DesignMatrix):
        if feature_names is not None and tuple(feature_names) != features.column_names:
            raise InputValidationError(
                "feature_names must match DesignMatrix column identity"
            )
        if (
            include_intercept is not None
            and include_intercept != features.include_intercept
        ):
            raise InputValidationError(
                "include_intercept must match the DesignMatrix specification"
            )
        if (
            design_fingerprint is not None
            and design_fingerprint != features.specification_fingerprint
        ):
            raise InputValidationError(
                "design_fingerprint must match the DesignMatrix specification"
            )
        raw_features = features.rows
        feature_names = features.column_names
        include_intercept = features.include_intercept
        design_fingerprint = features.specification_fingerprint
    else:
        raw_features = features
        include_intercept = True if include_intercept is None else include_intercept
    matrix = _matrix(raw_features, name="features", expected_rows=rows)
    names = _names(matrix.shape[1], feature_names)
    design = (
        np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (np.ones(rows, dtype=np.float64), matrix)
        )
        if include_intercept
        else matrix
    )
    if rows <= design.shape[1]:
        raise InputValidationError(
            "model fitting requires positive residual degrees of freedom"
        )
    if int(np.linalg.matrix_rank(design)) != design.shape[1]:
        raise RankDeficiencyError("design matrix must have full column rank")
    validate_sha256(design_fingerprint, role="design_fingerprint", nullable=True)
    coefficient_names = ("Intercept", *names) if include_intercept else names
    return (
        design,
        coefficient_names,
        include_intercept,
        design_fingerprint,
        matrix.shape[1],
    )


def _prediction_design(
    features: Iterable[Iterable[float]], n_features: int, includes_intercept: bool
) -> FloatMatrix:
    matrix = _matrix(features, name="prediction features")
    if matrix.shape[1] != n_features:
        raise InputValidationError(
            f"prediction features have {matrix.shape[1]} columns; expected {n_features}"
        )
    return (
        np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (np.ones(matrix.shape[0], dtype=np.float64), matrix)
        )
        if includes_intercept
        else matrix
    )


def _rows(value: FloatMatrix) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(item) for item in row) for row in value)


def _values(value: FloatVector) -> tuple[float, ...]:
    return tuple(float(item) for item in value)


def _validate_common_result(
    *,
    coefficient_names: tuple[str, ...],
    coefficients: tuple[float, ...],
    covariance: tuple[tuple[float, ...], ...],
    fitted_values: tuple[float, ...],
    residuals: tuple[float, ...],
    n_observations: int,
    n_features: int,
    includes_intercept: bool,
    design_fingerprint: str | None,
) -> None:
    if not isinstance(cast(object, includes_intercept), bool):
        raise InputValidationError("includes_intercept must be boolean")
    if (
        isinstance(cast(object, n_observations), bool)
        or not isinstance(cast(object, n_observations), int)
        or not 1 <= n_observations <= MAX_OBSERVATIONS
        or isinstance(cast(object, n_features), bool)
        or not isinstance(cast(object, n_features), int)
        or not 1 <= n_features < MAX_PARAMETERS
    ):
        raise InputValidationError("result dimensions are invalid")
    parameter_count = n_features + int(includes_intercept)
    if n_observations <= parameter_count:
        raise InputValidationError(
            "result requires positive residual degrees of freedom"
        )
    if (
        not isinstance(cast(object, coefficient_names), tuple)
        or len(coefficient_names) != parameter_count
        or any(
            not isinstance(name, str) or not name
            for name in cast(tuple[object, ...], cast(object, coefficient_names))
        )
        or len(set(coefficient_names)) != parameter_count
    ):
        raise InputValidationError("coefficient names are inconsistent")
    if (
        not isinstance(cast(object, coefficients), tuple)
        or len(coefficients) != parameter_count
    ):
        raise InputValidationError("coefficients are inconsistent")
    if (
        not isinstance(cast(object, covariance), tuple)
        or len(covariance) != parameter_count
        or any(
            not isinstance(cast(object, row), tuple) or len(row) != parameter_count
            for row in covariance
        )
    ):
        raise InputValidationError("covariance must be square by parameter")
    if (
        not isinstance(cast(object, fitted_values), tuple)
        or not isinstance(cast(object, residuals), tuple)
        or len(fitted_values) != n_observations
        or len(residuals) != n_observations
    ):
        raise InputValidationError("fitted values and residuals are inconsistent")
    numeric = (
        *coefficients,
        *(item for row in covariance for item in row),
        *fitted_values,
        *residuals,
    )
    if not all(_finite(value) for value in numeric):
        raise InputValidationError("result values must be finite")
    for row_index, row in enumerate(covariance):
        for column_index in range(row_index):
            if not math.isclose(
                row[column_index],
                covariance[column_index][row_index],
                rel_tol=1e-10,
                abs_tol=1e-12,
            ):
                raise InputValidationError("covariance must be symmetric")
    validate_sha256(design_fingerprint, role="design_fingerprint", nullable=True)


def _fingerprint(document: dict[str, JsonValue]) -> str:
    return hashlib.sha256(canonical_json(document).encode()).hexdigest()


def _object(document: object, *, version: str, fields: set[str]) -> dict[str, object]:
    if not isinstance(document, dict):
        raise InputValidationError("result document must be an object")
    raw = cast(dict[str, object], document)
    if set(raw) != fields:
        raise InputValidationError("result document fields differ")
    if raw["schema_version"] != version:
        raise InputValidationError("unsupported result schema version")
    return raw


def _read_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InputValidationError("coefficient_names must be an array")
    return tuple(cast(str, item) for item in cast(list[object], value))


def _read_float(value: object, *, role: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InputValidationError(f"{role} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise InputValidationError(f"{role} must be finite")
    return result


def _read_vector(value: object) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise InputValidationError("numeric result field must be an array")
    return tuple(
        _read_float(item, role="numeric result value")
        for item in cast(list[object], value)
    )


def _read_matrix(value: object) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, list) or any(
        not isinstance(row, list) for row in cast(list[object], value)
    ):
        raise InputValidationError("matrix result field must contain arrays")
    return tuple(
        tuple(
            _read_float(item, role="matrix result value")
            for item in cast(list[object], row)
        )
        for row in cast(list[object], value)
    )


@dataclass(frozen=True, slots=True)
class GeneralizedLeastSquaresResult:
    """Immutable GLS fit for a caller-supplied positive-definite covariance."""

    method: GlsMethod
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    fitted_values: tuple[float, ...]
    residuals: tuple[float, ...]
    residual_scale: float
    log_likelihood: float
    n_observations: int
    n_features: int
    includes_intercept: bool
    design_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.method not in {"ml", "reml"}:
            raise InputValidationError("GLS method must be 'ml' or 'reml'")
        _validate_common_result(
            coefficient_names=self.coefficient_names,
            coefficients=self.coefficients,
            covariance=self.covariance,
            fitted_values=self.fitted_values,
            residuals=self.residuals,
            n_observations=self.n_observations,
            n_features=self.n_features,
            includes_intercept=self.includes_intercept,
            design_fingerprint=self.design_fingerprint,
        )
        if not _finite(self.residual_scale) or self.residual_scale < 0.0:
            raise InputValidationError("residual_scale must be finite and nonnegative")
        if not _finite(self.log_likelihood):
            raise InputValidationError("log_likelihood must be finite")

    def predict(self, features: Iterable[Iterable[float]]) -> tuple[float, ...]:
        """Predict the conditional mean for explicit feature rows."""

        design = _prediction_design(features, self.n_features, self.includes_intercept)
        return _values(design @ np.asarray(self.coefficients, dtype=np.float64))

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned GLS document."""

        return {
            "schema_version": GLS_SCHEMA_VERSION,
            "method": self.method,
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "fitted_values": list(self.fitted_values),
            "residuals": list(self.residuals),
            "residual_scale": self.residual_scale,
            "log_likelihood": self.log_likelihood,
            "n_observations": self.n_observations,
            "n_features": self.n_features,
            "includes_intercept": self.includes_intercept,
            "design_fingerprint": self.design_fingerprint,
        }

    def to_json(self) -> str:
        """Serialize the GLS result as canonical non-executable JSON."""

        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical document."""

        return _fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: object) -> GeneralizedLeastSquaresResult:
        """Reconstruct a GLS result from an exact-version document."""

        fields = {
            "schema_version",
            "method",
            "coefficient_names",
            "coefficients",
            "covariance",
            "fitted_values",
            "residuals",
            "residual_scale",
            "log_likelihood",
            "n_observations",
            "n_features",
            "includes_intercept",
            "design_fingerprint",
        }
        raw = _object(document, version=GLS_SCHEMA_VERSION, fields=fields)
        return cls(
            cast(GlsMethod, raw["method"]),
            _read_names(raw["coefficient_names"]),
            _read_vector(raw["coefficients"]),
            _read_matrix(raw["covariance"]),
            _read_vector(raw["fitted_values"]),
            _read_vector(raw["residuals"]),
            _read_float(raw["residual_scale"], role="residual_scale"),
            _read_float(raw["log_likelihood"], role="log_likelihood"),
            cast(int, raw["n_observations"]),
            cast(int, raw["n_features"]),
            cast(bool, raw["includes_intercept"]),
            cast(str | None, raw["design_fingerprint"]),
        )

    @classmethod
    def from_json(cls, value: str) -> GeneralizedLeastSquaresResult:
        """Reconstruct a GLS result from strict bounded JSON."""

        return cls.from_dict(parse_json_object(value, role="GLS result"))


@dataclass(frozen=True, slots=True)
class QuantileRegressionResult:
    """Immutable single-quantile linear regression fit."""

    quantile: float
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    fitted_values: tuple[float, ...]
    residuals: tuple[float, ...]
    objective: float
    iterations: int
    n_observations: int
    n_features: int
    includes_intercept: bool
    design_fingerprint: str | None = None

    def __post_init__(self) -> None:
        _validate_common_result(
            coefficient_names=self.coefficient_names,
            coefficients=self.coefficients,
            covariance=self.covariance,
            fitted_values=self.fitted_values,
            residuals=self.residuals,
            n_observations=self.n_observations,
            n_features=self.n_features,
            includes_intercept=self.includes_intercept,
            design_fingerprint=self.design_fingerprint,
        )
        if not _finite(self.quantile) or not 0.0 < self.quantile < 1.0:
            raise InputValidationError("quantile must be strictly between zero and one")
        if not _finite(self.objective) or self.objective < 0.0:
            raise InputValidationError("objective must be finite and nonnegative")
        if (
            isinstance(cast(object, self.iterations), bool)
            or not isinstance(cast(object, self.iterations), int)
            or not 1 <= self.iterations <= 1_000_000
        ):
            raise InputValidationError("iterations must be a positive integer")

    def predict(self, features: Iterable[Iterable[float]]) -> tuple[float, ...]:
        """Predict the fitted conditional quantile for explicit feature rows."""

        design = _prediction_design(features, self.n_features, self.includes_intercept)
        return _values(design @ np.asarray(self.coefficients, dtype=np.float64))

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned quantile-regression document."""

        return {
            "schema_version": QUANTILE_SCHEMA_VERSION,
            "quantile": self.quantile,
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "fitted_values": list(self.fitted_values),
            "residuals": list(self.residuals),
            "objective": self.objective,
            "iterations": self.iterations,
            "n_observations": self.n_observations,
            "n_features": self.n_features,
            "includes_intercept": self.includes_intercept,
            "design_fingerprint": self.design_fingerprint,
        }

    def to_json(self) -> str:
        """Serialize the quantile result as canonical non-executable JSON."""

        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical document."""

        return _fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: object) -> QuantileRegressionResult:
        """Reconstruct a quantile result from an exact-version document."""

        fields = {
            "schema_version",
            "quantile",
            "coefficient_names",
            "coefficients",
            "covariance",
            "fitted_values",
            "residuals",
            "objective",
            "iterations",
            "n_observations",
            "n_features",
            "includes_intercept",
            "design_fingerprint",
        }
        raw = _object(document, version=QUANTILE_SCHEMA_VERSION, fields=fields)
        return cls(
            _read_float(raw["quantile"], role="quantile"),
            _read_names(raw["coefficient_names"]),
            _read_vector(raw["coefficients"]),
            _read_matrix(raw["covariance"]),
            _read_vector(raw["fitted_values"]),
            _read_vector(raw["residuals"]),
            _read_float(raw["objective"], role="objective"),
            cast(int, raw["iterations"]),
            cast(int, raw["n_observations"]),
            cast(int, raw["n_features"]),
            cast(bool, raw["includes_intercept"]),
            cast(str | None, raw["design_fingerprint"]),
        )

    @classmethod
    def from_json(cls, value: str) -> QuantileRegressionResult:
        """Reconstruct a quantile result from strict bounded JSON."""

        return cls.from_dict(parse_json_object(value, role="quantile result"))


@dataclass(frozen=True, slots=True)
class BuckleyJamesResult:
    """Immutable right-censored Buckley–James accelerated-time fit."""

    link: BuckleyJamesLink
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    fitted_values: tuple[float, ...]
    residuals: tuple[float, ...]
    imputed_response: tuple[float, ...]
    residual_scale: float
    iterations: int
    event_count: int
    n_observations: int
    n_features: int
    includes_intercept: bool
    design_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if self.link not in {"identity", "log"}:
            raise InputValidationError("Buckley-James link must be identity or log")
        _validate_common_result(
            coefficient_names=self.coefficient_names,
            coefficients=self.coefficients,
            covariance=self.covariance,
            fitted_values=self.fitted_values,
            residuals=self.residuals,
            n_observations=self.n_observations,
            n_features=self.n_features,
            includes_intercept=self.includes_intercept,
            design_fingerprint=self.design_fingerprint,
        )
        if (
            not isinstance(cast(object, self.imputed_response), tuple)
            or len(self.imputed_response) != self.n_observations
            or not all(_finite(value) for value in self.imputed_response)
        ):
            raise InputValidationError("imputed_response is inconsistent")
        parameter_count = self.n_features + int(self.includes_intercept)
        if (
            isinstance(cast(object, self.event_count), bool)
            or not isinstance(cast(object, self.event_count), int)
            or not parameter_count < self.event_count < self.n_observations
        ):
            raise InputValidationError("event_count must exceed the parameter count")
        if (
            isinstance(cast(object, self.iterations), bool)
            or not isinstance(cast(object, self.iterations), int)
            or not 1 <= self.iterations <= 10_000
            or not _finite(self.residual_scale)
            or self.residual_scale < 0.0
        ):
            raise InputValidationError("Buckley-James fit diagnostics are invalid")

    def predict(
        self,
        features: Iterable[Iterable[float]],
        *,
        scale: Literal["link", "response"] = "response",
    ) -> tuple[float, ...]:
        """Predict on the transformed-time or original response scale."""

        if scale not in {"link", "response"}:
            raise InputValidationError("prediction scale must be 'link' or 'response'")
        design = _prediction_design(features, self.n_features, self.includes_intercept)
        values = design @ np.asarray(self.coefficients, dtype=np.float64)
        if scale == "response" and self.link == "log":
            values = np.exp(values)
            if not np.all(np.isfinite(values)):  # pyright: ignore[reportUnknownMemberType]
                raise NumericalError("Buckley-James response prediction overflowed")
        return _values(values)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned Buckley–James document."""

        return {
            "schema_version": BUCKLEY_JAMES_SCHEMA_VERSION,
            "link": self.link,
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "covariance": [list(row) for row in self.covariance],
            "fitted_values": list(self.fitted_values),
            "residuals": list(self.residuals),
            "imputed_response": list(self.imputed_response),
            "residual_scale": self.residual_scale,
            "iterations": self.iterations,
            "event_count": self.event_count,
            "n_observations": self.n_observations,
            "n_features": self.n_features,
            "includes_intercept": self.includes_intercept,
            "design_fingerprint": self.design_fingerprint,
        }

    def to_json(self) -> str:
        """Serialize the Buckley–James result as canonical non-executable JSON."""

        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical document."""

        return _fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: object) -> BuckleyJamesResult:
        """Reconstruct a Buckley–James result from an exact-version document."""

        fields = {
            "schema_version",
            "link",
            "coefficient_names",
            "coefficients",
            "covariance",
            "fitted_values",
            "residuals",
            "imputed_response",
            "residual_scale",
            "iterations",
            "event_count",
            "n_observations",
            "n_features",
            "includes_intercept",
            "design_fingerprint",
        }
        raw = _object(document, version=BUCKLEY_JAMES_SCHEMA_VERSION, fields=fields)
        return cls(
            cast(BuckleyJamesLink, raw["link"]),
            _read_names(raw["coefficient_names"]),
            _read_vector(raw["coefficients"]),
            _read_matrix(raw["covariance"]),
            _read_vector(raw["fitted_values"]),
            _read_vector(raw["residuals"]),
            _read_vector(raw["imputed_response"]),
            _read_float(raw["residual_scale"], role="residual_scale"),
            cast(int, raw["iterations"]),
            cast(int, raw["event_count"]),
            cast(int, raw["n_observations"]),
            cast(int, raw["n_features"]),
            cast(bool, raw["includes_intercept"]),
            cast(str | None, raw["design_fingerprint"]),
        )

    @classmethod
    def from_json(cls, value: str) -> BuckleyJamesResult:
        """Reconstruct a Buckley–James result from strict bounded JSON."""

        return cls.from_dict(parse_json_object(value, role="Buckley-James result"))


@dataclass(frozen=True, slots=True)
class ProportionalHazardsParametricResult:
    """Weibull/exponential AFT fit represented on proportional-hazards scale."""

    distribution: Literal["weibull", "exponential"]
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    conditional_covariance: tuple[tuple[float, ...], ...]
    shape: float
    source_fingerprint: str
    n_observations: int

    def __post_init__(self) -> None:
        tuple_fields = (
            self.coefficient_names,
            self.coefficients,
            self.conditional_covariance,
        )
        if any(not isinstance(cast(object, value), tuple) for value in tuple_fields):
            raise InputValidationError("proportional-hazards arrays must be tuples")
        parameter_count = len(self.coefficient_names)
        if (
            self.distribution not in {"weibull", "exponential"}
            or parameter_count < 2
            or parameter_count > MAX_PARAMETERS
            or len(self.coefficients) != parameter_count
            or len(set(self.coefficient_names)) != parameter_count
            or any(
                not isinstance(name, str) or not name
                for name in cast(
                    tuple[object, ...], cast(object, self.coefficient_names)
                )
            )
            or len(self.conditional_covariance) != parameter_count
            or any(
                not isinstance(cast(object, row), tuple) or len(row) != parameter_count
                for row in self.conditional_covariance
            )
        ):
            raise InputValidationError("proportional-hazards result is inconsistent")
        numeric = (
            *self.coefficients,
            *(value for row in self.conditional_covariance for value in row),
            self.shape,
        )
        if not all(_finite(value) for value in numeric) or self.shape <= 0.0:
            raise InputValidationError("proportional-hazards values must be finite")
        for row_index, row in enumerate(self.conditional_covariance):
            for column_index in range(row_index):
                if not math.isclose(
                    row[column_index],
                    self.conditional_covariance[column_index][row_index],
                    rel_tol=1e-10,
                    abs_tol=1e-12,
                ):
                    raise InputValidationError(
                        "conditional_covariance must be symmetric"
                    )
        if (
            isinstance(cast(object, self.n_observations), bool)
            or not isinstance(cast(object, self.n_observations), int)
            or not 1 <= self.n_observations <= MAX_OBSERVATIONS
        ):
            raise InputValidationError("n_observations must be positive")
        validate_sha256(self.source_fingerprint, role="source_fingerprint")

    def predict_log_relative_hazard(
        self, features: Iterable[Iterable[float]]
    ) -> tuple[float, ...]:
        """Predict the slope-only log relative hazard."""

        matrix = _matrix(features, name="prediction features")
        slopes = np.asarray(self.coefficients[1:], dtype=np.float64)
        if matrix.shape[1] != slopes.size:
            raise InputValidationError("prediction features have the wrong shape")
        return _values(matrix @ slopes)

    def predict_survival(
        self, features: Iterable[Iterable[float]], times: Iterable[float]
    ) -> tuple[tuple[float, ...], ...]:
        """Predict survival from the proportional-hazards parameterization."""

        matrix = _matrix(features, name="prediction features")
        if matrix.shape[1] != len(self.coefficients) - 1:
            raise InputValidationError("prediction features have the wrong shape")
        requested = _vector(times, name="times")
        if np.any(requested <= 0.0):  # pyright: ignore[reportUnknownMemberType]
            raise InputValidationError("times must be strictly positive")
        predictors = self.coefficients[0] + matrix @ np.asarray(
            self.coefficients[1:], dtype=np.float64
        )
        log_cumulative = predictors[:, None] + self.shape * np.log(requested)[None, :]
        cumulative = np.exp(
            np.clip(  # pyright: ignore[reportUnknownMemberType]
                log_cumulative, -745.0, 700.0
            )
        )
        return _rows(np.exp(-cumulative))

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned proportional-hazards document."""

        return {
            "schema_version": PROPORTIONAL_HAZARDS_SCHEMA_VERSION,
            "distribution": self.distribution,
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "conditional_covariance": [
                list(row) for row in self.conditional_covariance
            ],
            "shape": self.shape,
            "source_fingerprint": self.source_fingerprint,
            "n_observations": self.n_observations,
        }

    def to_json(self) -> str:
        """Serialize the PH conversion as canonical non-executable JSON."""

        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical document."""

        return _fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: object) -> ProportionalHazardsParametricResult:
        """Reconstruct a PH conversion from an exact-version document."""

        fields = {
            "schema_version",
            "distribution",
            "coefficient_names",
            "coefficients",
            "conditional_covariance",
            "shape",
            "source_fingerprint",
            "n_observations",
        }
        raw = _object(
            document, version=PROPORTIONAL_HAZARDS_SCHEMA_VERSION, fields=fields
        )
        return cls(
            cast(Literal["weibull", "exponential"], raw["distribution"]),
            _read_names(raw["coefficient_names"]),
            _read_vector(raw["coefficients"]),
            _read_matrix(raw["conditional_covariance"]),
            _read_float(raw["shape"], role="shape"),
            cast(str, raw["source_fingerprint"]),
            cast(int, raw["n_observations"]),
        )

    @classmethod
    def from_json(cls, value: str) -> ProportionalHazardsParametricResult:
        """Reconstruct a PH conversion from strict bounded JSON."""

        return cls.from_dict(parse_json_object(value, role="PH parametric result"))


def fit_gls(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    observation_covariance: Iterable[Iterable[float]] | None = None,
    method: GlsMethod = "reml",
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
) -> GeneralizedLeastSquaresResult:
    """Fit GLS for a fixed caller-supplied relative observation covariance.

    The covariance must be symmetric positive definite and is treated as known
    up to one residual scale. Correlation/variance-structure estimation,
    grouping formulas, and bootstrap fitting are intentionally outside this
    bounded replacement for ``rms::Gls``.
    """

    if method not in {"ml", "reml"}:
        raise InputValidationError("GLS method must be 'ml' or 'reml'")
    y = _vector(response, name="response")
    if y.size > MAX_GLS_OBSERVATIONS:
        raise InputValidationError(
            f"GLS is bounded to {MAX_GLS_OBSERVATIONS} observations"
        )
    design, names, intercept, fingerprint, feature_count = _design(
        features,
        y.size,
        feature_names=feature_names,
        include_intercept=include_intercept,
        design_fingerprint=design_fingerprint,
    )
    if observation_covariance is None:
        relative_covariance = np.eye(y.size, dtype=np.float64)
    else:
        raw = tuple(tuple(row) for row in observation_covariance)
        if (
            len(raw) != y.size
            or any(len(row) != y.size for row in raw)
            or not all(_finite(value) for row in raw for value in row)
        ):
            raise InputValidationError(
                "observation_covariance must be finite and square by observation"
            )
        relative_covariance = np.asarray(
            tuple(tuple(float(value) for value in row) for row in raw),
            dtype=np.float64,
        )
        if not np.allclose(  # pyright: ignore[reportUnknownMemberType]
            relative_covariance, relative_covariance.T, rtol=1e-12, atol=1e-14
        ):
            raise InputValidationError("observation_covariance must be symmetric")
    try:
        lower = np.linalg.cholesky(relative_covariance)
    except np.linalg.LinAlgError as error:
        raise InputValidationError(
            "observation_covariance must be positive definite"
        ) from error
    whitened_design = np.linalg.solve(lower, design)
    whitened_response = np.linalg.solve(lower, y)
    q_matrix, r_matrix = np.linalg.qr(whitened_design, mode="reduced")
    coefficients = np.linalg.solve(r_matrix, q_matrix.T @ whitened_response)
    fitted = design @ coefficients
    residuals = y - fitted
    whitened_residuals = np.linalg.solve(lower, residuals)
    quadratic = float(whitened_residuals @ whitened_residuals)
    parameters = design.shape[1]
    denominator = y.size - parameters if method == "reml" else y.size
    variance = quadratic / denominator
    if not math.isfinite(variance) or variance <= 0.0:
        raise NumericalError("GLS residual variance is not strictly positive")
    inverse_r = np.linalg.solve(r_matrix, np.eye(parameters, dtype=np.float64))
    covariance = variance * (inverse_r @ inverse_r.T)
    logdet_relative = 2.0 * float(
        np.sum(np.log(np.diag(lower)))  # pyright: ignore[reportUnknownMemberType]
    )
    if method == "ml":
        log_likelihood = -0.5 * (
            y.size * (math.log(2.0 * math.pi * variance) + 1.0) + logdet_relative
        )
    else:
        gram_sign, gram_logdet = np.linalg.slogdet(whitened_design.T @ whitened_design)
        if gram_sign <= 0.0:
            raise NumericalError("GLS information matrix is not positive definite")
        log_likelihood = -0.5 * (
            denominator * (math.log(2.0 * math.pi * variance) + 1.0)
            + logdet_relative
            + float(gram_logdet)
        )
    return GeneralizedLeastSquaresResult(
        method,
        names,
        _values(coefficients),
        _rows(covariance),
        _values(fitted),
        _values(residuals),
        math.sqrt(variance),
        log_likelihood,
        int(y.size),
        feature_count,
        intercept,
        fingerprint,
    )


def _prox_check(
    value: FloatVector, weights: FloatVector, quantile: float, penalty: float
) -> FloatVector:
    upper = weights * quantile / penalty
    lower = weights * (1.0 - quantile) / penalty
    return np.where(  # pyright: ignore[reportUnknownMemberType]
        value > upper,
        value - upper,
        np.where(  # pyright: ignore[reportUnknownMemberType]
            value < -lower, value + lower, 0.0
        ),
    )


def fit_quantile_regression(
    response: Iterable[float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    quantile: float = 0.5,
    weights: Iterable[float] | None = None,
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 50_000,
    tolerance: float = 1e-7,
) -> QuantileRegressionResult:
    """Fit one weighted linear quantile by deterministic convex ADMM.

    This replacement does not expose the algorithm choices, sparsity methods,
    or inference modes of ``rms::Rq``/``quantreg``. Its covariance is a bounded
    kernel-density sandwich approximation and is labelled experimental.
    """

    if not _finite(quantile) or not 0.0 < float(quantile) < 1.0:
        raise InputValidationError("quantile must be strictly between zero and one")
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, Integral)
        or not 1 <= max_iterations <= 1_000_000
        or not _finite(tolerance)
        or not 0.0 < float(tolerance) < 1.0
    ):
        raise InputValidationError("invalid quantile-regression controls")
    y = _vector(response, name="response")
    design, names, intercept, fingerprint, feature_count = _design(
        features,
        y.size,
        feature_names=feature_names,
        include_intercept=include_intercept,
        design_fingerprint=design_fingerprint,
    )
    if weights is None:
        weight = np.ones(y.size, dtype=np.float64)
    else:
        weight = _vector(weights, name="weights")
        if weight.size != y.size or np.any(weight <= 0.0):  # pyright: ignore[reportUnknownMemberType]
            raise InputValidationError("weights must be positive and match response")
    gram = design.T @ design
    coefficients = np.linalg.solve(gram, design.T @ y)
    residual_variable = y - design @ coefficients
    dual = np.zeros(y.size, dtype=np.float64)
    penalty = 1.0 / max(float(np.std(y)), 1e-6)
    converged = False
    iterations = 0
    for iteration in range(1, int(max_iterations) + 1):
        coefficients = np.linalg.solve(gram, design.T @ (y - residual_variable - dual))
        previous = residual_variable.copy()
        prox_input = y - design @ coefficients - dual
        residual_variable = _prox_check(prox_input, weight, float(quantile), penalty)
        primal = design @ coefficients + residual_variable - y
        dual += primal
        primal_norm = float(
            np.linalg.norm(primal)  # pyright: ignore[reportUnknownMemberType]
        )
        dual_norm = float(
            np.linalg.norm(  # pyright: ignore[reportUnknownMemberType]
                penalty * design.T @ (residual_variable - previous)
            )
        )
        primal_limit = math.sqrt(y.size) * float(tolerance) + float(tolerance) * max(
            float(
                np.linalg.norm(  # pyright: ignore[reportUnknownMemberType]
                    design @ coefficients
                )
            ),
            float(
                np.linalg.norm(  # pyright: ignore[reportUnknownMemberType]
                    residual_variable
                )
            ),
            float(np.linalg.norm(y)),  # pyright: ignore[reportUnknownMemberType]
        )
        dual_limit = math.sqrt(design.shape[1]) * float(tolerance) + float(
            tolerance
        ) * float(
            np.linalg.norm(  # pyright: ignore[reportUnknownMemberType]
                penalty * design.T @ dual
            )
        )
        iterations = iteration
        if primal_norm <= primal_limit and dual_norm <= dual_limit:
            converged = True
            break
        if iteration % 25 == 0:
            if primal_norm > 10.0 * dual_norm:
                penalty *= 2.0
                dual /= 2.0
            elif dual_norm > 10.0 * primal_norm:
                penalty /= 2.0
                dual *= 2.0
    if not converged:
        raise ConvergenceError(
            "quantile regression did not meet the declared ADMM tolerance"
        )
    fitted = design @ coefficients
    residuals = y - fitted
    q = float(quantile)
    objective = float(
        np.sum(
            weight
            * np.where(  # pyright: ignore[reportUnknownMemberType]
                residuals >= 0.0, q * residuals, (q - 1.0) * residuals
            )
        )
    )
    standard_deviation = float(np.std(residuals, ddof=1))
    quartiles = np.quantile(  # pyright: ignore[reportUnknownMemberType]
        residuals, (0.25, 0.75)
    )
    robust_scale = float((quartiles[1] - quartiles[0]) / 1.349)
    scale_candidates = tuple(
        value for value in (standard_deviation, robust_scale) if value > 1e-12
    )
    scale = min(scale_candidates) if scale_candidates else max(standard_deviation, 1e-6)
    bandwidth = max(0.9 * scale * y.size ** (-0.2), 1e-8)
    density_terms = weight * cast(
        FloatVector,
        np.exp(-0.5 * (residuals / bandwidth) ** 2),
    )
    density_zero = float(np.sum(density_terms)) / (
        float(np.sum(weight)) * math.sqrt(2.0 * math.pi) * bandwidth
    )
    if not math.isfinite(density_zero) or density_zero <= 1e-12:
        raise NumericalError("residual density at zero is numerically undefined")
    bread = design.T @ (weight[:, None] * design)
    meat = design.T @ ((weight * weight)[:, None] * design)
    inverse_bread = np.linalg.inv(bread)
    covariance = (
        q
        * (1.0 - q)
        / (density_zero * density_zero)
        * (inverse_bread @ meat @ inverse_bread)
    )
    return QuantileRegressionResult(
        q,
        names,
        _values(coefficients),
        _rows(covariance),
        _values(fitted),
        _values(residuals),
        objective,
        iterations,
        int(y.size),
        feature_count,
        intercept,
        fingerprint,
    )


def _conditional_residual_means(
    residuals: FloatVector, events: npt.NDArray[np.int64]
) -> FloatVector:
    effective_events = events.copy()
    maximum = float(np.max(residuals))
    effective_events[residuals == maximum] = 1
    order = np.lexsort(  # pyright: ignore[reportUnknownMemberType]
        (-effective_events, residuals)
    )
    ordered = residuals[order]
    ordered_events = effective_events[order]
    event_times: list[float] = []
    masses: list[float] = []
    survival = 1.0
    index = 0
    while index < ordered.size:
        value = float(ordered[index])
        endpoint = index
        while endpoint < ordered.size and float(ordered[endpoint]) == value:
            endpoint += 1
        at_risk = ordered.size - index
        failures = int(np.sum(ordered_events[index:endpoint]))
        if failures:
            mass = survival * failures / at_risk
            event_times.append(value)
            masses.append(mass)
            survival *= 1.0 - failures / at_risk
        index = endpoint
    time_array = np.asarray(event_times, dtype=np.float64)
    mass_array = np.asarray(masses, dtype=np.float64)
    result = residuals.copy()
    for row, (value, event) in enumerate(zip(residuals, events, strict=True)):
        if event:
            continue
        mask = time_array > value
        probability = float(np.sum(mass_array[mask]))
        if probability <= 1e-14:
            raise ConvergenceError(
                "Buckley-James residual distribution has no estimable censoring tail"
            )
        result[row] = float(np.sum(time_array[mask] * mass_array[mask]) / probability)
    return result


def fit_buckley_james(
    times: Iterable[float],
    events: Iterable[int | bool],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    link: BuckleyJamesLink = "log",
    feature_names: Iterable[str] | None = None,
    include_intercept: bool | None = None,
    design_fingerprint: str | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-7,
) -> BuckleyJamesResult:
    """Fit a right-censored Buckley–James accelerated-time model.

    Only identity and log time links are supported. The implementation uses
    Kaplan–Meier residual-tail imputation and rejects nonconvergence rather than
    returning cycle-averaged coefficients. The reported covariance is an
    event-only working OLS covariance, not bootstrap or rms inference parity.
    """

    if link not in {"identity", "log"}:
        raise UnsupportedFeatureError(
            "Buckley-James supports only identity and log links"
        )
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, Integral)
        or not 1 <= max_iterations <= 10_000
        or not _finite(tolerance)
        or not 0.0 < float(tolerance) < 1.0
    ):
        raise InputValidationError("invalid Buckley-James controls")
    observed_times = _vector(times, name="times")
    if np.any(observed_times <= 0.0):  # pyright: ignore[reportUnknownMemberType]
        raise InputValidationError("times must be strictly positive")
    raw_events = tuple(events)
    if len(raw_events) != observed_times.size or any(
        not isinstance(value, (bool, Integral)) or int(value) not in {0, 1}
        for value in raw_events
    ):
        raise InputValidationError("events must contain one 0/1 value per time")
    event_array = np.asarray(tuple(int(value) for value in raw_events), dtype=np.int64)
    if not np.any(event_array == 0) or not np.any(event_array == 1):  # pyright: ignore[reportUnknownMemberType]
        raise InputValidationError(
            "Buckley-James requires observed and right-censored responses"
        )
    transformed = np.log(observed_times) if link == "log" else observed_times.copy()
    design, names, intercept, fingerprint, feature_count = _design(
        features,
        observed_times.size,
        feature_names=feature_names,
        include_intercept=include_intercept,
        design_fingerprint=design_fingerprint,
    )
    event_count = int(np.sum(event_array))
    if event_count <= design.shape[1]:
        raise InputValidationError(
            "Buckley-James requires more events than fitted parameters"
        )
    imputed = transformed.copy()
    coefficients = np.linalg.solve(design.T @ design, design.T @ imputed)
    converged = False
    iterations = 0
    for iteration in range(1, int(max_iterations) + 1):
        fitted = design @ coefficients
        raw_residuals = transformed - fitted
        conditional = _conditional_residual_means(raw_residuals, event_array)
        updated_response = transformed.copy()
        censored = event_array == 0
        updated_response[censored] = fitted[censored] + conditional[censored]
        updated = np.linalg.solve(design.T @ design, design.T @ updated_response)
        iterations = iteration
        if float(np.max(np.abs(updated - coefficients))) <= float(tolerance) * (
            1.0 + float(np.max(np.abs(coefficients)))
        ):
            coefficients = updated
            imputed = updated_response
            converged = True
            break
        coefficients = updated
        imputed = updated_response
    if not converged:
        raise ConvergenceError("Buckley-James fit did not converge")
    fitted = design @ coefficients
    residuals = transformed - fitted
    event_design = design[event_array == 1]
    event_residuals = residuals[event_array == 1]
    degrees = event_count - design.shape[1]
    variance = float(event_residuals @ event_residuals) / degrees
    try:
        covariance = variance * np.linalg.inv(event_design.T @ event_design)
    except np.linalg.LinAlgError as error:
        raise RankDeficiencyError(
            "Buckley-James event-only covariance design is singular"
        ) from error
    return BuckleyJamesResult(
        link,
        names,
        _values(coefficients),
        _rows(covariance),
        _values(fitted),
        _values(residuals),
        _values(imputed),
        math.sqrt(variance),
        iterations,
        event_count,
        int(observed_times.size),
        feature_count,
        intercept,
        fingerprint,
    )


def to_proportional_hazards(
    result: ParametricSurvivalResult,
) -> ProportionalHazardsParametricResult:
    """Convert a one-scale Weibull/exponential AFT fit to PH parameters.

    The covariance transformation conditions on the fitted scale because the
    current parametric result intentionally retains only coefficient covariance.
    Scale-stratified Weibull fits therefore fail closed.
    """

    if not isinstance(cast(object, result), ParametricSurvivalResult):
        raise InputValidationError("result must be a ParametricSurvivalResult")
    if len(result.scales) != 1:
        raise UnsupportedFeatureError(
            "proportional-hazards conversion requires one common AFT scale"
        )
    scale = result.scales[0]
    coefficients = -np.asarray(result.coefficients, dtype=np.float64) / scale
    covariance = np.asarray(result.covariance, dtype=np.float64) / (scale * scale)
    return ProportionalHazardsParametricResult(
        result.distribution,
        result.coefficient_names,
        _values(coefficients),
        _rows(covariance),
        1.0 / scale,
        result.fingerprint,
        result.n_observations,
    )
