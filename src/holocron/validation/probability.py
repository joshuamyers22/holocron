"""Model-independent validation metrics for binary probabilities."""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Integral, Real
from typing import cast

import numpy as np

from holocron.exceptions import InputValidationError

MAX_OBSERVATIONS = 1_000_000
MAX_GROUPS = 100
MAX_THRESHOLDS = 4_096
_EPSILON = np.finfo(np.float64).eps


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InputValidationError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise InputValidationError(f"{name} must be a finite number")
    return result


def _optional_probability(value: object, *, name: str) -> float | None:
    if value is None:
        return None
    result = _finite(value, name=name)
    if not 0.0 <= result <= 1.0:
        raise InputValidationError(f"{name} must be between 0 and 1")
    return result


@dataclass(frozen=True, slots=True)
class ProbabilityCalibrationGroup:
    """One weighted equal-frequency calibration group."""

    group: int
    observation_count: int
    total_weight: float
    minimum_prediction: float
    maximum_prediction: float
    mean_prediction: float
    observed_frequency: float
    calibration_error: float
    brier_score: float

    def __post_init__(self) -> None:
        raw_group = cast(object, self.group)
        raw_count = cast(object, self.observation_count)
        if (
            isinstance(raw_group, bool)
            or not isinstance(raw_group, Integral)
            or self.group < 1
            or isinstance(raw_count, bool)
            or not isinstance(raw_count, Integral)
            or self.observation_count < 1
        ):
            raise InputValidationError("calibration group identifiers are invalid")
        if _finite(self.total_weight, name="total_weight") <= 0.0:
            raise InputValidationError("calibration group weight must be positive")
        probabilities = (
            self.minimum_prediction,
            self.maximum_prediction,
            self.mean_prediction,
            self.observed_frequency,
            self.brier_score,
        )
        if any(
            not 0.0 <= _finite(value, name="calibration group") <= 1.0
            for value in probabilities
        ):
            raise InputValidationError("calibration group values must be probabilities")
        if self.minimum_prediction > self.maximum_prediction:
            raise InputValidationError("calibration group prediction range is invalid")
        error = _finite(self.calibration_error, name="calibration_error")
        if not -1.0 <= error <= 1.0:
            raise InputValidationError("calibration_error must be between -1 and 1")


@dataclass(frozen=True, slots=True)
class ProbabilityThresholdMetrics:
    """Weighted classification metrics at one declared probability threshold."""

    threshold: float
    true_positive_weight: float
    false_positive_weight: float
    true_negative_weight: float
    false_negative_weight: float
    sensitivity: float
    specificity: float
    positive_predictive_value: float | None
    negative_predictive_value: float | None
    accuracy: float

    def __post_init__(self) -> None:
        threshold = _finite(self.threshold, name="threshold")
        if not 0.0 < threshold < 1.0:
            raise InputValidationError("threshold must be strictly between 0 and 1")
        for name in (
            "true_positive_weight",
            "false_positive_weight",
            "true_negative_weight",
            "false_negative_weight",
        ):
            if _finite(getattr(self, name), name=name) < 0.0:
                raise InputValidationError(f"{name} must be non-negative")
        for name in ("sensitivity", "specificity", "accuracy"):
            value = _finite(getattr(self, name), name=name)
            if not 0.0 <= value <= 1.0:
                raise InputValidationError(f"{name} must be between 0 and 1")
        _optional_probability(
            self.positive_predictive_value,
            name="positive_predictive_value",
        )
        _optional_probability(
            self.negative_predictive_value,
            name="negative_predictive_value",
        )


