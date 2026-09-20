"""Bounded multiple-imputation pooling and ``processMI`` replacements."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Integral, Real
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias, cast, overload

import numpy as np
import numpy.typing as npt

from holocron._serialization import canonical_json, parse_json_object, validate_sha256
from holocron.exceptions import InputValidationError, NumericalError
from holocron.models.linear import OlsResult
from holocron.models.logistic import BinaryLogisticResult
from holocron.models.postfit import (
    _regularized_gamma_q,  # pyright: ignore[reportPrivateUsage]
)
from holocron.validation.optimism import (
    OptimismCorrectedCalibrationResult,
    OptimismCorrectedValidationResult,
    ValidationMetricName,
)

if TYPE_CHECKING:
    from holocron.reporting.specification import TableSpec

FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]
PooledModelFamily: TypeAlias = Literal["ols", "glm-binomial", "lrm-binary"]
ModelSource: TypeAlias = OlsResult | BinaryLogisticResult
SourceStatus: TypeAlias = Literal["complete", "partial", "failed"]
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

POOLED_MODEL_SCHEMA_VERSION = "holocron-pooled-model-result/v1"
POOLED_VALIDATION_SCHEMA_VERSION = "holocron-pooled-validation-result/v1"
POOLED_CALIBRATION_SCHEMA_VERSION = "holocron-pooled-calibration-result/v1"
POOLED_ANOVA_SCHEMA_VERSION = "holocron-pooled-anova-result/v1"
MAX_IMPUTATIONS = 1_000
MAX_PARAMETERS = 257
MAX_OBSERVATIONS = 1_000_000
MAX_CALIBRATION_POINTS = 1_000
MAX_TESTS = 1_000


class _StatusResult(Protocol):
    @property
    def status(self) -> SourceStatus: ...


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InputValidationError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise InputValidationError(f"{name} must be a finite number")
    return result


def _optional_finite(value: object, *, name: str) -> float | None:
    return None if value is None else _finite(value, name=name)


def _integer(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
        or not minimum <= int(value) <= maximum
    ):
        raise InputValidationError(
            f"{name} must be an integer between {minimum} and {maximum}"
        )
    return int(value)


def _names(value: object, *, expected: int | None = None) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise InputValidationError("coefficient_names must be a tuple")
    raw = cast(tuple[object, ...], value)
    if (
        not raw
        or len(raw) > MAX_PARAMETERS
        or (expected is not None and len(raw) != expected)
        or any(not isinstance(item, str) or not item for item in raw)
    ):
        raise InputValidationError("coefficient_names are invalid")
    result = tuple(cast(str, item) for item in raw)
    if len(set(result)) != len(result):
        raise InputValidationError("coefficient_names must be unique")
    return result


def _vector(
    value: object,
    *,
    name: str,
    expected: int | None = None,
    optional: bool = False,
) -> tuple[float | None, ...]:
    if not isinstance(value, tuple):
        raise InputValidationError(f"{name} must be a tuple")
    raw = cast(tuple[object, ...], value)
    if (
        not raw
        or len(raw) > MAX_OBSERVATIONS
        or (expected is not None and len(raw) != expected)
    ):
        raise InputValidationError(f"{name} has invalid dimensions")
    return tuple(
        _optional_finite(item, name=name) if optional else _finite(item, name=name)
        for item in raw
    )


def _finite_vector(
    value: object, *, name: str, expected: int | None = None
) -> tuple[float, ...]:
    return cast(
        tuple[float, ...],
        _vector(value, name=name, expected=expected, optional=False),
    )


def _matrix(value: object, *, name: str, size: int) -> tuple[tuple[float, ...], ...]:
    if not isinstance(value, tuple):
        raise InputValidationError(f"{name} must be square by parameter")
    raw = cast(tuple[object, ...], value)
    if len(raw) != size or any(not isinstance(row, tuple) for row in raw):
        raise InputValidationError(f"{name} rows must be tuples")
    result = tuple(
        _finite_vector(row, name=name, expected=size)
        for row in cast(tuple[tuple[object, ...], ...], raw)
    )
    for row_index, row in enumerate(result):
        for column_index in range(row_index):
            if not math.isclose(
                row[column_index],
                result[column_index][row_index],
                rel_tol=1e-10,
                abs_tol=1e-12,
            ):
                raise InputValidationError(f"{name} must be symmetric")
    return result


def _rows(value: FloatMatrix) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(item) for item in row) for row in value)


def _values(value: FloatVector) -> tuple[float, ...]:
    return tuple(float(item) for item in value)


def _fingerprint(document: dict[str, JsonValue]) -> str:
    return hashlib.sha256(canonical_json(document).encode()).hexdigest()


def _object(document: object, *, version: str, fields: set[str]) -> dict[str, object]:
    if not isinstance(document, dict):
        raise InputValidationError("multiple-imputation document must be an object")
    raw = cast(dict[str, object], document)
    if set(raw) != fields:
        raise InputValidationError("multiple-imputation document fields differ")
    if raw["schema_version"] != version:
        raise InputValidationError("unsupported multiple-imputation schema version")
    return raw


def _read_list(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise InputValidationError(f"{name} must be an array")
    return cast(list[object], value)


def _read_names(value: object) -> tuple[str, ...]:
    return _names(tuple(_read_list(value, name="coefficient_names")))


def _read_vector(
    value: object, *, name: str, optional: bool = False
) -> tuple[float | None, ...]:
    return _vector(tuple(_read_list(value, name=name)), name=name, optional=optional)


def _read_matrix(
    value: object, *, name: str, size: int
) -> tuple[tuple[float, ...], ...]:
    rows = _read_list(value, name=name)
    return _matrix(
        tuple(tuple(_read_list(row, name=name)) for row in rows),
        name=name,
        size=size,
    )


def _source_statuses(value: object, *, expected: int) -> tuple[SourceStatus, ...]:
    if not isinstance(value, tuple):
        raise InputValidationError("source_statuses must match n_imputations")
    raw = cast(tuple[object, ...], value)
    if len(raw) != expected or any(
        item not in {"complete", "partial", "failed"} for item in raw
    ):
        raise InputValidationError("source_statuses contain an unsupported status")
    return cast(tuple[SourceStatus, ...], value)


@dataclass(frozen=True, slots=True)
class PooledModelResult:
    """Rubin-pooled coefficients and covariance for completed-data fits."""

    model_family: PooledModelFamily
    coefficient_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    within_covariance: tuple[tuple[float, ...], ...]
    between_covariance: tuple[tuple[float, ...], ...]
    total_covariance: tuple[tuple[float, ...], ...]
    standard_errors: tuple[float, ...]
    degrees_of_freedom: tuple[float, ...]
    fraction_missing_information: tuple[float, ...]
    relative_increase_variance: tuple[float, ...]
    n_imputations: int
    n_observations: int
    n_features: int
    includes_intercept: bool
    complete_data_degrees_of_freedom: int
    design_fingerprint: str | None
    source_fingerprints: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "glm-binomial", "lrm-binary"}:
            raise InputValidationError("unsupported pooled model_family")
        if not isinstance(cast(object, self.includes_intercept), bool):
            raise InputValidationError("includes_intercept must be boolean")
        count = _integer(
            self.n_imputations,
            name="n_imputations",
            minimum=2,
            maximum=MAX_IMPUTATIONS,
        )
        observations = _integer(
            self.n_observations,
            name="n_observations",
            minimum=2,
            maximum=MAX_OBSERVATIONS,
        )
        features = _integer(
            self.n_features,
            name="n_features",
            minimum=1,
            maximum=MAX_PARAMETERS - 1,
        )
        parameter_count = features + int(self.includes_intercept)
        if not parameter_count < observations:
            raise InputValidationError(
                "pooled model requires positive residual freedom"
            )
        complete_df = _integer(
            self.complete_data_degrees_of_freedom,
            name="complete_data_degrees_of_freedom",
            minimum=1,
            maximum=MAX_OBSERVATIONS,
        )
        object.__setattr__(self, "n_imputations", count)
        object.__setattr__(self, "n_observations", observations)
        object.__setattr__(self, "n_features", features)
        object.__setattr__(self, "complete_data_degrees_of_freedom", complete_df)
        object.__setattr__(
            self,
            "coefficient_names",
            _names(self.coefficient_names, expected=parameter_count),
        )
        for name in ("coefficients", "standard_errors", "degrees_of_freedom"):
            object.__setattr__(
                self,
                name,
                _finite_vector(
                    getattr(self, name), name=name, expected=parameter_count
                ),
            )
        for name in (
            "fraction_missing_information",
            "relative_increase_variance",
        ):
            values = _finite_vector(
                getattr(self, name), name=name, expected=parameter_count
            )
            if any(value < 0.0 for value in values):
                raise InputValidationError(f"{name} must be nonnegative")
            if name == "fraction_missing_information" and any(
                value > 1.0 for value in values
            ):
                raise InputValidationError(
                    "fraction_missing_information must not exceed one"
                )
            object.__setattr__(self, name, values)
        if any(value <= 0.0 for value in self.degrees_of_freedom):
            raise InputValidationError("pooled degrees_of_freedom must be positive")
        for name in (
            "within_covariance",
            "between_covariance",
            "total_covariance",
        ):
            object.__setattr__(
                self,
                name,
                _matrix(getattr(self, name), name=name, size=parameter_count),
            )
        if any(value < 0.0 for value in self.standard_errors):
            raise InputValidationError("standard_errors must be nonnegative")
        if any(
            not math.isclose(
                self.standard_errors[index] ** 2,
                self.total_covariance[index][index],
                rel_tol=1e-10,
                abs_tol=1e-12,
            )
            for index in range(parameter_count)
        ):
            raise InputValidationError(
                "standard_errors must match total covariance diagonal"
            )
        validate_sha256(
            self.design_fingerprint, role="design_fingerprint", nullable=True
        )
        if (
            not isinstance(cast(object, self.source_fingerprints), tuple)
            or len(self.source_fingerprints) != count
        ):
            raise InputValidationError("source_fingerprints must match n_imputations")
        for value in self.source_fingerprints:
            validate_sha256(value, role="source_fingerprint")

    def predict_linear(self, features: Iterable[Iterable[float]]) -> tuple[float, ...]:
        """Predict from the Rubin-pooled coefficient vector."""

        rows = tuple(tuple(row) for row in features)
        if not rows or len(rows) > MAX_OBSERVATIONS:
            raise InputValidationError("prediction features must contain bounded rows")
        if any(len(row) != self.n_features for row in rows):
            raise InputValidationError("prediction features have the wrong shape")
        if any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            for row in rows
            for value in row
        ):
            raise InputValidationError("prediction features must be finite numbers")
        matrix = np.asarray(rows, dtype=np.float64)
        if self.includes_intercept:
            matrix = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
                (np.ones(matrix.shape[0], dtype=np.float64), matrix)
            )
        return _values(matrix @ np.asarray(self.coefficients, dtype=np.float64))

    def predict_response(
        self, features: Iterable[Iterable[float]]
    ) -> tuple[float, ...]:
        """Predict means for OLS or probabilities for binary logistic fits."""

        linear = np.asarray(self.predict_linear(features), dtype=np.float64)
        if self.model_family == "ols":
            return _values(linear)
        result = np.empty_like(linear)
        positive = linear >= 0.0
        result[positive] = 1.0 / (1.0 + np.exp(-linear[positive]))
        exponential = np.exp(linear[~positive])
        result[~positive] = exponential / (1.0 + exponential)
        return _values(result)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned pooled-model document."""

        return {
            "schema_version": POOLED_MODEL_SCHEMA_VERSION,
            "model_family": self.model_family,
            "coefficient_names": list(self.coefficient_names),
            "coefficients": list(self.coefficients),
            "within_covariance": [list(row) for row in self.within_covariance],
            "between_covariance": [list(row) for row in self.between_covariance],
            "total_covariance": [list(row) for row in self.total_covariance],
            "standard_errors": list(self.standard_errors),
            "degrees_of_freedom": list(self.degrees_of_freedom),
            "fraction_missing_information": list(self.fraction_missing_information),
            "relative_increase_variance": list(self.relative_increase_variance),
            "n_imputations": self.n_imputations,
            "n_observations": self.n_observations,
            "n_features": self.n_features,
            "includes_intercept": self.includes_intercept,
            "complete_data_degrees_of_freedom": (self.complete_data_degrees_of_freedom),
            "design_fingerprint": self.design_fingerprint,
            "source_fingerprints": list(self.source_fingerprints),
        }

    def to_json(self) -> str:
        """Serialize the pooled model as canonical non-executable JSON."""

        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return the SHA-256 identity of the canonical document."""

        return _fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: object) -> PooledModelResult:
        """Reconstruct a pooled model from an exact-version document."""

        fields = {
            "schema_version",
            "model_family",
            "coefficient_names",
            "coefficients",
            "within_covariance",
            "between_covariance",
            "total_covariance",
            "standard_errors",
            "degrees_of_freedom",
            "fraction_missing_information",
            "relative_increase_variance",
            "n_imputations",
            "n_observations",
            "n_features",
            "includes_intercept",
            "complete_data_degrees_of_freedom",
            "design_fingerprint",
            "source_fingerprints",
        }
        raw = _object(document, version=POOLED_MODEL_SCHEMA_VERSION, fields=fields)
        names = _read_names(raw["coefficient_names"])
        size = len(names)
        return cls(
            cast(PooledModelFamily, raw["model_family"]),
            names,
            cast(
                tuple[float, ...],
                _read_vector(raw["coefficients"], name="coefficients"),
            ),
            _read_matrix(raw["within_covariance"], name="within_covariance", size=size),
            _read_matrix(
                raw["between_covariance"], name="between_covariance", size=size
            ),
            _read_matrix(raw["total_covariance"], name="total_covariance", size=size),
            cast(
                tuple[float, ...],
                _read_vector(raw["standard_errors"], name="standard_errors"),
            ),
            cast(
                tuple[float, ...],
                _read_vector(raw["degrees_of_freedom"], name="degrees_of_freedom"),
            ),
            cast(
                tuple[float, ...],
                _read_vector(
                    raw["fraction_missing_information"],
                    name="fraction_missing_information",
                ),
            ),
            cast(
                tuple[float, ...],
                _read_vector(
                    raw["relative_increase_variance"], name="relative_increase_variance"
                ),
            ),
            cast(int, raw["n_imputations"]),
            cast(int, raw["n_observations"]),
            cast(int, raw["n_features"]),
            cast(bool, raw["includes_intercept"]),
            cast(int, raw["complete_data_degrees_of_freedom"]),
            cast(str | None, raw["design_fingerprint"]),
            tuple(
                cast(str, item)
                for item in _read_list(
                    raw["source_fingerprints"], name="source_fingerprints"
                )
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> PooledModelResult:
        """Reconstruct a pooled model from strict bounded JSON."""

        return cls.from_dict(parse_json_object(value, role="pooled model result"))


def _model_family(model: ModelSource) -> PooledModelFamily:
    if isinstance(model, OlsResult):
        return "ols"
    return "glm-binomial" if model.estimator == "glm" else "lrm-binary"


def pool_imputation_models(results: Iterable[ModelSource]) -> PooledModelResult:
    """Pool compatible OLS or binary-logistic fits using Rubin's rules."""

    models = tuple(results)
    if not 2 <= len(models) <= MAX_IMPUTATIONS:
        raise InputValidationError(
            f"multiple-imputation pooling requires 2-{MAX_IMPUTATIONS} fits"
        )
    first = models[0]
    if not isinstance(cast(object, first), (OlsResult, BinaryLogisticResult)) or any(
        type(model) is not type(first) for model in models
    ):
        raise InputValidationError(
            "pooled fits must share one supported concrete model type"
        )
    typed = models
    family = _model_family(first)
    names = first.coefficient_names
    fingerprint = first.design_fingerprint
    if any(
        model.coefficient_names != names
        or model.n_observations != first.n_observations
        or model.n_features != first.n_features
        or model.includes_intercept != first.includes_intercept
        or model.design_fingerprint != fingerprint
        or _model_family(model) != family
        for model in typed[1:]
    ):
        raise InputValidationError(
            "pooled fits must share coefficient, design, family, and row identity"
        )
    estimates = np.asarray(
        tuple(model.coefficients for model in typed), dtype=np.float64
    )
    covariances = np.asarray(
        tuple(model.covariance for model in typed), dtype=np.float64
    )
    mean = np.mean(estimates, axis=0)
    within = np.mean(covariances, axis=0)
    centered = estimates - mean
    between = centered.T @ centered / (len(typed) - 1)
    total = within + (1.0 + 1.0 / len(typed)) * between
    within_diagonal = np.diag(  # pyright: ignore[reportUnknownMemberType]
        within
    )
    total_diagonal = np.diag(  # pyright: ignore[reportUnknownMemberType]
        total
    )
    between_diagonal = np.diag(  # pyright: ignore[reportUnknownMemberType]
        between
    )
    if np.any(within_diagonal <= 0.0) or np.any(total_diagonal <= 0.0):  # pyright: ignore[reportUnknownMemberType]
        raise NumericalError("pooled covariance diagonals must be positive")
    standard_errors = np.sqrt(total_diagonal)
    inflation = (1.0 + 1.0 / len(typed)) * between_diagonal / within_diagonal
    missing_fraction = inflation / (1.0 + inflation)
    complete_df = (
        first.residual_degrees_of_freedom
        if isinstance(first, OlsResult)
        else first.n_observations - first.rank
    )
    old_df = np.full(inflation.shape, np.inf, dtype=np.float64)
    positive_inflation = inflation > 0.0
    old_df[positive_inflation] = (len(typed) - 1) * (
        1.0 + 1.0 / inflation[positive_inflation]
    ) ** 2
    observed_df = (
        (complete_df + 1.0)
        / (complete_df + 3.0)
        * complete_df
        * (1.0 - missing_fraction)
    )
    pooled_df = 1.0 / (1.0 / old_df + 1.0 / observed_df)
    fmi = (inflation + 2.0 / (pooled_df + 3.0)) / (inflation + 1.0)
    return PooledModelResult(
        family,
        names,
        _values(mean),
        _rows(within),
        _rows(between),
        _rows(total),
        _values(standard_errors),
        _values(pooled_df),
        _values(fmi),
        _values(inflation),
        len(typed),
        first.n_observations,
        first.n_features,
        first.includes_intercept,
        complete_df,
        fingerprint,
        tuple(model.fingerprint for model in typed),
    )


