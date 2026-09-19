"""Bounded diagnostics, penalty tracing, and selection for supported models."""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Literal, TypeAlias, cast

import numpy as np

from holocron.design import DesignMatrix
from holocron.exceptions import (
    InputValidationError,
    NumericalError,
    UnsupportedFeatureError,
)
from holocron.models.glm import fit_glm, fit_lrm
from holocron.models.linear import OlsResult, fit_ols
from holocron.models.logistic import BinaryLogisticResult
from holocron.models.postfit import anova
from holocron.models.regularization import (
    CovarianceEstimate,
    ModelResult,
    PenalizedResult,
    _analysis_design,  # pyright: ignore[reportPrivateUsage]
    _analysis_response,  # pyright: ignore[reportPrivateUsage]
    fit_penalized_lrm,
    fit_penalized_ols,
    robust_covariance,
)

ModelFamily: TypeAlias = Literal["ols", "binary-logistic"]
PenaltyCriterion: TypeAlias = Literal["aic", "bic"]
MAX_TRACE_POINTS = 1_000
MAX_SELECTION_TERMS = 256


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InputValidationError(f"{name} must be a finite number")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise InputValidationError(f"{name} must be a finite number")
    return normalized


def _model_family(result: ModelResult) -> ModelFamily:
    return "ols" if isinstance(result, OlsResult) else "binary-logistic"


@dataclass(frozen=True, slots=True)
class InfluenceObservation:
    """One row's leverage, residual, Cook distance, and coefficient influence."""

    row_index: int
    leverage: float
    standardized_residual: float
    cooks_distance: float
    coefficient_change: tuple[float, ...]
    dfbetas: tuple[float, ...]
    influential: bool

    def __post_init__(self) -> None:
        raw_index = cast(object, self.row_index)
        if (
            isinstance(raw_index, bool)
            or not isinstance(raw_index, Integral)
            or self.row_index < 0
        ):
            raise InputValidationError("row_index must be a non-negative integer")
        leverage = _finite(self.leverage, name="leverage")
        cooks = _finite(self.cooks_distance, name="cooks_distance")
        if not 0.0 <= leverage <= 1.0 or cooks < 0.0:
            raise InputValidationError("influence leverage or Cook distance is invalid")
        for name in ("standardized_residual",):
            _finite(getattr(self, name), name=name)
        if (
            not isinstance(cast(object, self.coefficient_change), tuple)
            or not self.coefficient_change
            or not isinstance(cast(object, self.dfbetas), tuple)
            or len(self.dfbetas) != len(self.coefficient_change)
        ):
            raise InputValidationError("coefficient influence vectors are invalid")
        for value in (*self.coefficient_change, *self.dfbetas):
            _finite(value, name="coefficient influence")
        if not isinstance(cast(object, self.influential), bool):
            raise InputValidationError("influential must be boolean")


@dataclass(frozen=True, slots=True)
class InfluenceResult:
    """Observation-level influence diagnostics with declared flag thresholds."""

    model_family: ModelFamily
    coefficient_names: tuple[str, ...]
    observations: tuple[InfluenceObservation, ...]
    leverage_threshold: float
    cooks_distance_threshold: float
    dfbeta_threshold: float

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported influence model_family")
        if (
            not isinstance(cast(object, self.coefficient_names), tuple)
            or not self.coefficient_names
            or len(set(self.coefficient_names)) != len(self.coefficient_names)
            or any(not name for name in self.coefficient_names)
        ):
            raise InputValidationError("influence coefficient names are invalid")
        if (
            not isinstance(cast(object, self.observations), tuple)
            or not self.observations
            or any(
                not isinstance(cast(object, value), InfluenceObservation)
                for value in self.observations
            )
            or tuple(value.row_index for value in self.observations)
            != tuple(range(len(self.observations)))
            or any(
                len(value.dfbetas) != len(self.coefficient_names)
                for value in self.observations
            )
        ):
            raise InputValidationError("influence observations are inconsistent")
        for name in (
            "leverage_threshold",
            "cooks_distance_threshold",
            "dfbeta_threshold",
        ):
            if _finite(getattr(self, name), name=name) <= 0.0:
                raise InputValidationError("influence thresholds must be positive")

    @property
    def influential_rows(self) -> tuple[int, ...]:
        """Return row indices exceeding any declared heuristic threshold."""
        return tuple(
            value.row_index for value in self.observations if value.influential
        )