@dataclass(frozen=True, slots=True)
class ProbabilityValidationResult:
    """Weighted discrimination, accuracy, and calibration for binary risk."""

    auc: float
    dxy: float
    brier_score: float
    scaled_brier_score: float
    log_loss: float
    null_log_loss: float
    nagelkerke_r_squared: float
    discrimination_index: float
    unreliability_index: float | None
    quality_index: float | None
    likelihood_ratio_chi_square: float
    likelihood_ratio_p_value: float
    unreliability_chi_square: float | None
    unreliability_p_value: float | None
    calibration_intercept: float | None
    calibration_slope: float | None
    maximum_absolute_calibration_error: float | None
    p90_absolute_calibration_error: float | None
    mean_absolute_calibration_error: float | None
    spiegelhalter_z: float
    spiegelhalter_p_value: float
    prevalence: float
    mean_prediction: float
    calibration_in_the_large: float
    calibration_groups: tuple[ProbabilityCalibrationGroup, ...]
    threshold_metrics: tuple[ProbabilityThresholdMetrics, ...]
    n_observations: int
    total_weight: float

    def __post_init__(self) -> None:
        raw_count = cast(object, self.n_observations)
        if (
            isinstance(raw_count, bool)
            or not isinstance(raw_count, Integral)
            or not 2 <= self.n_observations <= MAX_OBSERVATIONS
        ):
            raise InputValidationError("n_observations is outside the supported range")
        if _finite(self.total_weight, name="total_weight") <= 0.0:
            raise InputValidationError("total_weight must be positive")
        for name in (
            "auc",
            "brier_score",
            "likelihood_ratio_p_value",
            "spiegelhalter_p_value",
            "prevalence",
            "mean_prediction",
        ):
            value = _finite(getattr(self, name), name=name)
            if not 0.0 <= value <= 1.0:
                raise InputValidationError(f"{name} must be between 0 and 1")
        if not -1.0 <= _finite(self.dxy, name="dxy") <= 1.0:
            raise InputValidationError("dxy must be between -1 and 1")
        if not math.isclose(self.dxy, 2.0 * self.auc - 1.0, abs_tol=1e-12):
            raise InputValidationError("dxy must equal twice auc minus one")
        for name in (
            "scaled_brier_score",
            "nagelkerke_r_squared",
            "discrimination_index",
            "spiegelhalter_z",
            "calibration_in_the_large",
        ):
            _finite(getattr(self, name), name=name)
        for name in (
            "log_loss",
            "null_log_loss",
            "likelihood_ratio_chi_square",
        ):
            if _finite(getattr(self, name), name=name) < 0.0:
                raise InputValidationError(f"{name} must be non-negative")
        optional_finite = (
            self.unreliability_index,
            self.quality_index,
            self.unreliability_chi_square,
            self.calibration_intercept,
            self.calibration_slope,
        )
        if any(
            value is not None and not math.isfinite(value) for value in optional_finite
        ):
            raise InputValidationError("optional probability metrics must be finite")
        for name in (
            "unreliability_p_value",
            "maximum_absolute_calibration_error",
            "p90_absolute_calibration_error",
            "mean_absolute_calibration_error",
        ):
            _optional_probability(getattr(self, name), name=name)
        recalibration_defined = self.calibration_intercept is not None
        linked = (
            self.calibration_slope,
            self.unreliability_index,
            self.quality_index,
            self.unreliability_chi_square,
            self.unreliability_p_value,
            self.maximum_absolute_calibration_error,
            self.p90_absolute_calibration_error,
            self.mean_absolute_calibration_error,
        )
        if any((value is not None) != recalibration_defined for value in linked):
            raise InputValidationError("recalibration metrics must be jointly defined")
        if not isinstance(cast(object, self.calibration_groups), tuple) or any(
            not isinstance(cast(object, value), ProbabilityCalibrationGroup)
            for value in self.calibration_groups
        ):
            raise InputValidationError("calibration_groups are invalid")
        if not isinstance(cast(object, self.threshold_metrics), tuple) or any(
            not isinstance(cast(object, value), ProbabilityThresholdMetrics)
            for value in self.threshold_metrics
        ):
            raise InputValidationError("threshold_metrics are invalid")


def _inputs(
    outcomes: Iterable[int | bool],
    probabilities: Iterable[float],
    weights: Iterable[float] | None,
) -> tuple[tuple[int, ...], tuple[float, ...], tuple[float, ...]]:
    raw_outcomes = tuple(outcomes)
    raw_probabilities = tuple(probabilities)
    if not 2 <= len(raw_outcomes) <= MAX_OBSERVATIONS:
        raise InputValidationError("outcomes must contain 2-1000000 observations")
    if len(raw_probabilities) != len(raw_outcomes):
        raise InputValidationError("probabilities must contain one value per outcome")
    if any(
        not isinstance(value, (bool, Integral)) or int(value) not in {0, 1}
        for value in raw_outcomes
    ):
        raise InputValidationError("outcomes must contain only binary values")
    y = tuple(int(value) for value in raw_outcomes)
    if len(set(y)) != 2:
        raise InputValidationError("outcomes must contain both binary classes")
    p = tuple(_finite(value, name="probabilities") for value in raw_probabilities)
    if any(not 0.0 < value < 1.0 for value in p):
        raise InputValidationError("probabilities must be strictly between 0 and 1")
    if weights is None:
        w = (1.0,) * len(y)
    else:
        raw_weights = tuple(weights)
        if len(raw_weights) != len(y):
            raise InputValidationError("weights must contain one value per outcome")
        w = tuple(_finite(value, name="weights") for value in raw_weights)
        if any(value <= 0.0 for value in w):
            raise InputValidationError("weights must be positive")
    return y, p, w


