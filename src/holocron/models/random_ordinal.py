"""Clustered cumulative-link models with escalating adaptive quadrature."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import math
from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass
from typing import cast

import numpy as np

from holocron.design import DesignMatrix
from holocron.exceptions import ConvergenceError, InputValidationError, NumericalError
from holocron.models.ordinal import (
    MAX_PARAMETERS,
    CensoredResponse,
    FloatMatrix,
    FloatVector,
    IntVector,
    OrdinalFamily,
    OrdinalResult,
    _as_feature_matrix,
    _family_values,
    _feature_names,
    _finite_number,
    _fit_parameters,
    _probability_rows,
    _response_contract,
)


@dataclass(frozen=True, slots=True)
class VarianceComponentTest:
    """Boundary-aware likelihood-ratio test for ordinal random effects."""

    statistic: float
    mixture: str
    p_value: float


@dataclass(frozen=True, slots=True)
class RandomEffectsOrdinalResult:
    """Marginal ordinal fit with one cluster-level Gaussian random effect."""

    fixed: OrdinalResult
    sigma: float | None
    sigma1: float | None
    sigma2: float | None
    cluster_count: int
    cluster_modes: tuple[float, ...]
    log_likelihood: float
    clustered_null_log_likelihood: float
    quadrature_points: int
    quadrature_history: tuple[tuple[int, float], ...]
    parameter_names: tuple[str, ...]
    covariance: tuple[tuple[float, ...], ...]
    variance_component_test: VarianceComponentTest

    def __post_init__(self) -> None:
        if self.cluster_count < 2 or len(self.cluster_modes) != self.cluster_count:
            raise InputValidationError("random-effect cluster metadata is invalid")
        if self.sigma is not None:
            if self.sigma1 is not None or self.sigma2 is not None or self.sigma <= 0.0:
                raise InputValidationError("plain random-effect scales are invalid")
        elif self.sigma1 is None or self.sigma2 is None or self.sigma1 <= 0.0:
            raise InputValidationError("weighted random-effect scales are invalid")
        numeric = (
            *self.cluster_modes,
            self.log_likelihood,
            self.clustered_null_log_likelihood,
            self.variance_component_test.statistic,
            self.variance_component_test.p_value,
        )
        if any(not _finite_number(value) for value in numeric):
            raise InputValidationError(
                "random-effect result contains non-finite values"
            )
        if len(self.parameter_names) != len(self.covariance) or any(
            len(row) != len(self.parameter_names) for row in self.covariance
        ):
            raise InputValidationError(
                "random-effect covariance dimensions are invalid"
            )


def _cluster_codes(
    values: Iterable[Hashable],
) -> tuple[IntVector, tuple[Hashable, ...]]:
    items = tuple(values)
    if not items:
        raise InputValidationError("clusters must not be empty")
    levels: list[Hashable] = []
    mapping: dict[Hashable, int] = {}
    codes: list[int] = []
    for item in items:
        if item not in mapping:
            mapping[item] = len(levels)
            levels.append(item)
        codes.append(mapping[item])
    if len(levels) < 2:
        raise InputValidationError(
            "random-intercept models require at least two clusters"
        )
    return np.asarray(codes, dtype=np.int64), tuple(levels)


def _probability_derivatives(
    thresholds: FloatVector,
    predictor: float,
    start: int,
    stop: int,
    family: OrdinalFamily,
) -> tuple[float, float, float]:
    upper_probability = 1.0
    lower_probability = 0.0
    first = 0.0
    second = 0.0
    if start > 0:
        values = _family_values(np.asarray([thresholds[start - 1] + predictor]), family)
        upper_probability = float(values[0][0])
        first += float(values[1][0])
        second += float(values[2][0])
    if stop < thresholds.size:
        values = _family_values(np.asarray([thresholds[stop] + predictor]), family)
        lower_probability = float(values[0][0])
        first -= float(values[1][0])
        second -= float(values[2][0])
    probability = upper_probability - lower_probability
    return probability, first, second


def _cluster_mode(
    thresholds: FloatVector,
    fixed_predictor: FloatVector,
    scales: FloatVector,
    first: IntVector,
    last: IntVector,
    family: OrdinalFamily,
    initial: float = 0.0,
) -> tuple[float, float]:
    mode = initial
    for _ in range(80):
        score = -mode
        hessian = -1.0
        for predictor, scale, start, stop in zip(
            fixed_predictor, scales, first, last, strict=True
        ):
            probability, derivative, second = _probability_derivatives(
                thresholds,
                float(predictor + scale * mode),
                int(start),
                int(stop),
                family,
            )
            if probability <= 1e-300:
                raise NumericalError("cluster likelihood probability became zero")
            ratio = derivative / probability
            score += float(scale) * ratio
            hessian += float(scale * scale) * (second / probability - ratio * ratio)
        if not math.isfinite(hessian) or hessian >= -1e-10:
            raise NumericalError("cluster posterior curvature is not negative")
        step = score / -hessian
        candidate = mode + step
        if not math.isfinite(candidate):
            raise NumericalError("cluster mode is not finite")
        mode = candidate
        if abs(step) <= 1e-10 * (1.0 + abs(mode)):
            return mode, -hessian
    raise ConvergenceError("cluster posterior mode did not converge")


def _cluster_log_integral(
    thresholds: FloatVector,
    predictor: FloatVector,
    scales: FloatVector,
    first: IntVector,
    last: IntVector,
    family: OrdinalFamily,
    nodes: FloatVector,
    weights: FloatVector,
) -> tuple[float, float]:
    mode, curvature = _cluster_mode(thresholds, predictor, scales, first, last, family)
    transformed = mode + math.sqrt(2.0 / curvature) * nodes
    log_terms = np.empty(nodes.size, dtype=np.float64)
    for node_index, random_value in enumerate(transformed):
        value = -0.5 * float(random_value * random_value)
        for fixed, scale, start, stop in zip(
            predictor, scales, first, last, strict=True
        ):
            probability, _, _ = _probability_derivatives(
                thresholds,
                float(fixed + scale * random_value),
                int(start),
                int(stop),
                family,
            )
            if probability <= 1e-300:
                value = -math.inf
                break
            value += math.log(probability)
        log_terms[node_index] = (
            math.log(float(weights[node_index])) + value + float(nodes[node_index] ** 2)
        )
    maximum = float(np.max(log_terms))
    if not math.isfinite(maximum):
        raise NumericalError("adaptive quadrature has no finite node")
    log_integral = (
        maximum
        + math.log(float(np.sum(np.exp(log_terms - maximum))))
        - 0.5 * math.log(math.pi * curvature)
    )
    return log_integral, mode


def _marginal_log_likelihood(
    parameters: FloatVector,
    features: FloatMatrix,
    first: IntVector,
    last: IntVector,
    codes: IntVector,
    family: OrdinalFamily,
    threshold_count: int,
    mre: FloatVector | None,
    quadrature_points: int,
) -> tuple[float, tuple[float, ...]]:
    thresholds = parameters[:threshold_count]
    if bool((thresholds[:-1] <= thresholds[1:]).any()):
        return -math.inf, ()
    slope_stop = parameters.size - (2 if mre is not None else 1)
    slopes = parameters[threshold_count:slope_stop]
    if mre is None:
        scale = math.exp(float(parameters[-1]))
        if not 1e-7 <= scale <= 100.0:
            return -math.inf, ()
        all_scales = np.full(features.shape[0], scale)
    else:
        sigma1 = math.exp(float(parameters[-2]))
        sigma2 = float(parameters[-1])
        if not 1e-7 <= sigma1 <= 100.0 or abs(sigma2) > 100.0:
            return -math.inf, ()
        all_scales = sigma1 * (1.0 - mre) + sigma2 * mre
    fixed = features @ slopes
    raw_nodes, raw_weights = np.polynomial.hermite.hermgauss(quadrature_points)
    nodes = cast(FloatVector, raw_nodes.astype(np.float64))
    weights = cast(FloatVector, raw_weights.astype(np.float64))
    total = 0.0
    modes: list[float] = []
    for code in range(int(np.max(codes)) + 1):
        selected = codes == code
        try:
            contribution, mode = _cluster_log_integral(
                thresholds,
                fixed[selected],
                all_scales[selected],
                first[selected],
                last[selected],
                family,
                nodes,
                weights,
            )
        except (ConvergenceError, NumericalError):
            return -math.inf, ()
        total += contribution
        modes.append(mode)
    return total, tuple(modes)


def _numerical_gradient(
    objective: Callable[[FloatVector], float],
    parameters: FloatVector,
) -> FloatVector:
    gradient = np.empty(parameters.size, dtype=np.float64)
    for index in range(parameters.size):
        step = 2e-5 * (1.0 + abs(float(parameters[index])))
        plus = parameters.copy()
        minus = parameters.copy()
        plus[index] += step
        minus[index] -= step
        upper = objective(plus)
        lower = objective(minus)
        if not math.isfinite(upper) or not math.isfinite(lower):
            gradient[index] = 0.0
        else:
            gradient[index] = (upper - lower) / (2.0 * step)
    return gradient


def _numerical_information(
    objective: Callable[[FloatVector], float], parameters: FloatVector
) -> FloatMatrix:
    """Compute the symmetric observed information for a scalar log likelihood."""
    count = parameters.size
    information = np.empty((count, count), dtype=np.float64)
    center = objective(parameters)
    if not math.isfinite(center):
        raise NumericalError("likelihood is not finite at the covariance solution")
    steps = 1e-4 * (1.0 + np.abs(parameters))
    for row in range(count):
        plus = parameters.copy()
        minus = parameters.copy()
        plus[row] += steps[row]
        minus[row] -= steps[row]
        upper = objective(plus)
        lower = objective(minus)
        if not math.isfinite(upper) or not math.isfinite(lower):
            raise NumericalError(
                "likelihood is not finite around the covariance solution"
            )
        information[row, row] = -(upper - 2.0 * center + lower) / (
            steps[row] * steps[row]
        )
        for column in range(row):
            plus_plus = parameters.copy()
            plus_minus = parameters.copy()
            minus_plus = parameters.copy()
            minus_minus = parameters.copy()
            plus_plus[row] += steps[row]
            plus_plus[column] += steps[column]
            plus_minus[row] += steps[row]
            plus_minus[column] -= steps[column]
            minus_plus[row] -= steps[row]
            minus_plus[column] += steps[column]
            minus_minus[row] -= steps[row]
            minus_minus[column] -= steps[column]
            values = tuple(
                objective(candidate)
                for candidate in (plus_plus, plus_minus, minus_plus, minus_minus)
            )
            if any(not math.isfinite(value) for value in values):
                raise NumericalError(
                    "likelihood is not finite around the covariance solution"
                )
            value = -(values[0] - values[1] - values[2] + values[3]) / (
                4.0 * steps[row] * steps[column]
            )
            information[row, column] = value
            information[column, row] = value
    return information


def _bfgs_maximize(
    objective: Callable[[FloatVector], float],
    initial: FloatVector,
    *,
    max_iterations: int,
    tolerance: float,
) -> tuple[FloatVector, float, int]:
    parameters = initial.copy()
    value = objective(parameters)
    if not math.isfinite(value):
        raise NumericalError("random-effect likelihood is not finite at initialization")
    gradient = _numerical_gradient(objective, parameters)
    inverse_information = np.eye(parameters.size, dtype=np.float64)
    for iteration in range(1, max_iterations + 1):
        if float(np.max(np.abs(gradient))) <= tolerance:
            return parameters, value, iteration
        direction = np.asarray(inverse_information @ gradient, dtype=np.float64)
        if float(direction @ gradient) <= 0.0:
            direction = gradient
            inverse_information = np.eye(parameters.size, dtype=np.float64)
        scale = 1.0
        accepted = False
        candidate = parameters
        candidate_value = value
        for _ in range(60):
            candidate = parameters + scale * direction
            candidate_value = objective(candidate)
            if math.isfinite(
                candidate_value
            ) and candidate_value >= value + 1e-4 * scale * float(gradient @ direction):
                accepted = True
                break
            scale *= 0.5
        if not accepted:
            if float(np.max(np.abs(gradient))) <= tolerance * 10.0:
                return parameters, value, iteration
            raise ConvergenceError("random-effect likelihood line search failed")
        candidate_gradient = _numerical_gradient(objective, candidate)
        displacement = candidate - parameters
        gradient_change = candidate_gradient - gradient
        curvature = float(displacement @ gradient_change)
        if curvature < -1e-12:
            rho = -1.0 / curvature
            identity = np.eye(parameters.size)
            left = identity + rho * np.outer(displacement, gradient_change)
            right = identity + rho * np.outer(gradient_change, displacement)
            inverse_information = left @ inverse_information @ right + rho * np.outer(
                displacement, displacement
            )
        else:
            inverse_information = np.eye(parameters.size, dtype=np.float64)
        parameters = candidate
        value = candidate_value
        gradient = candidate_gradient
    raise ConvergenceError(
        f"random-effect fit did not converge in {max_iterations} iterations"
    )


def _chi_square_one_survival(statistic: float) -> float:
    return math.erfc(math.sqrt(max(statistic, 0.0) / 2.0))


def _variance_test(
    full: float, fixed: float, *, weighted: bool
) -> VarianceComponentTest:
    statistic = max(0.0, 2.0 * (full - fixed))
    one = _chi_square_one_survival(statistic)
    if weighted:
        probability = 0.5 * (one + math.exp(-statistic / 2.0))
        mixture = "0.5*chi2(1)+0.5*chi2(2)"
    else:
        probability = 0.5 * one if statistic > 0.0 else 1.0
        mixture = "0.5*chi2(0)+0.5*chi2(1)"
    return VarianceComponentTest(statistic, mixture, probability)


def fit_random_intercept_orm(
    response: Iterable[int | float] | CensoredResponse,
    features: Iterable[Iterable[float]] | DesignMatrix,
    clusters: Iterable[Hashable],
    *,
    family: OrdinalFamily = "logistic",
    feature_names: Iterable[str] | None = None,
    design_fingerprint: str | None = None,
    mix_re: Iterable[float] | None = None,
    quadrature_grid: Iterable[int] = (7, 11, 15, 21, 31, 45, 63),
    quadrature_tolerance: float = 1e-6,
    max_iterations: int = 80,
    tolerance: float = 1e-6,
) -> RandomEffectsOrdinalResult:
    """Fit a single random-intercept ORM with escalating adaptive quadrature."""
    levels, first, last, censored = _response_contract(response)
    codes, cluster_levels = _cluster_codes(clusters)
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
    if matrix.shape[0] != first.size or codes.size != first.size:
        raise InputValidationError(
            "response, features, and clusters must have equal length"
        )
    if (
        matrix.shape[1] + len(levels) + (1 if mix_re is not None else 0)
        > MAX_PARAMETERS
    ):
        raise InputValidationError(
            "random-effect ordinal fit exceeds the parameter limit"
        )
    names = _feature_names(matrix.shape[1], feature_names)
    raw_grid = tuple(quadrature_grid)
    if (
        not raw_grid
        or any(
            isinstance(value, bool) or value < 3 or value > 127 or value % 2 == 0
            for value in raw_grid
        )
        or any(
            left >= right for left, right in zip(raw_grid, raw_grid[1:], strict=False)
        )
    ):
        raise InputValidationError(
            "quadrature_grid must contain increasing odd integers from 3 to 127"
        )
    mre_values: FloatVector | None = None
    if mix_re is not None:
        raw_mre = tuple(mix_re)
        if len(raw_mre) != first.size or any(
            not _finite_number(value) for value in raw_mre
        ):
            raise InputValidationError(
                "mix_re must be finite and match the observations"
            )
        mre_values = np.asarray(raw_mre, dtype=np.float64)
        if not any(
            len(set(float(value) for value in mre_values[codes == code])) > 1
            for code in range(len(cluster_levels))
        ):
            raise InputValidationError("mix_re must vary within at least one cluster")

    fixed_parameters, _, fixed_iterations, fixed_log_likelihood = _fit_parameters(
        matrix,
        first,
        last,
        len(levels),
        family,
        max_iterations=max_iterations,
        tolerance=min(tolerance, 1e-8),
    )
    threshold_count = len(levels) - 1
    scale_start = (math.log(0.5), 0.0) if mre_values is not None else (math.log(0.5),)
    parameters = np.empty(fixed_parameters.size + len(scale_start), dtype=np.float64)
    parameters[: fixed_parameters.size] = fixed_parameters
    parameters[fixed_parameters.size :] = scale_start
    history: list[tuple[int, float]] = []
    modes: tuple[float, ...] = ()
    completed_iterations = fixed_iterations
    for points in raw_grid:

        def objective(candidate: FloatVector, selected_points: int = points) -> float:
            return _marginal_log_likelihood(
                candidate,
                matrix,
                first,
                last,
                codes,
                family,
                threshold_count,
                mre_values,
                selected_points,
            )[0]

        parameters, value, completed_iterations = _bfgs_maximize(
            objective, parameters, max_iterations=max_iterations, tolerance=tolerance
        )
        value, modes = _marginal_log_likelihood(
            parameters,
            matrix,
            first,
            last,
            codes,
            family,
            threshold_count,
            mre_values,
            points,
        )
        history.append((points, value))
        if len(history) > 1 and abs(
            history[-1][1] - history[-2][1]
        ) <= quadrature_tolerance * (1.0 + abs(value)):
            break
    else:
        raise ConvergenceError(
            "adaptive quadrature did not stabilize on the declared grid"
        )

    scale_count = 2 if mre_values is not None else 1
    fixed_values = parameters[:-scale_count]
    thresholds = fixed_values[:threshold_count]
    slopes = fixed_values[threshold_count:]
    predictor = matrix @ slopes

    null_matrix = np.empty((matrix.shape[0], 0), dtype=np.float64)
    null_fixed, _, _, _ = _fit_parameters(
        null_matrix,
        first,
        last,
        len(levels),
        family,
        max_iterations=max_iterations,
        tolerance=min(tolerance, 1e-8),
    )
    null_initial = np.empty(null_fixed.size + scale_count, dtype=np.float64)
    null_initial[: null_fixed.size] = null_fixed
    null_initial[null_fixed.size :] = parameters[-scale_count:]
    final_points = history[-1][0]

    def null_objective(candidate: FloatVector) -> float:
        return _marginal_log_likelihood(
            candidate,
            null_matrix,
            first,
            last,
            codes,
            family,
            threshold_count,
            mre_values,
            final_points,
        )[0]

    null_parameters, null_value, _ = _bfgs_maximize(
        null_objective,
        null_initial,
        max_iterations=max_iterations,
        tolerance=tolerance,
    )
    del null_parameters
    threshold_names = tuple(f"y>={level:g}" for level in levels[1:])
    information = _numerical_information(objective, parameters)
    try:
        covariance = np.linalg.solve(information, np.eye(parameters.size))
    except np.linalg.LinAlgError as error:
        raise NumericalError(
            "random-effect observed information matrix is singular"
        ) from error
    covariance = (covariance + covariance.T) * 0.5
    covariance_diagonal = np.asarray(covariance.diagonal(), dtype=np.float64)
    if bool((covariance_diagonal <= 0.0).any()):
        raise NumericalError("random-effect covariance is not positive on its diagonal")
    fixed_covariance = covariance[:-scale_count, :-scale_count]
    fixed_result = OrdinalResult(
        estimator="orm",
        family=family,
        response_levels=levels,
        threshold_names=threshold_names,
        feature_names=names,
        thresholds=tuple(float(value) for value in thresholds),
        coefficients=tuple(float(value) for value in slopes),
        covariance=tuple(
            tuple(float(value) for value in row) for row in fixed_covariance
        ),
        linear_predictors=tuple(float(thresholds[0] + value) for value in predictor),
        fitted_probabilities=_probability_rows(thresholds, predictor, family),
        deviance=(-2.0 * null_value, -2.0 * history[-1][1]),
        iterations=completed_iterations,
        n_observations=matrix.shape[0],
        design_fingerprint=design_fingerprint,
        censored=censored,
    )
    if mre_values is None:
        sigma = math.exp(float(parameters[-1]))
        sigma1 = None
        sigma2 = None
    else:
        sigma = None
        sigma1 = math.exp(float(parameters[-2]))
        sigma2 = float(parameters[-1])
    return RandomEffectsOrdinalResult(
        fixed=fixed_result,
        sigma=sigma,
        sigma1=sigma1,
        sigma2=sigma2,
        cluster_count=len(cluster_levels),
        cluster_modes=modes,
        log_likelihood=history[-1][1],
        clustered_null_log_likelihood=null_value,
        quadrature_points=final_points,
        quadrature_history=tuple(history),
        parameter_names=(
            *threshold_names,
            *names,
            "log(sigma1)" if mre_values is not None else "log(sigma)",
            *(("sigma2",) if mre_values is not None else ()),
        ),
        covariance=tuple(tuple(float(value) for value in row) for row in covariance),
        variance_component_test=_variance_test(
            history[-1][1], fixed_log_likelihood, weighted=mre_values is not None
        ),
    )


__all__ = [
    "RandomEffectsOrdinalResult",
    "VarianceComponentTest",
    "fit_random_intercept_orm",
]