@dataclass(frozen=True, slots=True)
class VarianceInflationFactor:
    """One coefficient's covariance-correlation variance inflation factor."""

    coefficient_name: str
    value: float

    def __post_init__(self) -> None:
        if not self.coefficient_name:
            raise InputValidationError("VIF coefficient_name must not be empty")
        if _finite(self.value, name="VIF") < 1.0 - 1e-10:
            raise InputValidationError("VIF must be at least one")


@dataclass(frozen=True, slots=True)
class CoefficientRobustness:
    """Model-based and cluster-robust uncertainty for one coefficient."""

    coefficient_name: str
    coefficient: float
    model_standard_error: float
    robust_standard_error: float
    robust_to_model_ratio: float

    def __post_init__(self) -> None:
        if not self.coefficient_name:
            raise InputValidationError("coefficient_name must not be empty")
        _finite(self.coefficient, name="coefficient")
        model_se = _finite(self.model_standard_error, name="model_standard_error")
        robust_se = _finite(self.robust_standard_error, name="robust_standard_error")
        ratio = _finite(self.robust_to_model_ratio, name="robust_to_model_ratio")
        if model_se <= 0.0 or robust_se < 0.0 or ratio < 0.0:
            raise InputValidationError("robustness standard errors are invalid")
        if not math.isclose(ratio, robust_se / model_se, rel_tol=1e-12, abs_tol=1e-12):
            raise InputValidationError("robustness ratio is inconsistent")


@dataclass(frozen=True, slots=True)
class RobustnessDiagnostics:
    """Cluster-sandwich covariance and coefficient-level uncertainty changes."""

    covariance: CovarianceEstimate
    coefficients: tuple[CoefficientRobustness, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(cast(object, self.covariance), CovarianceEstimate)
            or self.covariance.method != "robust"
            or not isinstance(cast(object, self.coefficients), tuple)
            or not self.coefficients
            or any(
                not isinstance(cast(object, value), CoefficientRobustness)
                for value in self.coefficients
            )
            or tuple(value.coefficient_name for value in self.coefficients)
            != self.covariance.coefficient_names
        ):
            raise InputValidationError("robustness diagnostics are inconsistent")


@dataclass(frozen=True, slots=True)
class PenaltyTracePoint:
    """One scalar-penalty fit and its effective-complexity criteria."""

    penalty: float
    effective_degrees_of_freedom: float
    deviance: float
    aic: float
    bic: float
    coefficients: tuple[float, ...]

    def __post_init__(self) -> None:
        if _finite(self.penalty, name="penalty") < 0.0:
            raise InputValidationError("penalty must be non-negative")
        if (
            _finite(
                self.effective_degrees_of_freedom,
                name="effective_degrees_of_freedom",
            )
            <= 0.0
        ):
            raise InputValidationError("effective degrees of freedom must be positive")
        for name in ("deviance", "aic", "bic"):
            _finite(getattr(self, name), name=name)
        if (
            not isinstance(cast(object, self.coefficients), tuple)
            or not self.coefficients
        ):
            raise InputValidationError("trace coefficients must be a non-empty tuple")
        for value in self.coefficients:
            _finite(value, name="trace coefficient")