@dataclass(frozen=True, slots=True)
class PooledValidationMetric:
    """One validation metric averaged over completed-data analyses."""

    name: ValidationMetricName
    apparent: float | None
    mean_training: float | None
    mean_assessment: float | None
    optimism: float | None
    corrected: float | None
    contributing_imputations: int
    contributing_resamples: int

    def __post_init__(self) -> None:
        if self.name not in {
            "r_squared",
            "mean_squared_error",
            "dxy",
            "brier_score",
            "calibration_intercept",
            "calibration_slope",
        }:
            raise InputValidationError("unsupported pooled validation metric")
        for name in (
            "apparent",
            "mean_training",
            "mean_assessment",
            "optimism",
            "corrected",
        ):
            object.__setattr__(
                self, name, _optional_finite(getattr(self, name), name=name)
            )
        imputation_count = _integer(
            self.contributing_imputations,
            name="contributing_imputations",
            minimum=0,
            maximum=MAX_IMPUTATIONS,
        )
        resample_count = _integer(
            self.contributing_resamples,
            name="contributing_resamples",
            minimum=0,
            maximum=10_000_000,
        )
        object.__setattr__(self, "contributing_imputations", imputation_count)
        object.__setattr__(self, "contributing_resamples", resample_count)
        aggregates = (
            self.apparent,
            self.mean_training,
            self.mean_assessment,
            self.optimism,
            self.corrected,
        )
        if imputation_count == 0:
            if any(value is not None for value in aggregates) or resample_count != 0:
                raise InputValidationError(
                    "undefined pooled metrics must not retain estimates or resamples"
                )
            return
        if (
            any(value is None for value in aggregates)
            or resample_count < imputation_count
        ):
            raise InputValidationError(
                "defined pooled metrics require complete estimates and contributors"
            )
        assert self.apparent is not None
        assert self.mean_training is not None
        assert self.mean_assessment is not None
        assert self.optimism is not None
        assert self.corrected is not None
        if not math.isclose(
            self.optimism,
            self.mean_training - self.mean_assessment,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.corrected,
            self.apparent - self.optimism,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise InputValidationError(
                "pooled validation metric violates correction identities"
            )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "apparent": self.apparent,
            "mean_training": self.mean_training,
            "mean_assessment": self.mean_assessment,
            "optimism": self.optimism,
            "corrected": self.corrected,
            "contributing_imputations": self.contributing_imputations,
            "contributing_resamples": self.contributing_resamples,
        }

    @classmethod
    def from_dict(cls, document: object) -> PooledValidationMetric:
        if not isinstance(document, dict):
            raise InputValidationError("pooled validation metric must be an object")
        raw = cast(dict[str, object], document)
        fields = {
            "name",
            "apparent",
            "mean_training",
            "mean_assessment",
            "optimism",
            "corrected",
            "contributing_imputations",
            "contributing_resamples",
        }
        if set(raw) != fields:
            raise InputValidationError("pooled validation metric fields differ")
        return cls(
            cast(ValidationMetricName, raw["name"]),
            _optional_finite(raw["apparent"], name="apparent"),
            _optional_finite(raw["mean_training"], name="mean_training"),
            _optional_finite(raw["mean_assessment"], name="mean_assessment"),
            _optional_finite(raw["optimism"], name="optimism"),
            _optional_finite(raw["corrected"], name="corrected"),
            cast(int, raw["contributing_imputations"]),
            cast(int, raw["contributing_resamples"]),
        )