def _weighted_auc(
    outcomes: tuple[int, ...],
    probabilities: tuple[float, ...],
    weights: tuple[float, ...],
) -> float:
    controls = sorted(
        (probability, weight)
        for outcome, probability, weight in zip(
            outcomes, probabilities, weights, strict=True
        )
        if outcome == 0
    )
    values = [value for value, _ in controls]
    prefix = [0.0]
    for _, weight in controls:
        prefix.append(prefix[-1] + weight)
    control_weight = prefix[-1]
    case_weight = sum(
        weight for outcome, weight in zip(outcomes, weights, strict=True) if outcome
    )
    concordant = 0.0
    for outcome, probability, weight in zip(
        outcomes, probabilities, weights, strict=True
    ):
        if outcome == 0:
            continue
        left = bisect.bisect_left(values, probability)
        right = bisect.bisect_right(values, probability)
        lower_weight = prefix[left]
        equal_weight = prefix[right] - prefix[left]
        concordant += weight * (lower_weight + 0.5 * equal_weight)
    return concordant / (case_weight * control_weight)


def _expit(value: float) -> float:
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _log_likelihood(
    outcomes: tuple[int, ...],
    probabilities: tuple[float, ...],
    weights: tuple[float, ...],
) -> float:
    return sum(
        weight
        * (outcome * math.log(probability) + (1 - outcome) * math.log1p(-probability))
        for outcome, probability, weight in zip(
            outcomes, probabilities, weights, strict=True
        )
    )


def _recalibrate(
    outcomes: tuple[int, ...],
    logits: tuple[float, ...],
    weights: tuple[float, ...],
) -> tuple[float, float, tuple[float, ...], float] | None:
    if max(logits) == min(logits):
        prevalence = sum(
            outcome * weight for outcome, weight in zip(outcomes, weights, strict=True)
        ) / sum(weights)
        intercept = math.log(prevalence / (1.0 - prevalence))
        calibrated = (prevalence,) * len(outcomes)
        return (
            intercept,
            0.0,
            calibrated,
            _log_likelihood(outcomes, calibrated, weights),
        )
    design = np.empty((len(outcomes), 2), dtype=np.float64)
    design[:, 0] = 1.0
    design[:, 1] = np.asarray(logits, dtype=np.float64)
    response = np.asarray(outcomes, dtype=np.float64)
    frequency = np.asarray(weights, dtype=np.float64)
    coefficients = np.asarray((0.0, 1.0), dtype=np.float64)
    for _ in range(100):
        linear = design @ coefficients
        probability = np.asarray([_expit(float(value)) for value in linear])
        working_weight = frequency * probability * (1.0 - probability)
        information = design.T @ (working_weight[:, None] * design)
        score = design.T @ (frequency * (response - probability))
        try:
            step = np.linalg.solve(information, score)
        except np.linalg.LinAlgError:
            return None
        coefficients += step
        if (
            not all(math.isfinite(float(value)) for value in coefficients)
            or float(np.max(np.abs(coefficients))) >= 50.0
        ):
            return None
        if float(np.max(np.abs(step))) <= 1e-10:
            calibrated = tuple(_expit(float(value)) for value in design @ coefficients)
            return (
                float(coefficients[0]),
                float(coefficients[1]),
                calibrated,
                _log_likelihood(outcomes, calibrated, weights),
            )
    return None


def _weighted_quantile(
    values: tuple[float, ...], weights: tuple[float, ...], probability: float
) -> float:
    ordered = sorted(zip(values, weights, strict=True))
    target = probability * sum(weights)
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return value
    return ordered[-1][0]