@dataclass(frozen=True, slots=True)
class PenaltyTraceResult:
    """A bounded scalar-penalty path with one selected information criterion."""

    model_family: Literal["ols", "lrm-binary"]
    criterion: PenaltyCriterion
    points: tuple[PenaltyTracePoint, ...]
    selected_penalty: float

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "lrm-binary"}:
            raise InputValidationError("unsupported penalty-trace model_family")
        if self.criterion not in {"aic", "bic"}:
            raise InputValidationError("criterion must be 'aic' or 'bic'")
        if (
            not isinstance(cast(object, self.points), tuple)
            or not self.points
            or len(self.points) > MAX_TRACE_POINTS
            or any(
                not isinstance(cast(object, value), PenaltyTracePoint)
                for value in self.points
            )
            or any(
                left.penalty >= right.penalty
                for left, right in zip(self.points, self.points[1:], strict=False)
            )
        ):
            raise InputValidationError("penalty trace points are invalid")
        selected = _finite(self.selected_penalty, name="selected_penalty")
        best = min(
            self.points,
            key=lambda point: (getattr(point, self.criterion), point.penalty),
        )
        if selected != best.penalty:
            raise InputValidationError("selected penalty does not minimize criterion")

    @property
    def selected_point(self) -> PenaltyTracePoint:
        """Return the criterion-minimizing point, preferring the lower penalty."""
        return next(
            point for point in self.points if point.penalty == self.selected_penalty
        )


@dataclass(frozen=True, slots=True)
class SelectionStep:
    """One fully refitted backward-elimination step."""

    step: int
    removed_term: str
    p_value: float
    remaining_terms: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(cast(object, self.step), bool)
            or not isinstance(cast(object, self.step), Integral)
            or self.step < 1
            or not self.removed_term
        ):
            raise InputValidationError("selection step metadata is invalid")
        p_value = _finite(self.p_value, name="selection p_value")
        if not 0.0 <= p_value <= 1.0:
            raise InputValidationError("selection p_value must be between zero and one")
        if (
            not isinstance(cast(object, self.remaining_terms), tuple)
            or len(set(self.remaining_terms)) != len(self.remaining_terms)
            or any(not term for term in self.remaining_terms)
        ):
            raise InputValidationError("remaining_terms are invalid")


@dataclass(frozen=True, slots=True)
class BackwardSelectionResult:
    """A bounded sequence of term removals with the final fresh model fit."""

    model_family: ModelFamily
    significance_level: float
    initial_terms: tuple[str, ...]
    selected_terms: tuple[str, ...]
    protected_terms: tuple[str, ...]
    steps: tuple[SelectionStep, ...]
    final_model: ModelResult

    def __post_init__(self) -> None:
        if self.model_family not in {"ols", "binary-logistic"}:
            raise InputValidationError("unsupported selection model_family")
        level = _finite(self.significance_level, name="significance_level")
        if not 0.0 < level < 1.0:
            raise InputValidationError(
                "significance_level must be between zero and one"
            )
        if (
            not isinstance(cast(object, self.initial_terms), tuple)
            or not isinstance(cast(object, self.selected_terms), tuple)
            or not isinstance(cast(object, self.protected_terms), tuple)
            or not isinstance(cast(object, self.steps), tuple)
            or not self.initial_terms
            or len(set(self.initial_terms)) != len(self.initial_terms)
            or len(set(self.selected_terms)) != len(self.selected_terms)
            or len(set(self.protected_terms)) != len(self.protected_terms)
            or any(not term for term in self.initial_terms)
            or any(term not in self.initial_terms for term in self.selected_terms)
            or any(term not in self.selected_terms for term in self.protected_terms)
            or any(
                not isinstance(cast(object, step), SelectionStep) for step in self.steps
            )
            or tuple(step.step for step in self.steps)
            != tuple(range(1, len(self.steps) + 1))
            or len(self.steps) != len(self.initial_terms) - len(self.selected_terms)
        ):
            raise InputValidationError("selection terms are inconsistent")
        expected_type = (
            OlsResult if self.model_family == "ols" else BinaryLogisticResult
        )
        if not isinstance(cast(object, self.final_model), expected_type):
            raise InputValidationError("final_model does not match model_family")