@dataclass(frozen=True, slots=True)
class PooledValidationResult:
    """Validation indices averaged across completed-data analyses."""

    model_family: Literal["ols", "binary-logistic"]
    metrics: tuple[PooledValidationMetric, ...]
    n_imputations: int
    source_statuses: tuple[SourceStatus, ...]
    source_failure_rates: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported pooled validation model_family")
        count = _integer(
            self.n_imputations,
            name="n_imputations",
            minimum=2,
            maximum=MAX_IMPUTATIONS,
        )
        expected = (
            (
                "r_squared",
                "mean_squared_error",
                "calibration_intercept",
                "calibration_slope",
            )
            if self.model_family == "ols"
            else (
                "dxy",
                "brier_score",
                "calibration_intercept",
                "calibration_slope",
            )
        )
        if (
            not isinstance(cast(object, self.metrics), tuple)
            or any(
                not isinstance(cast(object, metric), PooledValidationMetric)
                for metric in self.metrics
            )
            or tuple(metric.name for metric in self.metrics) != expected
        ):
            raise InputValidationError(
                "pooled validation metrics do not match model_family"
            )
        object.__setattr__(self, "n_imputations", count)
        object.__setattr__(
            self,
            "source_statuses",
            _source_statuses(self.source_statuses, expected=count),
        )
        rates = _finite_vector(
            self.source_failure_rates,
            name="source_failure_rates",
            expected=count,
        )
        if any(not 0.0 <= value <= 1.0 for value in rates):
            raise InputValidationError("source_failure_rates must be probabilities")
        object.__setattr__(self, "source_failure_rates", rates)
        if any(metric.contributing_imputations > count for metric in self.metrics):
            raise InputValidationError(
                "metric contributors exceed the number of imputations"
            )

    def metric(self, name: ValidationMetricName) -> PooledValidationMetric:
        """Return one named pooled metric."""

        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise InputValidationError(f"metric {name!r} is unavailable")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned pooled-validation document."""

        return {
            "schema_version": POOLED_VALIDATION_SCHEMA_VERSION,
            "model_family": self.model_family,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "n_imputations": self.n_imputations,
            "source_statuses": list(self.source_statuses),
            "source_failure_rates": list(self.source_failure_rates),
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: object) -> PooledValidationResult:
        fields = {
            "schema_version",
            "model_family",
            "metrics",
            "n_imputations",
            "source_statuses",
            "source_failure_rates",
        }
        raw = _object(document, version=POOLED_VALIDATION_SCHEMA_VERSION, fields=fields)
        return cls(
            cast(Literal["ols", "binary-logistic"], raw["model_family"]),
            tuple(
                PooledValidationMetric.from_dict(item)
                for item in _read_list(raw["metrics"], name="metrics")
            ),
            cast(int, raw["n_imputations"]),
            tuple(
                cast(SourceStatus, item)
                for item in _read_list(raw["source_statuses"], name="source_statuses")
            ),
            cast(
                tuple[float, ...],
                _read_vector(raw["source_failure_rates"], name="source_failure_rates"),
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> PooledValidationResult:
        return cls.from_dict(parse_json_object(value, role="pooled validation result"))


def _require_sources(
    results: Iterable[_StatusResult],
    expected_type: type[object],
    *,
    allow_partial: bool,
) -> tuple[_StatusResult, ...]:
    if not isinstance(cast(object, allow_partial), bool):
        raise InputValidationError("allow_partial must be boolean")
    sources = tuple(results)
    if not 2 <= len(sources) <= MAX_IMPUTATIONS or any(
        not isinstance(source, expected_type) for source in sources
    ):
        raise InputValidationError(
            f"pooling requires 2-{MAX_IMPUTATIONS} homogeneous results"
        )
    statuses = tuple(source.status for source in sources)
    if any(status != "complete" for status in statuses) and not allow_partial:
        raise InputValidationError(
            "an imputation result is partial; pass allow_partial=True explicitly"
        )
    return sources


def pool_imputation_validation(
    results: Iterable[OptimismCorrectedValidationResult],
    *,
    allow_partial: bool = False,
) -> PooledValidationResult:
    """Average optimism-corrected validation outputs across imputations."""

    sources = cast(
        tuple[OptimismCorrectedValidationResult, ...],
        _require_sources(
            cast(Iterable[_StatusResult], results),
            OptimismCorrectedValidationResult,
            allow_partial=allow_partial,
        ),
    )
    first = sources[0]
    names = cast(
        tuple[ValidationMetricName, ...],
        tuple(metric.name for metric in first.metrics),
    )
    if any(
        source.model_family != first.model_family
        or tuple(metric.name for metric in source.metrics) != names
        for source in sources[1:]
    ):
        raise InputValidationError(
            "validation inputs must share model family and metric identity"
        )
    pooled: list[PooledValidationMetric] = []
    for index, name in enumerate(names):
        candidates = tuple(
            source.metrics[index]
            for source in sources
            if source.metrics[index].corrected is not None
            and source.metrics[index].apparent is not None
            and source.metrics[index].mean_training is not None
            and source.metrics[index].mean_assessment is not None
        )
        if not candidates:
            pooled.append(
                PooledValidationMetric(name, None, None, None, None, None, 0, 0)
            )
            continue
        count = len(candidates)
        apparent = math.fsum(cast(float, item.apparent) for item in candidates) / count
        training = (
            math.fsum(cast(float, item.mean_training) for item in candidates) / count
        )
        assessment = (
            math.fsum(cast(float, item.mean_assessment) for item in candidates) / count
        )
        optimism = training - assessment
        pooled.append(
            PooledValidationMetric(
                name,
                apparent,
                training,
                assessment,
                optimism,
                apparent - optimism,
                count,
                sum(item.contributing_resamples for item in candidates),
            )
        )
    return PooledValidationResult(
        first.model_family,
        tuple(pooled),
        len(sources),
        tuple(source.status for source in sources),
        tuple(source.failure_rate for source in sources),
    )


@dataclass(frozen=True, slots=True)
class PooledCalibrationResult:
    """Pointwise calibration curves averaged across imputations."""

    model_family: Literal["ols", "binary-logistic"]
    scale: Literal["response", "probability"]
    prediction_grid: tuple[float, ...]
    apparent_curve: tuple[float, ...]
    mean_training_curve: tuple[float, ...]
    mean_assessment_curve: tuple[float, ...]
    optimism_curve: tuple[float, ...]
    corrected_curve: tuple[float, ...]
    n_imputations: int
    contributing_resamples: int
    source_statuses: tuple[SourceStatus, ...]
    source_failure_rates: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported pooled calibration model_family")
        expected_scale = "response" if self.model_family == "ols" else "probability"
        if self.scale != expected_scale:
            raise InputValidationError("calibration scale does not match model family")
        count = _integer(
            self.n_imputations,
            name="n_imputations",
            minimum=2,
            maximum=MAX_IMPUTATIONS,
        )
        contributors = _integer(
            self.contributing_resamples,
            name="contributing_resamples",
            minimum=count,
            maximum=10_000_000,
        )
        grid = _finite_vector(self.prediction_grid, name="prediction_grid")
        if not 2 <= len(grid) <= MAX_CALIBRATION_POINTS or any(
            left >= right for left, right in zip(grid, grid[1:], strict=False)
        ):
            raise InputValidationError("prediction_grid must be bounded and increasing")
        if self.scale == "probability" and any(not 0.0 < value < 1.0 for value in grid):
            raise InputValidationError("probability grid must be inside zero and one")
        object.__setattr__(self, "prediction_grid", grid)
        curves = (
            "apparent_curve",
            "mean_training_curve",
            "mean_assessment_curve",
            "optimism_curve",
            "corrected_curve",
        )
        for name in curves:
            object.__setattr__(
                self,
                name,
                _finite_vector(getattr(self, name), name=name, expected=len(grid)),
            )
        if self.scale == "probability" and any(
            not 0.0 <= value <= 1.0
            for curve in (
                self.apparent_curve,
                self.mean_training_curve,
                self.mean_assessment_curve,
            )
            for value in curve
        ):
            raise InputValidationError(
                "uncorrected probability calibration curves must be probabilities"
            )
        for index in range(len(grid)):
            if not math.isclose(
                self.optimism_curve[index],
                self.mean_training_curve[index] - self.mean_assessment_curve[index],
                rel_tol=1e-12,
                abs_tol=1e-12,
            ) or not math.isclose(
                self.corrected_curve[index],
                self.apparent_curve[index] - self.optimism_curve[index],
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise InputValidationError(
                    "pooled calibration curves violate correction identities"
                )
        object.__setattr__(self, "n_imputations", count)
        object.__setattr__(self, "contributing_resamples", contributors)
        object.__setattr__(
            self,
            "source_statuses",
            _source_statuses(self.source_statuses, expected=count),
        )
        rates = _finite_vector(
            self.source_failure_rates,
            name="source_failure_rates",
            expected=count,
        )
        if any(not 0.0 <= value <= 1.0 for value in rates):
            raise InputValidationError("source_failure_rates must be probabilities")
        object.__setattr__(self, "source_failure_rates", rates)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned pooled-calibration document."""

        return {
            "schema_version": POOLED_CALIBRATION_SCHEMA_VERSION,
            "model_family": self.model_family,
            "scale": self.scale,
            "prediction_grid": list(self.prediction_grid),
            "apparent_curve": list(self.apparent_curve),
            "mean_training_curve": list(self.mean_training_curve),
            "mean_assessment_curve": list(self.mean_assessment_curve),
            "optimism_curve": list(self.optimism_curve),
            "corrected_curve": list(self.corrected_curve),
            "n_imputations": self.n_imputations,
            "contributing_resamples": self.contributing_resamples,
            "source_statuses": list(self.source_statuses),
            "source_failure_rates": list(self.source_failure_rates),
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: object) -> PooledCalibrationResult:
        fields = {
            "schema_version",
            "model_family",
            "scale",
            "prediction_grid",
            "apparent_curve",
            "mean_training_curve",
            "mean_assessment_curve",
            "optimism_curve",
            "corrected_curve",
            "n_imputations",
            "contributing_resamples",
            "source_statuses",
            "source_failure_rates",
        }
        raw = _object(
            document, version=POOLED_CALIBRATION_SCHEMA_VERSION, fields=fields
        )
        return cls(
            cast(Literal["ols", "binary-logistic"], raw["model_family"]),
            cast(Literal["response", "probability"], raw["scale"]),
            cast(
                tuple[float, ...],
                _read_vector(raw["prediction_grid"], name="prediction_grid"),
            ),
            cast(
                tuple[float, ...],
                _read_vector(raw["apparent_curve"], name="apparent_curve"),
            ),
            cast(
                tuple[float, ...],
                _read_vector(raw["mean_training_curve"], name="mean_training_curve"),
            ),
            cast(
                tuple[float, ...],
                _read_vector(
                    raw["mean_assessment_curve"], name="mean_assessment_curve"
                ),
            ),
            cast(
                tuple[float, ...],
                _read_vector(raw["optimism_curve"], name="optimism_curve"),
            ),
            cast(
                tuple[float, ...],
                _read_vector(raw["corrected_curve"], name="corrected_curve"),
            ),
            cast(int, raw["n_imputations"]),
            cast(int, raw["contributing_resamples"]),
            tuple(
                cast(SourceStatus, item)
                for item in _read_list(raw["source_statuses"], name="source_statuses")
            ),
            cast(
                tuple[float, ...],
                _read_vector(raw["source_failure_rates"], name="source_failure_rates"),
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> PooledCalibrationResult:
        return cls.from_dict(parse_json_object(value, role="pooled calibration result"))


def _interpolate_extrapolate(
    source_x: tuple[float, ...], source_y: tuple[float, ...], target: FloatVector
) -> FloatVector:
    if len(source_x) != len(source_y) or len(source_x) < 2:
        raise InputValidationError("calibration sources require two aligned points")
    x = np.asarray(source_x, dtype=np.float64)
    y = np.asarray(source_y, dtype=np.float64)
    if np.any(np.diff(x) <= 0.0):  # pyright: ignore[reportUnknownMemberType]
        raise InputValidationError("source calibration grids must increase")
    result = np.interp(target, x, y)
    left = target < x[0]
    right = target > x[-1]
    result[left] = y[0] + (target[left] - x[0]) * (y[1] - y[0]) / (x[1] - x[0])
    result[right] = y[-1] + (target[right] - x[-1]) * (y[-1] - y[-2]) / (x[-1] - x[-2])
    return result


def pool_imputation_calibration(
    results: Iterable[OptimismCorrectedCalibrationResult],
    *,
    prediction_grid: Iterable[float] | None = None,
    grid_points: int | None = None,
    allow_partial: bool = False,
) -> PooledCalibrationResult:
    """Interpolate and average corrected calibration curves by imputation."""

    sources = cast(
        tuple[OptimismCorrectedCalibrationResult, ...],
        _require_sources(
            cast(Iterable[_StatusResult], results),
            OptimismCorrectedCalibrationResult,
            allow_partial=allow_partial,
        ),
    )
    first = sources[0]
    if any(
        source.model_family != first.model_family or source.scale != first.scale
        for source in sources[1:]
    ):
        raise InputValidationError(
            "calibration inputs must share model family and prediction scale"
        )
    if prediction_grid is not None and grid_points is not None:
        raise InputValidationError("supply prediction_grid or grid_points, not both")
    if prediction_grid is None:
        points = (
            max(len(source.prediction_grid) for source in sources)
            if grid_points is None
            else _integer(
                grid_points,
                name="grid_points",
                minimum=2,
                maximum=MAX_CALIBRATION_POINTS,
            )
        )
        lower = min(source.prediction_grid[0] for source in sources)
        upper = max(source.prediction_grid[-1] for source in sources)
        if lower >= upper:
            raise NumericalError("pooled calibration grid has no positive range")
        target = np.linspace(lower, upper, points)
    else:
        target = np.asarray(tuple(prediction_grid), dtype=np.float64)
    grid = _finite_vector(_values(target), name="prediction_grid")
    if not 2 <= len(grid) <= MAX_CALIBRATION_POINTS or any(
        left >= right for left, right in zip(grid, grid[1:], strict=False)
    ):
        raise InputValidationError("prediction_grid must be bounded and increasing")
    if first.scale == "probability" and any(not 0.0 < value < 1.0 for value in grid):
        raise InputValidationError("probability grid must be inside zero and one")
    target = np.asarray(grid, dtype=np.float64)

    def average(name: str) -> tuple[float, ...]:
        matrix = np.asarray(
            tuple(
                _interpolate_extrapolate(
                    source.prediction_grid,
                    cast(tuple[float, ...], getattr(source, name)),
                    target,
                )
                for source in sources
            ),
            dtype=np.float64,
        )
        return _values(np.mean(matrix, axis=0))

    apparent = average("apparent_curve")
    training = average("mean_training_curve")
    assessment = average("mean_assessment_curve")
    optimism = tuple(
        left - right for left, right in zip(training, assessment, strict=True)
    )
    corrected = tuple(
        value - gap for value, gap in zip(apparent, optimism, strict=True)
    )
    return PooledCalibrationResult(
        first.model_family,
        first.scale,
        grid,
        apparent,
        training,
        assessment,
        optimism,
        corrected,
        len(sources),
        sum(source.contributing_resamples for source in sources),
        tuple(source.status for source in sources),
        tuple(source.failure_rate for source in sources),
    )


@dataclass(frozen=True, slots=True)
class LikelihoodRatioTest:
    """One explicit completed-data or stacked likelihood-ratio test."""

    term: str
    coefficient_names: tuple[str, ...]
    chi_square: float
    degrees_of_freedom: int

    def __post_init__(self) -> None:
        if (
            not isinstance(cast(object, self.term), str)
            or not self.term
            or len(self.term) > 4_096
        ):
            raise InputValidationError("likelihood-ratio term is invalid")
        object.__setattr__(
            self,
            "coefficient_names",
            _names(self.coefficient_names),
        )
        statistic = _finite(self.chi_square, name="chi_square")
        if statistic < 0.0:
            raise InputValidationError("chi_square must be nonnegative")
        object.__setattr__(self, "chi_square", statistic)
        object.__setattr__(
            self,
            "degrees_of_freedom",
            _integer(
                self.degrees_of_freedom,
                name="degrees_of_freedom",
                minimum=1,
                maximum=MAX_PARAMETERS,
            ),
        )


@dataclass(frozen=True, slots=True)
class LikelihoodRatioAnova:
    """An ordered explicit likelihood-ratio table for one data realization."""

    tests: tuple[LikelihoodRatioTest, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(cast(object, self.tests), tuple)
            or not 1 <= len(self.tests) <= MAX_TESTS
            or any(
                not isinstance(cast(object, test), LikelihoodRatioTest)
                for test in self.tests
            )
        ):
            raise InputValidationError("likelihood-ratio tests are invalid")


@dataclass(frozen=True, slots=True)
class MultipleImputationAnovaTest:
    """One Chan–Meng-adjusted likelihood-ratio test."""

    term: str
    coefficient_names: tuple[str, ...]
    degrees_of_freedom: int
    mean_imputation_chi_square: float
    stacked_chi_square: float
    adjusted_chi_square: float
    p_value: float
    missing_information_fraction: float
    denominator_degrees_of_freedom: float | None
    chi_square_discount: float

    def __post_init__(self) -> None:
        identity = LikelihoodRatioTest(
            self.term,
            self.coefficient_names,
            self.mean_imputation_chi_square,
            self.degrees_of_freedom,
        )
        object.__setattr__(self, "term", identity.term)
        object.__setattr__(self, "coefficient_names", identity.coefficient_names)
        object.__setattr__(self, "mean_imputation_chi_square", identity.chi_square)
        object.__setattr__(self, "degrees_of_freedom", identity.degrees_of_freedom)
        for name in (
            "stacked_chi_square",
            "adjusted_chi_square",
            "p_value",
            "missing_information_fraction",
            "chi_square_discount",
        ):
            value = _finite(getattr(self, name), name=name)
            if value < 0.0:
                raise InputValidationError(f"{name} must be nonnegative")
            object.__setattr__(self, name, value)
        if (
            self.p_value > 1.0
            or self.missing_information_fraction > 1.0
            or self.chi_square_discount > 1.0
        ):
            raise InputValidationError("probability and discount values exceed one")
        denominator = _optional_finite(
            self.denominator_degrees_of_freedom,
            name="denominator_degrees_of_freedom",
        )
        if denominator is not None and denominator <= 0.0:
            raise InputValidationError(
                "denominator_degrees_of_freedom must be positive or None"
            )
        object.__setattr__(self, "denominator_degrees_of_freedom", denominator)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "term": self.term,
            "coefficient_names": list(self.coefficient_names),
            "degrees_of_freedom": self.degrees_of_freedom,
            "mean_imputation_chi_square": self.mean_imputation_chi_square,
            "stacked_chi_square": self.stacked_chi_square,
            "adjusted_chi_square": self.adjusted_chi_square,
            "p_value": self.p_value,
            "missing_information_fraction": self.missing_information_fraction,
            "denominator_degrees_of_freedom": (self.denominator_degrees_of_freedom),
            "chi_square_discount": self.chi_square_discount,
        }

    @classmethod
    def from_dict(cls, document: object) -> MultipleImputationAnovaTest:
        if not isinstance(document, dict):
            raise InputValidationError("pooled ANOVA test must be an object")
        raw = cast(dict[str, object], document)
        fields = {
            "term",
            "coefficient_names",
            "degrees_of_freedom",
            "mean_imputation_chi_square",
            "stacked_chi_square",
            "adjusted_chi_square",
            "p_value",
            "missing_information_fraction",
            "denominator_degrees_of_freedom",
            "chi_square_discount",
        }
        if set(raw) != fields:
            raise InputValidationError("pooled ANOVA test fields differ")
        return cls(
            cast(str, raw["term"]),
            _read_names(raw["coefficient_names"]),
            cast(int, raw["degrees_of_freedom"]),
            _finite(
                raw["mean_imputation_chi_square"],
                name="mean_imputation_chi_square",
            ),
            _finite(raw["stacked_chi_square"], name="stacked_chi_square"),
            _finite(raw["adjusted_chi_square"], name="adjusted_chi_square"),
            _finite(raw["p_value"], name="p_value"),
            _finite(
                raw["missing_information_fraction"],
                name="missing_information_fraction",
            ),
            _optional_finite(
                raw["denominator_degrees_of_freedom"],
                name="denominator_degrees_of_freedom",
            ),
            _finite(raw["chi_square_discount"], name="chi_square_discount"),
        )


@dataclass(frozen=True, slots=True)
class MultipleImputationAnovaResult:
    """Chan–Meng likelihood-ratio adjustments over multiple imputations."""

    tests: tuple[MultipleImputationAnovaTest, ...]
    n_imputations: int

    def __post_init__(self) -> None:
        count = _integer(
            self.n_imputations,
            name="n_imputations",
            minimum=2,
            maximum=MAX_IMPUTATIONS,
        )
        if (
            not isinstance(cast(object, self.tests), tuple)
            or not 1 <= len(self.tests) <= MAX_TESTS
            or any(
                not isinstance(cast(object, test), MultipleImputationAnovaTest)
                for test in self.tests
            )
        ):
            raise InputValidationError("pooled ANOVA tests are invalid")
        object.__setattr__(self, "n_imputations", count)

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict versioned pooled-ANOVA document."""

        return {
            "schema_version": POOLED_ANOVA_SCHEMA_VERSION,
            "tests": [test.to_dict() for test in self.tests],
            "n_imputations": self.n_imputations,
        }

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: object) -> MultipleImputationAnovaResult:
        fields = {"schema_version", "tests", "n_imputations"}
        raw = _object(document, version=POOLED_ANOVA_SCHEMA_VERSION, fields=fields)
        return cls(
            tuple(
                MultipleImputationAnovaTest.from_dict(item)
                for item in _read_list(raw["tests"], name="tests")
            ),
            cast(int, raw["n_imputations"]),
        )

    @classmethod
    def from_json(cls, value: str) -> MultipleImputationAnovaResult:
        return cls.from_dict(parse_json_object(value, role="pooled ANOVA result"))


def pool_imputation_likelihood_ratio(
    results: Iterable[LikelihoodRatioAnova],
    *,
    stacked: LikelihoodRatioAnova,
) -> MultipleImputationAnovaResult:
    """Apply the rms 8.2-0 Chan–Meng chi-square adjustment explicitly."""

    sources = tuple(results)
    if not 2 <= len(sources) <= MAX_IMPUTATIONS or any(
        not isinstance(cast(object, source), LikelihoodRatioAnova) for source in sources
    ):
        raise InputValidationError(
            f"likelihood-ratio pooling requires 2-{MAX_IMPUTATIONS} tables"
        )
    if not isinstance(cast(object, stacked), LikelihoodRatioAnova):
        raise InputValidationError("stacked must be a LikelihoodRatioAnova")
    identity = tuple(
        (test.term, test.coefficient_names, test.degrees_of_freedom)
        for test in sources[0].tests
    )
    if tuple(
        (test.term, test.coefficient_names, test.degrees_of_freedom)
        for test in stacked.tests
    ) != identity or any(
        tuple(
            (test.term, test.coefficient_names, test.degrees_of_freedom)
            for test in source.tests
        )
        != identity
        for source in sources[1:]
    ):
        raise InputValidationError(
            "likelihood-ratio tables must have identical ordered tests"
        )
    count = len(sources)
    pooled: list[MultipleImputationAnovaTest] = []
    for index, (term, coefficient_names, degrees) in enumerate(identity):
        mean_statistic = (
            math.fsum(source.tests[index].chi_square for source in sources) / count
        )
        stacked_statistic = stacked.tests[index].chi_square / count
        relative = max(
            0.0,
            (count + 1.0)
            / (degrees * (count - 1.0))
            * (mean_statistic - stacked_statistic),
        )
        missing = relative / (1.0 + relative)
        denominator = (
            None if missing == 0.0 else degrees * (count - 1.0) / (missing * missing)
        )
        discount = 1.0 / (1.0 + relative)
        adjusted = discount * stacked_statistic
        pooled.append(
            MultipleImputationAnovaTest(
                term,
                coefficient_names,
                degrees,
                mean_statistic,
                stacked_statistic,
                adjusted,
                _regularized_gamma_q(degrees / 2.0, adjusted / 2.0),
                missing,
                denominator,
                discount,
            )
        )
    return MultipleImputationAnovaResult(tuple(pooled), count)


def imputation_information_table(
    result: MultipleImputationAnovaResult,
    *,
    table_id: str = "imputation-information",
    title: str = "Imputation penalties",
) -> TableSpec:
    """Return the typed `prmiInfo` replacement without rendering side effects."""

    from holocron.reporting.specification import (
        TableColumn,
        TableMetadata,
        TableRow,
        TableSpec,
    )

    if not isinstance(cast(object, result), MultipleImputationAnovaResult):
        raise InputValidationError("result must be a MultipleImputationAnovaResult")
    columns = (
        TableColumn("test", "Test", "text", "left", 0),
        TableColumn(
            "missing_information",
            "Missing information fraction",
            "probability",
            "right",
            3,
        ),
        TableColumn("denominator_df", "Denominator df", "number", "right", 1),
        TableColumn(
            "chi_square_discount", "Chi-square discount", "probability", "right", 3
        ),
    )
    rows = tuple(
        TableRow(
            f"test-{index}",
            (
                test.term,
                test.missing_information_fraction,
                test.denominator_degrees_of_freedom,
                test.chi_square_discount,
            ),
        )
        for index, test in enumerate(result.tests)
    )
    return TableSpec(
        table_id,
        "anova",
        title,
        columns,
        rows,
        caption="Chan–Meng multiple-imputation likelihood-ratio adjustments.",
        notes=(
            "A missing denominator df denotes zero estimated missing information.",
            "Adjusted tests use chi-square tails; inspect small denominator df values.",
        ),
        metadata=(
            TableMetadata("n_imputations", str(result.n_imputations)),
            TableMetadata("source", "holocron-pooled-anova-result/v1"),
        ),
    )


@overload
def process_multiple_imputation(
    results: Iterable[ModelSource],
    *,
    stacked: None = None,
    prediction_grid: None = None,
    grid_points: None = None,
    allow_partial: bool = False,
) -> PooledModelResult: ...


@overload
def process_multiple_imputation(
    results: Iterable[OptimismCorrectedValidationResult],
    *,
    stacked: None = None,
    prediction_grid: None = None,
    grid_points: None = None,
    allow_partial: bool = False,
) -> PooledValidationResult: ...


@overload
def process_multiple_imputation(
    results: Iterable[OptimismCorrectedCalibrationResult],
    *,
    stacked: None = None,
    prediction_grid: Iterable[float] | None = None,
    grid_points: int | None = None,
    allow_partial: bool = False,
) -> PooledCalibrationResult: ...


@overload
def process_multiple_imputation(
    results: Iterable[LikelihoodRatioAnova],
    *,
    stacked: LikelihoodRatioAnova,
    prediction_grid: None = None,
    grid_points: None = None,
    allow_partial: bool = False,
) -> MultipleImputationAnovaResult: ...


def process_multiple_imputation(
    results: Iterable[object],
    *,
    stacked: LikelihoodRatioAnova | None = None,
    prediction_grid: Iterable[float] | None = None,
    grid_points: int | None = None,
    allow_partial: bool = False,
) -> (
    PooledModelResult
    | PooledValidationResult
    | PooledCalibrationResult
    | MultipleImputationAnovaResult
):
    """Dispatch one homogeneous completed-data result collection explicitly."""

    values = tuple(results)
    if not values:
        raise InputValidationError("multiple-imputation results must not be empty")
    first = values[0]
    if isinstance(first, (OlsResult, BinaryLogisticResult)):
        if (
            stacked is not None
            or prediction_grid is not None
            or grid_points is not None
            or allow_partial
        ):
            raise InputValidationError(
                "model pooling does not accept curve, partial, or ANOVA controls"
            )
        return pool_imputation_models(cast(tuple[ModelSource, ...], values))
    if isinstance(first, OptimismCorrectedValidationResult):
        if (
            stacked is not None
            or prediction_grid is not None
            or grid_points is not None
        ):
            raise InputValidationError(
                "validation pooling does not accept curve or ANOVA controls"
            )
        return pool_imputation_validation(
            cast(tuple[OptimismCorrectedValidationResult, ...], values),
            allow_partial=allow_partial,
        )
    if isinstance(first, OptimismCorrectedCalibrationResult):
        if stacked is not None:
            raise InputValidationError("calibration pooling does not accept stacked")
        return pool_imputation_calibration(
            cast(tuple[OptimismCorrectedCalibrationResult, ...], values),
            prediction_grid=prediction_grid,
            grid_points=grid_points,
            allow_partial=allow_partial,
        )
    if isinstance(first, LikelihoodRatioAnova):
        if stacked is None:
            raise InputValidationError("likelihood-ratio pooling requires stacked")
        if prediction_grid is not None or grid_points is not None or allow_partial:
            raise InputValidationError(
                "likelihood-ratio pooling does not accept curve or partial controls"
            )
        return pool_imputation_likelihood_ratio(
            cast(tuple[LikelihoodRatioAnova, ...], values), stacked=stacked
        )
    raise InputValidationError("unsupported multiple-imputation result type")


__all__ = [
    "LikelihoodRatioAnova",
    "LikelihoodRatioTest",
    "MultipleImputationAnovaResult",
    "MultipleImputationAnovaTest",
    "PooledCalibrationResult",
    "PooledModelResult",
    "PooledValidationMetric",
    "PooledValidationResult",
    "imputation_information_table",
    "pool_imputation_calibration",
    "pool_imputation_likelihood_ratio",
    "pool_imputation_models",
    "pool_imputation_validation",
    "process_multiple_imputation",
]