def _calibration_groups(
    outcomes: tuple[int, ...],
    probabilities: tuple[float, ...],
    weights: tuple[float, ...],
    group_count: int,
) -> tuple[ProbabilityCalibrationGroup, ...]:
    ordered = sorted(
        zip(probabilities, outcomes, weights, strict=True), key=lambda row: row[0]
    )
    total_weight = sum(weights)
    grouped: list[list[tuple[float, int, float]]] = []
    cumulative = 0.0
    current: list[tuple[float, int, float]] = []
    start = 0
    while start < len(ordered):
        stop = start + 1
        while stop < len(ordered) and ordered[stop][0] == ordered[start][0]:
            stop += 1
        tied_rows = ordered[start:stop]
        tied_weight = sum(row[2] for row in tied_rows)
        midpoint = cumulative + 0.5 * tied_weight
        target_group = min(group_count - 1, int(midpoint * group_count / total_weight))
        if current and len(grouped) < target_group:
            grouped.append(current)
            current = []
        current.extend(tied_rows)
        cumulative += tied_weight
        start = stop
    if current:
        grouped.append(current)
    result: list[ProbabilityCalibrationGroup] = []
    for index, rows in enumerate(grouped, start=1):
        group_weight = sum(row[2] for row in rows)
        mean_prediction = sum(row[0] * row[2] for row in rows) / group_weight
        observed = sum(row[1] * row[2] for row in rows) / group_weight
        brier = sum(row[2] * (row[1] - row[0]) ** 2 for row in rows) / group_weight
        result.append(
            ProbabilityCalibrationGroup(
                group=index,
                observation_count=len(rows),
                total_weight=group_weight,
                minimum_prediction=rows[0][0],
                maximum_prediction=rows[-1][0],
                mean_prediction=mean_prediction,
                observed_frequency=observed,
                calibration_error=observed - mean_prediction,
                brier_score=brier,
            )
        )
    return tuple(result)


def _threshold_metrics(
    outcomes: tuple[int, ...],
    probabilities: tuple[float, ...],
    weights: tuple[float, ...],
    thresholds: tuple[float, ...],
) -> tuple[ProbabilityThresholdMetrics, ...]:
    result: list[ProbabilityThresholdMetrics] = []
    for threshold in thresholds:
        true_positive = false_positive = true_negative = false_negative = 0.0
        for outcome, probability, weight in zip(
            outcomes, probabilities, weights, strict=True
        ):
            predicted = probability >= threshold
            if predicted and outcome:
                true_positive += weight
            elif predicted:
                false_positive += weight
            elif outcome:
                false_negative += weight
            else:
                true_negative += weight
        positive_prediction = true_positive + false_positive
        negative_prediction = true_negative + false_negative
        result.append(
            ProbabilityThresholdMetrics(
                threshold=threshold,
                true_positive_weight=true_positive,
                false_positive_weight=false_positive,
                true_negative_weight=true_negative,
                false_negative_weight=false_negative,
                sensitivity=true_positive / (true_positive + false_negative),
                specificity=true_negative / (true_negative + false_positive),
                positive_predictive_value=(
                    None
                    if positive_prediction == 0.0
                    else true_positive / positive_prediction
                ),
                negative_predictive_value=(
                    None
                    if negative_prediction == 0.0
                    else true_negative / negative_prediction
                ),
                accuracy=(true_positive + true_negative) / sum(weights),
            )
        )
    return tuple(result)