def influence_diagnostics(
    result: ModelResult,
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
) -> InfluenceResult:
    """Compute leverage, standardized residual, Cook, and DFBETA diagnostics."""
    if not isinstance(cast(object, result), (OlsResult, BinaryLogisticResult)):
        raise UnsupportedFeatureError(
            "influence diagnostics support OLS and binary-logistic results"
        )
    design = _analysis_design(result, features)
    observed = _analysis_response(result, response)
    parameter_count = design.shape[1]
    if isinstance(result, OlsResult):
        try:
            inverse = np.linalg.solve(
                design.T @ design,
                np.eye(parameter_count, dtype=np.float64),
            )
        except np.linalg.LinAlgError as error:
            raise NumericalError("influence design crossproduct is singular") from error
        raw_residuals = np.asarray(result.residuals, dtype=np.float64)
        scale = result.residual_scale
        leverage = np.einsum("ij,jk,ik->i", design, inverse, design)
        score_residuals = raw_residuals
        pearson = raw_residuals / scale
    else:
        inverse = np.asarray(result.covariance, dtype=np.float64)
        probabilities = np.asarray(result.fitted_probabilities, dtype=np.float64)
        weights = probabilities * (1.0 - probabilities)
        if float(np.min(weights)) <= 0.0:
            raise NumericalError("binary influence requires positive working weights")
        leverage = weights * np.einsum("ij,jk,ik->i", design, inverse, design)
        score_residuals = observed - probabilities
        pearson = score_residuals / np.sqrt(weights)
    if float(np.max(leverage)) >= 1.0 - 1e-12:
        raise NumericalError("influence diagnostics require leverage below one")
    leverage_threshold = 2.0 * parameter_count / result.n_observations
    cooks_threshold = 4.0 / result.n_observations
    dfbeta_threshold = 2.0 / math.sqrt(result.n_observations)
    standard_errors = np.sqrt(
        np.diag(  # pyright: ignore[reportUnknownMemberType]
            np.asarray(result.covariance, dtype=np.float64)
        )
    )
    if float(np.min(standard_errors)) <= 0.0:
        raise NumericalError("influence diagnostics require positive standard errors")
    observations: list[InfluenceObservation] = []
    for index in range(result.n_observations):
        one_minus = 1.0 - float(leverage[index])
        standardized = float(pearson[index]) / math.sqrt(one_minus)
        change = inverse @ design[index, :] * float(score_residuals[index]) / one_minus
        dfbetas = change / standard_errors
        cooks = standardized**2 * float(leverage[index]) / (parameter_count * one_minus)
        influential = (
            float(leverage[index]) > leverage_threshold
            or cooks > cooks_threshold
            or float(np.max(np.abs(dfbetas))) > dfbeta_threshold
        )
        observations.append(
            InfluenceObservation(
                row_index=index,
                leverage=float(leverage[index]),
                standardized_residual=standardized,
                cooks_distance=cooks,
                coefficient_change=tuple(float(value) for value in change),
                dfbetas=tuple(float(value) for value in dfbetas),
                influential=influential,
            )
        )
    return InfluenceResult(
        model_family=_model_family(result),
        coefficient_names=result.coefficient_names,
        observations=tuple(observations),
        leverage_threshold=leverage_threshold,
        cooks_distance_threshold=cooks_threshold,
        dfbeta_threshold=dfbeta_threshold,
    )


def variance_inflation_factors(
    result: ModelResult,
) -> tuple[VarianceInflationFactor, ...]:
    """Compute covariance-correlation VIFs for non-intercept coefficients."""
    if not isinstance(cast(object, result), (OlsResult, BinaryLogisticResult)):
        raise UnsupportedFeatureError("VIF supports OLS and binary-logistic results")
    offset = int(result.includes_intercept)
    names = result.coefficient_names[offset:]
    covariance = np.asarray(result.covariance, dtype=np.float64)[offset:, offset:]
    if not names:
        raise InputValidationError("VIF requires at least one slope coefficient")
    diagonal = np.diag(  # pyright: ignore[reportUnknownMemberType]
        covariance
    )
    if float(np.min(diagonal)) <= 0.0:
        raise NumericalError("VIF requires positive covariance diagonal values")
    scale = np.sqrt(diagonal)
    correlation = covariance / np.outer(scale, scale)
    try:
        inverse = np.linalg.solve(
            correlation,
            np.eye(correlation.shape[0], dtype=np.float64),
        )
    except np.linalg.LinAlgError as error:
        raise NumericalError("coefficient correlation matrix is singular") from error
    return tuple(
        VarianceInflationFactor(name, max(1.0, float(inverse[index, index])))
        for index, name in enumerate(names)
    )


