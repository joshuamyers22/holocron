"""Typed post-estimation operations for supported Holocron model results."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from numbers import Real
from statistics import NormalDist
from typing import Literal, TypeAlias, cast

import numpy as np
import numpy.typing as npt

from holocron.design import DesignMatrix, DesignSpec
from holocron.exceptions import InputValidationError, NumericalError
from holocron.models.linear import OlsResult
from holocron.models.logistic import BinaryLogisticResult

ModelResult: TypeAlias = OlsResult | BinaryLogisticResult
FloatMatrix = npt.NDArray[np.float64]
FloatVector = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class CovarianceResult:
    """A named covariance matrix, optionally restricted to selected terms."""

    coefficient_names: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class LikelihoodResult:
    """Maximized and null likelihood statistics for a fitted model."""

    log_likelihood: float
    null_log_likelihood: float
    parameter_count: int
    aic: float
    likelihood_ratio: float
    degrees_of_freedom: int
    p_value: float


@dataclass(frozen=True, slots=True)
class ResidualResult:
    """A named residual vector in original training-row order."""

    kind: str
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """Predictions with model-based standard errors and confidence limits."""

    scale: Literal["linear", "response"]
    interval: Literal["mean", "individual"]
    confidence_level: float
    values: tuple[float, ...]
    standard_errors: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class InferenceEstimate:
    """One estimate with a Wald statistic, p-value, and confidence interval."""

    name: str
    estimate: float
    standard_error: float
    statistic: float
    distribution: Literal["normal", "t"]
    degrees_of_freedom: int | None
    p_value: float
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class ModelSummary:
    """Coefficient-level inference and likelihood metadata for one model."""

    model_type: Literal["ols", "glm-binomial", "lrm-binary"]
    n_observations: int
    rank: int
    confidence_level: float
    coefficients: tuple[InferenceEstimate, ...]
    likelihood: LikelihoodResult


@dataclass(frozen=True, slots=True)
class AnovaTest:
    """One joint Wald test over a declared formula term."""

    term: str
    coefficient_names: tuple[str, ...]
    statistic: float
    distribution: Literal["chi-square", "f"]
    degrees_of_freedom: int
    denominator_degrees_of_freedom: int | None
    p_value: float


@dataclass(frozen=True, slots=True)
class AnovaResult:
    """Joint Wald tests in stable formula-term order."""

    tests: tuple[AnovaTest, ...]


def _confidence_level(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(float(value))
        or not 0.0 < float(value) < 1.0
    ):
        raise InputValidationError("confidence_level must be between 0 and 1")
    return float(value)


def _regularized_beta(x: float, a: float, b: float) -> float:
    if not 0.0 <= x <= 1.0 or a <= 0.0 or b <= 0.0:
        raise NumericalError("invalid incomplete-beta arguments")
    if x in {0.0, 1.0}:
        return x

    def fraction(x_value: float, left: float, right: float) -> float:
        tiny = 1e-300
        qab = left + right
        qap = left + 1.0
        qam = left - 1.0
        c = 1.0
        d = 1.0 - qab * x_value / qap
        d = 1.0 / max(abs(d), tiny) * (1.0 if d >= 0.0 else -1.0)
        result = d
        for iteration in range(1, 401):
            even = 2 * iteration
            numerator = (
                iteration
                * (right - iteration)
                * x_value
                / ((qam + even) * (left + even))
            )
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            result *= d * c
            numerator = -(
                (left + iteration)
                * (qab + iteration)
                * x_value
                / ((left + even) * (qap + even))
            )
            d = 1.0 + numerator * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + numerator / c
            c = c if abs(c) > tiny else tiny
            change = d * c
            result *= change
            if abs(change - 1.0) <= 3e-14:
                return result
        raise NumericalError("incomplete-beta evaluation did not converge")

    scale = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return scale * fraction(x, a, b) / a
    return 1.0 - scale * fraction(1.0 - x, b, a) / b


def _regularized_gamma_q(a: float, x: float) -> float:
    if a <= 0.0 or x < 0.0:
        raise NumericalError("invalid incomplete-gamma arguments")
    if x == 0.0:
        return 1.0
    epsilon = 3e-14
    if x < a + 1.0:
        term = 1.0 / a
        total = term
        shifted = a
        for _ in range(1, 1001):
            shifted += 1.0
            term *= x / shifted
            total += term
            if abs(term) <= abs(total) * epsilon:
                p_value = total * math.exp(-x + a * math.log(x) - math.lgamma(a))
                return max(0.0, min(1.0, 1.0 - p_value))
        raise NumericalError("incomplete-gamma series did not converge")
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    result = d
    for iteration in range(1, 1001):
        numerator = -iteration * (iteration - a)
        b += 2.0
        d = numerator * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + numerator / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        change = d * c
        result *= change
        if abs(change - 1.0) <= epsilon:
            q_value = math.exp(-x + a * math.log(x) - math.lgamma(a)) * result
            return max(0.0, min(1.0, q_value))
    raise NumericalError("incomplete-gamma fraction did not converge")


def _student_cdf(value: float, degrees_of_freedom: int) -> float:
    x = degrees_of_freedom / (degrees_of_freedom + value * value)
    tail = 0.5 * _regularized_beta(x, degrees_of_freedom / 2.0, 0.5)
    return 1.0 - tail if value >= 0.0 else tail


def _student_quantile(probability: float, degrees_of_freedom: int) -> float:
    if probability == 0.5:
        return 0.0
    if probability < 0.5:
        return -_student_quantile(1.0 - probability, degrees_of_freedom)
    lower = 0.0
    upper = max(1.0, NormalDist().inv_cdf(probability))
    while _student_cdf(upper, degrees_of_freedom) < probability:
        upper *= 2.0
        if upper > 1e12:
            raise NumericalError("Student t quantile could not be bounded")
    for _ in range(100):
        midpoint = (lower + upper) * 0.5
        if _student_cdf(midpoint, degrees_of_freedom) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) * 0.5


def _normal_two_sided(statistic: float) -> float:
    return math.erfc(abs(statistic) / math.sqrt(2.0))


def _student_two_sided(statistic: float, degrees_of_freedom: int) -> float:
    x = degrees_of_freedom / (degrees_of_freedom + statistic * statistic)
    return _regularized_beta(
        x,
        degrees_of_freedom / 2.0,
        0.5,
    )


def _critical_value(result: ModelResult, confidence_level: float) -> float:
    probability = 0.5 + confidence_level / 2.0
    if isinstance(result, OlsResult):
        return _student_quantile(probability, result.residual_degrees_of_freedom)
    if result.estimator == "glm":
        return _student_quantile(probability, result.n_observations - result.rank)
    return NormalDist().inv_cdf(probability)


def _coefficient_indices(
    result: ModelResult, names: Iterable[str] | None
) -> tuple[int, ...]:
    if names is None:
        return tuple(range(len(result.coefficient_names)))
    requested = tuple(names)
    if not requested or len(set(requested)) != len(requested):
        raise InputValidationError("coefficient selection must be non-empty and unique")
    lookup = {name: index for index, name in enumerate(result.coefficient_names)}
    unknown = [name for name in requested if name not in lookup]
    if unknown:
        raise InputValidationError(f"unknown coefficients: {', '.join(unknown)}")
    return tuple(lookup[name] for name in requested)


def covariance(
    result: ModelResult, names: Iterable[str] | None = None
) -> CovarianceResult:
    """Return the full covariance matrix or a named principal submatrix."""
    indices = _coefficient_indices(result, names)
    return CovarianceResult(
        coefficient_names=tuple(result.coefficient_names[index] for index in indices),
        matrix=tuple(
            tuple(result.covariance[row][column] for column in indices)
            for row in indices
        ),
    )


def _normal_log_likelihood(residual_sum_of_squares: float, count: int) -> float:
    if residual_sum_of_squares <= 0.0:
        raise NumericalError("Gaussian likelihood requires positive residual variance")
    return (
        -0.5
        * count
        * (math.log(2.0 * math.pi) + 1.0 + math.log(residual_sum_of_squares / count))
    )


def likelihood(result: ModelResult) -> LikelihoodResult:
    """Return maximized/null log likelihood, AIC, and the model LR test."""
    if isinstance(result, OlsResult):
        response = tuple(
            fitted + residual
            for fitted, residual in zip(
                result.fitted_values, result.residuals, strict=True
            )
        )
        residual_sum = sum(value * value for value in result.residuals)
        if result.includes_intercept:
            center = sum(response) / len(response)
            null_sum = sum((value - center) ** 2 for value in response)
            null_parameters = 2
        else:
            null_sum = sum(value * value for value in response)
            null_parameters = 1
        fitted_log_likelihood = _normal_log_likelihood(
            residual_sum, result.n_observations
        )
        null_log_likelihood = _normal_log_likelihood(null_sum, result.n_observations)
        parameter_count = result.rank + 1
    else:
        fitted_log_likelihood = -0.5 * result.deviance[1]
        null_log_likelihood = -0.5 * result.deviance[0]
        parameter_count = result.rank
        null_parameters = 1 if result.includes_intercept else 0
    degrees_of_freedom = parameter_count - null_parameters
    likelihood_ratio = max(0.0, 2.0 * (fitted_log_likelihood - null_log_likelihood))
    p_value = (
        _regularized_gamma_q(degrees_of_freedom / 2.0, likelihood_ratio / 2.0)
        if degrees_of_freedom > 0
        else 1.0
    )
    return LikelihoodResult(
        log_likelihood=fitted_log_likelihood,
        null_log_likelihood=null_log_likelihood,
        parameter_count=parameter_count,
        aic=2.0 * parameter_count - 2.0 * fitted_log_likelihood,
        likelihood_ratio=likelihood_ratio,
        degrees_of_freedom=degrees_of_freedom,
        p_value=p_value,
    )


def _binary_response(
    response: Iterable[int | float] | None, expected_count: int
) -> FloatVector:
    if response is None:
        raise InputValidationError(
            "binary residuals require the original response explicitly"
        )
    values = tuple(response)
    if len(values) != expected_count:
        raise InputValidationError("response must match the fitted observation count")
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or float(value) not in {0.0, 1.0}
        for value in values
    ):
        raise InputValidationError("binary response must contain only numeric 0 and 1")
    return np.asarray(values, dtype=np.float64)


def residuals(
    result: ModelResult,
    *,
    kind: Literal["ordinary", "standardized", "pearson", "deviance"] = "ordinary",
    response: Iterable[int | float] | None = None,
) -> ResidualResult:
    """Compute supported training residuals without reconstructing hidden inputs.

    Binary results deliberately do not persist the training response, so callers
    must provide it explicitly. OLS supports ordinary and standardized residuals;
    binary models support ordinary, Pearson, and deviance residuals.
    """
    if isinstance(result, OlsResult):
        if response is not None:
            raise InputValidationError("OLS residuals already retain their response")
        if kind == "ordinary":
            values = result.residuals
        elif kind == "standardized":
            if result.residual_scale == 0.0:
                raise NumericalError("standardized residuals require positive scale")
            values = tuple(value / result.residual_scale for value in result.residuals)
        else:
            raise InputValidationError(
                "OLS residual kind must be 'ordinary' or 'standardized'"
            )
        return ResidualResult(kind=kind, values=values)

    if kind == "standardized":
        raise InputValidationError(
            "binary residual kind must be 'ordinary', 'pearson', or 'deviance'"
        )
    observed = _binary_response(response, result.n_observations)
    probability = np.asarray(result.fitted_probabilities, dtype=np.float64)
    if any(float(value) <= 0.0 or float(value) >= 1.0 for value in probability):
        raise NumericalError("binary residuals require probabilities inside (0, 1)")
    ordinary = observed - probability
    if kind == "ordinary":
        computed = ordinary
    elif kind == "pearson":
        computed = ordinary / np.sqrt(probability * (1.0 - probability))
    else:
        contribution = np.where(  # pyright: ignore[reportUnknownMemberType]
            observed == 1.0,
            -2.0 * np.log(probability),
            -2.0 * np.log1p(-probability),
        )
        computed = np.copysign(np.sqrt(contribution), ordinary)
    return ResidualResult(kind=kind, values=tuple(float(value) for value in computed))


def _prediction_matrix(
    result: ModelResult, features: Iterable[Iterable[float]] | DesignMatrix
) -> FloatMatrix:
    if isinstance(features, DesignMatrix):
        if (
            result.design_fingerprint is not None
            and features.specification_fingerprint != result.design_fingerprint
        ):
            raise InputValidationError(
                "prediction design fingerprint differs from the fitted design"
            )
        values: Iterable[Iterable[float]] = features.rows
    else:
        values = features
    try:
        rows = tuple(tuple(float(value) for value in row) for row in values)
    except (TypeError, ValueError) as error:
        raise InputValidationError("prediction features must be numeric") from error
    if not rows or any(len(row) != result.n_features for row in rows):
        raise InputValidationError(
            f"prediction features must have {result.n_features} columns"
        )
    if not all(math.isfinite(value) for row in rows for value in row):
        raise InputValidationError("prediction features must be finite")
    matrix = np.asarray(rows, dtype=np.float64)
    if result.includes_intercept:
        matrix = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (np.ones(matrix.shape[0], dtype=np.float64), matrix)
        )
    return matrix


def _expit(values: FloatVector) -> FloatVector:
    output = np.empty_like(values)
    positive = values >= 0.0
    output[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponential = np.exp(values[~positive])
    output[~positive] = exponential / (1.0 + exponential)
    return output


def predict(
    result: ModelResult,
    features: Iterable[Iterable[float]] | DesignMatrix,
    *,
    scale: Literal["linear", "response"] = "response",
    interval: Literal["mean", "individual"] = "mean",
    confidence_level: float = 0.95,
) -> PredictionResult:
    """Predict with covariance-based standard errors and confidence limits."""
    level = _confidence_level(confidence_level)
    if scale not in {"linear", "response"}:
        raise InputValidationError("prediction scale must be 'linear' or 'response'")
    if interval not in {"mean", "individual"}:
        raise InputValidationError("prediction interval must be 'mean' or 'individual'")
    if isinstance(result, BinaryLogisticResult) and interval != "mean":
        raise InputValidationError("binary prediction supports mean intervals only")
    design = _prediction_matrix(result, features)
    coefficients = np.asarray(result.coefficients, dtype=np.float64)
    covariance_matrix = np.asarray(result.covariance, dtype=np.float64)
    linear = design @ coefficients
    variances = np.einsum("ij,jk,ik->i", design, covariance_matrix, design)
    if isinstance(result, OlsResult) and interval == "individual":
        variances = variances + result.residual_scale**2
    if min(float(value) for value in variances) < -1e-12:
        raise NumericalError("prediction variance is negative")
    linear_se = np.sqrt(np.maximum(variances, 0.0))
    critical = _critical_value(result, level)
    lower_linear = linear - critical * linear_se
    upper_linear = linear + critical * linear_se
    if isinstance(result, BinaryLogisticResult) and scale == "response":
        values = _expit(linear)
        lower = _expit(lower_linear)
        upper = _expit(upper_linear)
        standard_errors = linear_se * values * (1.0 - values)
    else:
        values = linear
        lower = lower_linear
        upper = upper_linear
        standard_errors = linear_se
    return PredictionResult(
        scale=scale,
        interval=interval,
        confidence_level=level,
        values=tuple(float(value) for value in values),
        standard_errors=tuple(float(value) for value in standard_errors),
        lower=tuple(float(value) for value in lower),
        upper=tuple(float(value) for value in upper),
    )


def _inference_estimate(
    result: ModelResult,
    *,
    name: str,
    estimate: float,
    variance: float,
    confidence_level: float,
) -> InferenceEstimate:
    if variance < 0.0:
        raise NumericalError("inference variance must not be negative")
    standard_error = math.sqrt(variance)
    if standard_error == 0.0:
        raise NumericalError("inference requires a positive standard error")
    statistic = estimate / standard_error
    critical = _critical_value(result, confidence_level)
    if isinstance(result, OlsResult) or result.estimator == "glm":
        degrees_of_freedom: int | None = (
            result.residual_degrees_of_freedom
            if isinstance(result, OlsResult)
            else result.n_observations - result.rank
        )
        distribution: Literal["normal", "t"] = "t"
        p_value = _student_two_sided(statistic, degrees_of_freedom)
    else:
        degrees_of_freedom = None
        distribution = "normal"
        p_value = _normal_two_sided(statistic)
    return InferenceEstimate(
        name=name,
        estimate=estimate,
        standard_error=standard_error,
        statistic=statistic,
        distribution=distribution,
        degrees_of_freedom=degrees_of_freedom,
        p_value=max(0.0, min(1.0, p_value)),
        lower=estimate - critical * standard_error,
        upper=estimate + critical * standard_error,
    )


def summarize(result: ModelResult, *, confidence_level: float = 0.95) -> ModelSummary:
    """Summarize coefficient-level inference for a supported fitted model."""
    level = _confidence_level(confidence_level)
    estimates = tuple(
        _inference_estimate(
            result,
            name=name,
            estimate=result.coefficients[index],
            variance=result.covariance[index][index],
            confidence_level=level,
        )
        for index, name in enumerate(result.coefficient_names)
    )
    model_type: Literal["ols", "glm-binomial", "lrm-binary"]
    if isinstance(result, OlsResult):
        model_type = "ols"
    elif result.estimator == "glm":
        model_type = "glm-binomial"
    else:
        model_type = "lrm-binary"
    return ModelSummary(
        model_type=model_type,
        n_observations=result.n_observations,
        rank=result.rank,
        confidence_level=level,
        coefficients=estimates,
        likelihood=likelihood(result),
    )


def contrast(
    result: ModelResult,
    weights: Mapping[str, float] | Iterable[float],
    *,
    name: str = "contrast",
    confidence_level: float = 0.95,
) -> InferenceEstimate:
    """Evaluate one linear coefficient contrast with model-based uncertainty."""
    level = _confidence_level(confidence_level)
    if not name:
        raise InputValidationError("contrast name must not be empty")
    if isinstance(weights, Mapping):
        named_weights = cast(Mapping[str, float], weights)
        unknown = sorted(set(named_weights) - set(result.coefficient_names))
        if unknown:
            raise InputValidationError(f"unknown coefficients: {', '.join(unknown)}")
        raw_weights = tuple(
            float(named_weights.get(item, 0.0)) for item in result.coefficient_names
        )
    else:
        raw_weights = tuple(float(value) for value in weights)
    if len(raw_weights) != len(result.coefficients):
        raise InputValidationError("contrast weights must match the coefficient count")
    if not all(math.isfinite(value) for value in raw_weights):
        raise InputValidationError("contrast weights must be finite")
    if not any(value != 0.0 for value in raw_weights):
        raise InputValidationError("contrast weights must not all be zero")
    vector = np.asarray(raw_weights, dtype=np.float64)
    coefficients = np.asarray(result.coefficients, dtype=np.float64)
    covariance_matrix = np.asarray(result.covariance, dtype=np.float64)
    estimate = float(vector @ coefficients)
    variance = float(vector @ covariance_matrix @ vector)
    return _inference_estimate(
        result,
        name=name,
        estimate=estimate,
        variance=max(0.0, variance),
        confidence_level=level,
    )


def _joint_test(
    result: ModelResult,
    *,
    term: str,
    indices: tuple[int, ...],
) -> AnovaTest:
    coefficients = np.asarray(
        tuple(result.coefficients[index] for index in indices), dtype=np.float64
    )
    covariance_matrix = np.asarray(
        tuple(
            tuple(result.covariance[row][column] for column in indices)
            for row in indices
        ),
        dtype=np.float64,
    )
    try:
        wald = float(coefficients @ np.linalg.solve(covariance_matrix, coefficients))
    except np.linalg.LinAlgError as error:
        raise NumericalError("ANOVA covariance block is singular") from error
    degrees_of_freedom = len(indices)
    if isinstance(result, OlsResult):
        statistic = wald / degrees_of_freedom
        denominator = result.residual_degrees_of_freedom
        x = denominator / (denominator + degrees_of_freedom * statistic)
        p_value = _regularized_beta(x, denominator / 2.0, degrees_of_freedom / 2.0)
        distribution: Literal["chi-square", "f"] = "f"
    else:
        statistic = wald
        denominator = None
        p_value = _regularized_gamma_q(degrees_of_freedom / 2.0, statistic / 2.0)
        distribution = "chi-square"
    return AnovaTest(
        term=term,
        coefficient_names=tuple(result.coefficient_names[index] for index in indices),
        statistic=max(0.0, statistic),
        distribution=distribution,
        degrees_of_freedom=degrees_of_freedom,
        denominator_degrees_of_freedom=denominator,
        p_value=max(0.0, min(1.0, p_value)),
    )


def anova(
    result: ModelResult,
    terms: DesignSpec | Mapping[str, Iterable[str]],
) -> AnovaResult:
    """Compute joint Wald tests from a design specification or explicit groups."""
    if isinstance(terms, DesignSpec):
        if result.design_fingerprint is None:
            raise InputValidationError("ANOVA requires a fit made from a DesignMatrix")
        if terms.fingerprint != result.design_fingerprint:
            raise InputValidationError(
                "ANOVA specification differs from the fitted design"
            )
        if len(terms.columns) != result.n_features:
            raise InputValidationError("ANOVA specification width differs from the fit")
        offset = int(result.includes_intercept)
        groups = tuple(
            (
                term.expression,
                tuple(range(offset + start, offset + stop)),
            )
            for term, (start, stop) in zip(
                terms.formula.terms, terms.term_slices, strict=True
            )
        )
    else:
        if not terms:
            raise InputValidationError("ANOVA term groups must not be empty")
        lookup = {name: index for index, name in enumerate(result.coefficient_names)}
        groups_list: list[tuple[str, tuple[int, ...]]] = []
        assigned: set[str] = set()
        for term, names in terms.items():
            selected = tuple(names)
            if not term or not selected or len(set(selected)) != len(selected):
                raise InputValidationError(
                    "ANOVA groups require named, non-empty, unique coefficients"
                )
            unknown = [name for name in selected if name not in lookup]
            if unknown:
                raise InputValidationError(
                    f"unknown ANOVA coefficients: {', '.join(unknown)}"
                )
            overlap = assigned.intersection(selected)
            if overlap:
                overlap_names = ", ".join(sorted(overlap))
                raise InputValidationError(
                    f"ANOVA coefficients occur in multiple groups: {overlap_names}"
                )
            if result.includes_intercept and "Intercept" in selected:
                raise InputValidationError(
                    "ANOVA term groups must exclude the intercept"
                )
            assigned.update(selected)
            groups_list.append((term, tuple(lookup[name] for name in selected)))
        groups = tuple(groups_list)
    tests = tuple(
        _joint_test(result, term=term, indices=indices) for term, indices in groups
    )
    return AnovaResult(tests=tests)


__all__ = [
    "AnovaResult",
    "AnovaTest",
    "CovarianceResult",
    "InferenceEstimate",
    "LikelihoodResult",
    "ModelSummary",
    "PredictionResult",
    "ResidualResult",
    "anova",
    "contrast",
    "covariance",
    "likelihood",
    "predict",
    "residuals",
    "summarize",
]