def validate_probabilities(
    outcomes: Iterable[int | bool],
    probabilities: Iterable[float],
    *,
    weights: Iterable[float] | None = None,
    calibration_groups: int = 10,
    thresholds: Iterable[float] = (0.5,),
) -> ProbabilityValidationResult:
    """Validate binary probabilities without requiring a fitted model.

    The result combines weighted rank discrimination, proper scores,
    likelihood-based quality indices, logistic recalibration, grouped
    calibration, Spiegelhalter's calibration test, and declared-threshold
    classification metrics. Probabilities at exactly zero or one are rejected
    because finite log loss and logit recalibration are part of this contract.
    """
    y, p, w = _inputs(outcomes, probabilities, weights)
    raw_groups = cast(object, calibration_groups)
    if (
        isinstance(raw_groups, bool)
        or not isinstance(raw_groups, Integral)
        or not 1 <= calibration_groups <= MAX_GROUPS
    ):
        raise InputValidationError(
            f"calibration_groups must be between 1 and {MAX_GROUPS}"
        )
    threshold_values = tuple(_finite(value, name="thresholds") for value in thresholds)
    if (
        not threshold_values
        or len(threshold_values) > MAX_THRESHOLDS
        or any(not 0.0 < value < 1.0 for value in threshold_values)
        or any(
            left >= right
            for left, right in zip(threshold_values, threshold_values[1:], strict=False)
        )
    ):
        raise InputValidationError(
            "thresholds must be strictly increasing values between 0 and 1"
        )
    total_weight = sum(w)
    prevalence = (
        sum(outcome * weight for outcome, weight in zip(y, w, strict=True))
        / total_weight
    )
    mean_prediction = (
        sum(probability * weight for probability, weight in zip(p, w, strict=True))
        / total_weight
    )
    brier = (
        sum(
            weight * (outcome - probability) ** 2
            for outcome, probability, weight in zip(y, p, w, strict=True)
        )
        / total_weight
    )
    null_brier = prevalence * (1.0 - prevalence)
    original_log_likelihood = _log_likelihood(y, p, w)
    null_probabilities = (prevalence,) * len(y)
    null_log_likelihood = _log_likelihood(y, null_probabilities, w)
    likelihood_ratio = 2.0 * (original_log_likelihood - null_log_likelihood)
    denominator = 1.0 - math.exp(2.0 * null_log_likelihood / total_weight)
    nagelkerke = (
        (1.0 - math.exp(-likelihood_ratio / total_weight)) / denominator
        if denominator > 0.0
        else 0.0
    )
    discrimination = (likelihood_ratio - 1.0) / total_weight
    logits = tuple(math.log(value / (1.0 - value)) for value in p)
    recalibrated = _recalibrate(y, logits, w)
    intercept: float | None = None
    slope: float | None = None
    unreliability_chi_square: float | None = None
    unreliability_p_value: float | None = None
    unreliability: float | None = None
    quality: float | None = None
    maximum_error: float | None = None
    p90_error: float | None = None
    mean_error: float | None = None
    if recalibrated is not None:
        intercept, slope, recalibrated_probabilities, recalibrated_log_likelihood = (
            recalibrated
        )
        unreliability_chi_square = max(
            0.0, 2.0 * (recalibrated_log_likelihood - original_log_likelihood)
        )
        unreliability_p_value = math.exp(-0.5 * unreliability_chi_square)
        unreliability = (unreliability_chi_square - 2.0) / total_weight
        quality = discrimination - unreliability
        errors = tuple(
            abs(original - calibrated)
            for original, calibrated in zip(p, recalibrated_probabilities, strict=True)
        )
        maximum_error = max(errors)
        p90_error = _weighted_quantile(errors, w, 0.9)
        mean_error = (
            sum(error * weight for error, weight in zip(errors, w, strict=True))
            / total_weight
        )
    spiegelhalter_numerator = sum(
        weight * (outcome - probability) * (1.0 - 2.0 * probability)
        for outcome, probability, weight in zip(y, p, w, strict=True)
    )
    spiegelhalter_denominator = math.sqrt(
        sum(
            weight * (1.0 - 2.0 * probability) ** 2 * probability * (1.0 - probability)
            for probability, weight in zip(p, w, strict=True)
        )
    )
    spiegelhalter_z = (
        0.0
        if spiegelhalter_denominator <= _EPSILON
        else spiegelhalter_numerator / spiegelhalter_denominator
    )
    auc = _weighted_auc(y, p, w)
    return ProbabilityValidationResult(
        auc=auc,
        dxy=2.0 * auc - 1.0,
        brier_score=brier,
        scaled_brier_score=1.0 - brier / null_brier,
        log_loss=-original_log_likelihood / total_weight,
        null_log_loss=-null_log_likelihood / total_weight,
        nagelkerke_r_squared=nagelkerke,
        discrimination_index=discrimination,
        unreliability_index=unreliability,
        quality_index=quality,
        likelihood_ratio_chi_square=max(0.0, likelihood_ratio),
        likelihood_ratio_p_value=math.erfc(math.sqrt(max(0.0, likelihood_ratio) / 2.0)),
        unreliability_chi_square=unreliability_chi_square,
        unreliability_p_value=unreliability_p_value,
        calibration_intercept=intercept,
        calibration_slope=slope,
        maximum_absolute_calibration_error=maximum_error,
        p90_absolute_calibration_error=p90_error,
        mean_absolute_calibration_error=mean_error,
        spiegelhalter_z=spiegelhalter_z,
        spiegelhalter_p_value=math.erfc(abs(spiegelhalter_z) / math.sqrt(2.0)),
        prevalence=prevalence,
        mean_prediction=mean_prediction,
        calibration_in_the_large=prevalence - mean_prediction,
        calibration_groups=_calibration_groups(y, p, w, calibration_groups),
        threshold_metrics=_threshold_metrics(y, p, w, threshold_values),
        n_observations=len(y),
        total_weight=total_weight,
    )


__all__ = [
    "ProbabilityCalibrationGroup",
    "ProbabilityThresholdMetrics",
    "ProbabilityValidationResult",
    "validate_probabilities",
]