def robustness_diagnostics(
    result: ModelResult,
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    clusters: Iterable[Hashable] | None = None,
) -> RobustnessDiagnostics:
    """Compare model-based standard errors with the robust sandwich estimate."""
    if not isinstance(cast(object, result), (OlsResult, BinaryLogisticResult)):
        raise UnsupportedFeatureError(
            "robustness diagnostics support OLS and binary-logistic results"
        )
    covariance = robust_covariance(
        result,
        response,
        features,
        clusters=clusters,
    )
    model_matrix = np.asarray(result.covariance, dtype=np.float64)
    robust_matrix = np.asarray(covariance.matrix, dtype=np.float64)
    summaries: list[CoefficientRobustness] = []
    for index, name in enumerate(result.coefficient_names):
        model_se = math.sqrt(max(0.0, float(model_matrix[index, index])))
        robust_se = math.sqrt(max(0.0, float(robust_matrix[index, index])))
        if model_se <= 0.0:
            raise NumericalError("robustness diagnostics require positive model SEs")
        summaries.append(
            CoefficientRobustness(
                coefficient_name=name,
                coefficient=result.coefficients[index],
                model_standard_error=model_se,
                robust_standard_error=robust_se,
                robust_to_model_ratio=robust_se / model_se,
            )
        )
    return RobustnessDiagnostics(covariance, tuple(summaries))


def _trace_point(
    fitted: ModelResult | PenalizedResult,
    observed: np.ndarray[tuple[int], np.dtype[np.float64]],
    *,
    penalty: float,
) -> PenaltyTracePoint:
    if isinstance(fitted, OlsResult):
        residuals = np.asarray(fitted.residuals, dtype=np.float64)
        effective_df = float(fitted.rank)
    elif isinstance(fitted, BinaryLogisticResult):
        residuals = observed - np.asarray(fitted.fitted_probabilities)
        effective_df = float(fitted.rank)
    else:
        residuals = np.asarray(fitted.residuals, dtype=np.float64)
        effective_df = fitted.effective_degrees_of_freedom
    if isinstance(fitted, OlsResult) or (
        isinstance(fitted, PenalizedResult) and fitted.model_type == "ols"
    ):
        mean_squared_error = float(residuals @ residuals) / len(observed)
        if mean_squared_error <= 0.0:
            raise NumericalError("penalty tracing requires positive OLS error")
        deviance = len(observed) * math.log(mean_squared_error)
    else:
        linear = np.asarray(fitted.linear_predictors, dtype=np.float64)
        deviance = -2.0 * float(np.sum(observed * linear - np.logaddexp(0.0, linear)))
    return PenaltyTracePoint(
        penalty=penalty,
        effective_degrees_of_freedom=effective_df,
        deviance=deviance,
        aic=deviance + 2.0 * effective_df,
        bic=deviance + math.log(len(observed)) * effective_df,
        coefficients=fitted.coefficients,
    )


def trace_penalty(
    result: ModelResult,
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    penalties: Iterable[float],
    *,
    criterion: PenaltyCriterion = "aic",
    ols_variance: Literal["simple", "sandwich"] = "simple",
    max_iterations: int = 100,
    tolerance: float = 1e-10,
) -> PenaltyTraceResult:
    """Refit an explicit scalar-penalty grid and select minimum AIC or BIC."""
    if not isinstance(cast(object, result), (OlsResult, BinaryLogisticResult)):
        raise UnsupportedFeatureError("penalty tracing supports OLS and binary lrm")
    if isinstance(result, BinaryLogisticResult) and result.estimator != "lrm":
        raise UnsupportedFeatureError("penalty tracing supports binary lrm, not Glm")
    if criterion not in {"aic", "bic"}:
        raise InputValidationError("criterion must be 'aic' or 'bic'")
    if ols_variance not in {"simple", "sandwich"}:
        raise InputValidationError("ols_variance must be 'simple' or 'sandwich'")
    raw_iterations = cast(object, max_iterations)
    if (
        isinstance(raw_iterations, bool)
        or not isinstance(raw_iterations, Integral)
        or not 1 <= max_iterations <= 10_000
    ):
        raise InputValidationError("max_iterations must be an integer from 1 to 10000")
    normalized_tolerance = _finite(tolerance, name="tolerance")
    if not 0.0 < normalized_tolerance < 1.0:
        raise InputValidationError("tolerance must be between zero and one")
    if isinstance(result, OlsResult) and (
        max_iterations != 100 or normalized_tolerance != 1e-10
    ):
        raise InputValidationError(
            "iterative controls do not apply to OLS penalty tracing"
        )
    if isinstance(result, BinaryLogisticResult) and ols_variance != "simple":
        raise InputValidationError(
            "ols_variance does not apply to binary penalty tracing"
        )
    raw_penalties = tuple(_finite(value, name="penalty") for value in penalties)
    if (
        not raw_penalties
        or len(raw_penalties) > MAX_TRACE_POINTS
        or raw_penalties[0] < 0.0
        or any(
            left >= right
            for left, right in zip(raw_penalties, raw_penalties[1:], strict=False)
        )
    ):
        raise InputValidationError(
            "penalties must be 1-1000 strictly increasing non-negative values"
        )
    design = _analysis_design(result, features)
    observed = _analysis_response(result, response)
    feature_matrix = tuple(
        tuple(float(value) for value in row)
        for row in design[:, int(result.includes_intercept) :]
    )
    names = result.coefficient_names[int(result.includes_intercept) :]
    points: list[PenaltyTracePoint] = []
    for penalty in raw_penalties:
        if penalty == 0.0:
            fitted: ModelResult | PenalizedResult = result
        elif isinstance(result, OlsResult):
            fitted = fit_penalized_ols(
                observed,
                feature_matrix,
                penalty=penalty,
                variance=ols_variance,
                feature_names=names,
                include_intercept=result.includes_intercept,
            )
        else:
            fitted = fit_penalized_lrm(
                observed,
                feature_matrix,
                penalty=penalty,
                feature_names=names,
                include_intercept=result.includes_intercept,
                max_iterations=max_iterations,
                tolerance=normalized_tolerance,
            )
        points.append(_trace_point(fitted, observed, penalty=penalty))
    selected = min(
        points,
        key=lambda point: (getattr(point, criterion), point.penalty),
    )
    return PenaltyTraceResult(
        model_family="ols" if isinstance(result, OlsResult) else "lrm-binary",
        criterion=criterion,
        points=tuple(points),
        selected_penalty=selected.penalty,
    )


def backward_select(
    result: ModelResult,
    response: Iterable[int | float],
    features: Iterable[Iterable[float]] | DesignMatrix,
    terms: Mapping[str, Iterable[str]],
    *,
    significance_level: float = 0.05,
    protected_terms: Iterable[str] = (),
    minimum_terms: int = 1,
    max_iterations: int = 100,
    tolerance: float | None = None,
) -> BackwardSelectionResult:
    """Remove the largest eligible Wald-p term and freshly refit each step."""
    if not isinstance(cast(object, result), (OlsResult, BinaryLogisticResult)):
        raise UnsupportedFeatureError(
            "backward selection supports OLS and binary-logistic results"
        )
    level = _finite(significance_level, name="significance_level")
    if not 0.0 < level < 1.0:
        raise InputValidationError("significance_level must be between zero and one")
    raw_iterations = cast(object, max_iterations)
    if (
        isinstance(raw_iterations, bool)
        or not isinstance(raw_iterations, Integral)
        or not 1 <= max_iterations <= 10_000
    ):
        raise InputValidationError("max_iterations must be an integer from 1 to 10000")
    if isinstance(result, OlsResult) and (
        tolerance is not None or max_iterations != 100
    ):
        raise InputValidationError("iterative controls do not apply to OLS selection")
    if (
        not isinstance(cast(object, terms), Mapping)
        or not 1 <= len(terms) <= MAX_SELECTION_TERMS
    ):
        raise InputValidationError("terms must contain 1-256 declared groups")
    normalized: dict[str, tuple[str, ...]] = {}
    assigned: set[str] = set()
    for term, raw_names in terms.items():
        names = tuple(raw_names)
        if (
            not isinstance(cast(object, term), str)
            or not term
            or not names
            or len(set(names)) != len(names)
            or any(
                not isinstance(cast(object, name), str) or not name for name in names
            )
        ):
            raise InputValidationError("selection term groups are invalid")
        overlap = assigned.intersection(names)
        if overlap:
            raise InputValidationError("selection coefficient groups must not overlap")
        assigned.update(names)
        normalized[term] = names
    slope_names = result.coefficient_names[int(result.includes_intercept) :]
    if assigned != set(slope_names):
        raise InputValidationError(
            "selection term groups must partition every slope coefficient"
        )
    protected = tuple(protected_terms)
    if len(set(protected)) != len(protected) or any(
        term not in normalized for term in protected
    ):
        raise InputValidationError("protected_terms must be unique declared terms")
    raw_minimum = cast(object, minimum_terms)
    if (
        isinstance(raw_minimum, bool)
        or not isinstance(raw_minimum, Integral)
        or not 1 <= minimum_terms <= len(normalized)
        or minimum_terms < len(protected)
    ):
        raise InputValidationError("minimum_terms is outside the supported range")
    if tolerance is not None and not 0.0 < _finite(tolerance, name="tolerance") < 1.0:
        raise InputValidationError("tolerance must be between zero and one")

    design = _analysis_design(result, features)
    observed = _analysis_response(result, response)
    original_features = design[:, int(result.includes_intercept) :]
    original_lookup = {name: index for index, name in enumerate(slope_names)}
    active = list(normalized)
    current: ModelResult = result
    steps: list[SelectionStep] = []

    def refit() -> ModelResult:
        selected_names = tuple(
            name
            for name in slope_names
            if any(name in normalized[term] for term in active)
        )
        indices = tuple(original_lookup[name] for name in selected_names)
        selected_rows = tuple(
            tuple(float(row[index]) for index in indices) for row in original_features
        )
        if isinstance(result, OlsResult):
            return fit_ols(
                observed,
                selected_rows,
                feature_names=selected_names,
                include_intercept=result.includes_intercept,
            )
        normalized_tolerance = (
            (1e-10 if result.estimator == "lrm" else 1e-8)
            if tolerance is None
            else tolerance
        )
        if result.estimator == "lrm":
            return fit_lrm(
                observed,
                selected_rows,
                feature_names=selected_names,
                include_intercept=result.includes_intercept,
                max_iterations=max_iterations,
                tolerance=normalized_tolerance,
            )
        return fit_glm(
            observed,
            selected_rows,
            family="binomial",
            feature_names=selected_names,
            include_intercept=result.includes_intercept,
            max_iterations=max_iterations,
            tolerance=normalized_tolerance,
        )

    while len(active) > minimum_terms:
        groups = {term: normalized[term] for term in active}
        p_values = {test.term: test.p_value for test in anova(current, groups).tests}
        eligible = tuple(term for term in active if term not in protected)
        if not eligible:
            break
        candidate = max(eligible, key=lambda term: (p_values[term], term))
        if p_values[candidate] <= level:
            break
        active.remove(candidate)
        current = refit()
        steps.append(
            SelectionStep(
                step=len(steps) + 1,
                removed_term=candidate,
                p_value=p_values[candidate],
                remaining_terms=tuple(active),
            )
        )
    return BackwardSelectionResult(
        model_family=_model_family(result),
        significance_level=level,
        initial_terms=tuple(normalized),
        selected_terms=tuple(active),
        protected_terms=protected,
        steps=tuple(steps),
        final_model=current,
    )


__all__ = [
    "BackwardSelectionResult",
    "CoefficientRobustness",
    "InfluenceObservation",
    "InfluenceResult",
    "PenaltyTracePoint",
    "PenaltyTraceResult",
    "RobustnessDiagnostics",
    "SelectionStep",
    "VarianceInflationFactor",
    "backward_select",
    "influence_diagnostics",
    "robustness_diagnostics",
    "trace_penalty",
    "variance_inflation_factors",
]
