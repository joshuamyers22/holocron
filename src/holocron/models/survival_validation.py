"""Censoring-aware fixed-horizon survival-validation primitives."""

from __future__ import annotations

import bisect
import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Integral, Real
from typing import cast

from holocron.exceptions import InputValidationError

MAX_OBSERVATIONS = 1_000_000
MAX_HORIZONS = 4096
MAX_PREDICTION_VALUES = 10_000_000
MAX_CALIBRATION_GROUPS = 100
MAX_RISK_THRESHOLDS = 4096


def _optional_probability(value: float | None, *, name: str) -> None:
    if value is not None and (not math.isfinite(value) or not 0.0 <= value <= 1.0):
        raise InputValidationError(f"{name} must be undefined or between 0 and 1")


@dataclass(frozen=True, slots=True)
class SurvivalCalibrationGroup:
    """One prediction-ranked Kaplan--Meier calibration group at a horizon."""

    horizon: float
    group: int
    observation_count: int
    total_weight: float
    minimum_predicted_survival: float
    maximum_predicted_survival: float
    mean_predicted_survival: float
    observed_survival: float
    calibration_error: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.horizon)
            or self.horizon <= 0.0
            or isinstance(cast(object, self.group), bool)
            or not isinstance(cast(object, self.group), Integral)
            or self.group < 1
            or isinstance(cast(object, self.observation_count), bool)
            or not isinstance(cast(object, self.observation_count), Integral)
            or self.observation_count < 1
            or not math.isfinite(self.total_weight)
            or self.total_weight <= 0.0
        ):
            raise InputValidationError("survival calibration group metadata is invalid")
        probabilities = (
            self.minimum_predicted_survival,
            self.maximum_predicted_survival,
            self.mean_predicted_survival,
            self.observed_survival,
        )
        if any(
            not math.isfinite(value) or not 0.0 <= value <= 1.0
            for value in probabilities
        ):
            raise InputValidationError(
                "survival calibration group probabilities are invalid"
            )
        if self.minimum_predicted_survival > self.maximum_predicted_survival:
            raise InputValidationError(
                "survival calibration group prediction range is invalid"
            )
        if (
            not math.isfinite(self.calibration_error)
            or not -1.0 <= self.calibration_error <= 1.0
        ):
            raise InputValidationError("survival calibration error is invalid")


@dataclass(frozen=True, slots=True)
class SurvivalThresholdMetrics:
    """IPCW binary risk-classification metrics at one horizon and threshold."""

    horizon: float
    risk_threshold: float
    true_positive_weight: float
    false_positive_weight: float
    true_negative_weight: float
    false_negative_weight: float
    sensitivity: float | None
    specificity: float | None
    positive_predictive_value: float | None
    negative_predictive_value: float | None
    accuracy: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.horizon) or self.horizon <= 0.0:
            raise InputValidationError("threshold horizon must be positive")
        if (
            not math.isfinite(self.risk_threshold)
            or not 0.0 < self.risk_threshold < 1.0
        ):
            raise InputValidationError("risk_threshold must be between 0 and 1")
        weights = (
            self.true_positive_weight,
            self.false_positive_weight,
            self.true_negative_weight,
            self.false_negative_weight,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in weights):
            raise InputValidationError("survival threshold weights are invalid")
        for name in (
            "sensitivity",
            "specificity",
            "positive_predictive_value",
            "negative_predictive_value",
        ):
            _optional_probability(getattr(self, name), name=name)
        if not math.isfinite(self.accuracy) or not 0.0 <= self.accuracy <= 1.0:
            raise InputValidationError("survival threshold accuracy is invalid")


@dataclass(frozen=True, slots=True)
class SurvivalValidationResult:
    """Censoring-adjusted discrimination, accuracy, and calibration by horizon."""

    horizons: tuple[float, ...]
    brier_scores: tuple[float, ...]
    aucs: tuple[float | None, ...]
    dxy: tuple[float | None, ...]
    observed_survival: tuple[float, ...]
    mean_predicted_survival: tuple[float, ...]
    calibration_errors: tuple[float, ...]
    censoring_survival: tuple[float, ...]
    case_counts: tuple[int, ...]
    control_counts: tuple[int, ...]
    integrated_brier_score: float | None
    integrated_auc: float | None
    integrated_absolute_calibration_error: float | None
    calibration_groups: tuple[tuple[SurvivalCalibrationGroup, ...], ...]
    threshold_metrics: tuple[SurvivalThresholdMetrics, ...]
    n_observations: int
    total_weight: float

    def __post_init__(self) -> None:
        width = len(self.horizons)
        aligned = (
            self.brier_scores,
            self.aucs,
            self.dxy,
            self.observed_survival,
            self.mean_predicted_survival,
            self.calibration_errors,
            self.censoring_survival,
            self.case_counts,
            self.control_counts,
        )
        if (
            width == 0
            or any(len(values) != width for values in aligned)
            or self.n_observations < 1
            or not math.isfinite(self.total_weight)
            or self.total_weight <= 0.0
            or any(not math.isfinite(value) or value <= 0.0 for value in self.horizons)
            or any(
                later <= earlier
                for earlier, later in zip(
                    self.horizons, self.horizons[1:], strict=False
                )
            )
            or any(
                not math.isfinite(value) or value < 0.0 for value in self.brier_scores
            )
            or any(value is not None and not 0.0 <= value <= 1.0 for value in self.aucs)
            or any(value is not None and not -1.0 <= value <= 1.0 for value in self.dxy)
            or any(
                not math.isfinite(value) or not 0.0 <= value <= 1.0
                for values in (
                    self.observed_survival,
                    self.mean_predicted_survival,
                    self.censoring_survival,
                )
                for value in values
            )
            or any(
                not math.isfinite(value) or not -1.0 <= value <= 1.0
                for value in self.calibration_errors
            )
            or any(
                value < 0
                for values in (self.case_counts, self.control_counts)
                for value in values
            )
            or (
                self.integrated_brier_score is not None
                and (
                    not math.isfinite(self.integrated_brier_score)
                    or self.integrated_brier_score < 0.0
                )
            )
            or (
                self.integrated_auc is not None
                and (
                    not math.isfinite(self.integrated_auc)
                    or not 0.0 <= self.integrated_auc <= 1.0
                )
            )
            or (
                self.integrated_absolute_calibration_error is not None
                and (
                    not math.isfinite(self.integrated_absolute_calibration_error)
                    or not 0.0 <= self.integrated_absolute_calibration_error <= 1.0
                )
            )
        ):
            raise InputValidationError("inconsistent survival validation result")
        for auc, dxy in zip(self.aucs, self.dxy, strict=True):
            if (auc is None) != (dxy is None) or (
                auc is not None
                and dxy is not None
                and not math.isclose(dxy, 2.0 * auc - 1.0, abs_tol=1e-12)
            ):
                raise InputValidationError(
                    "inconsistent survival discrimination result"
                )
        if (width == 1) != (self.integrated_brier_score is None):
            raise InputValidationError("inconsistent integrated Brier score")
        if width == 1 and (
            self.integrated_auc is not None
            or self.integrated_absolute_calibration_error is not None
        ):
            raise InputValidationError("single-horizon integrated metrics must be None")
        if width > 1 and (
            self.integrated_absolute_calibration_error is None
            or (self.integrated_auc is None)
            != any(value is None for value in self.aucs)
        ):
            raise InputValidationError("inconsistent integrated survival metrics")
        if len(self.calibration_groups) != width or any(
            not isinstance(cast(object, groups), tuple)
            or not groups
            or any(
                not isinstance(cast(object, group), SurvivalCalibrationGroup)
                or group.horizon != self.horizons[index]
                for group in groups
            )
            for index, groups in enumerate(self.calibration_groups)
        ):
            raise InputValidationError("survival calibration groups are inconsistent")
        if not isinstance(cast(object, self.threshold_metrics), tuple) or any(
            not isinstance(cast(object, value), SurvivalThresholdMetrics)
            for value in self.threshold_metrics
        ):
            raise InputValidationError("survival threshold metrics are inconsistent")
        threshold_rows = tuple(
            tuple(
                value.risk_threshold
                for value in self.threshold_metrics
                if value.horizon == horizon
            )
            for horizon in self.horizons
        )
        if (
            not threshold_rows[0]
            or any(
                value.horizon not in self.horizons for value in self.threshold_metrics
            )
            or any(values != threshold_rows[0] for values in threshold_rows[1:])
            or len(self.threshold_metrics) != width * len(threshold_rows[0])
        ):
            raise InputValidationError("survival threshold metrics are inconsistent")


def _numeric_tuple(
    values: Iterable[float], *, name: str, positive: bool = False
) -> tuple[float, ...]:
    raw = tuple(values)
    if not raw or len(raw) > MAX_OBSERVATIONS:
        raise InputValidationError(f"{name} must contain supported observations")
    result: list[float] = []
    for value in raw:
        if (
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(float(value))
            or (positive and float(value) <= 0.0)
        ):
            qualifier = "positive finite" if positive else "finite"
            raise InputValidationError(f"{name} must contain only {qualifier} values")
        result.append(float(value))
    return tuple(result)


def _event_tuple(values: Iterable[int | bool], rows: int) -> tuple[int, ...]:
    raw = tuple(values)
    if len(raw) != rows or any(
        not isinstance(value, (bool, Integral)) or int(value) not in {0, 1}
        for value in raw
    ):
        raise InputValidationError("events must contain one binary value per row")
    return tuple(int(value) for value in raw)


def _prediction_rows(
    values: Iterable[Iterable[float]], rows: int, columns: int
) -> tuple[tuple[float, ...], ...]:
    if rows * columns > MAX_PREDICTION_VALUES:
        raise InputValidationError("survival predictions exceed the supported size")
    raw_rows = tuple(tuple(row) for row in values)
    if len(raw_rows) != rows or any(len(row) != columns for row in raw_rows):
        raise InputValidationError(
            "predicted survival must have one row per observation and horizon"
        )
    result: list[tuple[float, ...]] = []
    for row in raw_rows:
        parsed: list[float] = []
        for value in row:
            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(float(value))
                or not 0.0 <= float(value) <= 1.0
            ):
                raise InputValidationError(
                    "predicted survival probabilities must be finite and in [0, 1]"
                )
            parsed.append(float(value))
        if any(
            later > earlier for earlier, later in zip(parsed, parsed[1:], strict=False)
        ):
            raise InputValidationError(
                "predicted survival must not increase across horizons"
            )
        result.append(tuple(parsed))
    return tuple(result)


def _kaplan_meier_steps(
    times: tuple[float, ...],
    failures: tuple[int, ...],
    weights: tuple[float, ...],
) -> tuple[tuple[float, ...], tuple[float, ...], dict[float, float]]:
    grouped: dict[float, list[float]] = {}
    for time, failure, weight in zip(times, failures, weights, strict=True):
        totals = grouped.setdefault(time, [0.0, 0.0])
        totals[0] += weight
        if failure:
            totals[1] += weight
    risk = sum(weights)
    survival = 1.0
    step_times: list[float] = []
    step_values: list[float] = []
    before: dict[float, float] = {}
    for time in sorted(grouped):
        observed_weight, failure_weight = grouped[time]
        before[time] = survival
        if failure_weight:
            survival *= max(0.0, 1.0 - failure_weight / risk)
        step_times.append(time)
        step_values.append(survival)
        risk -= observed_weight
    return tuple(step_times), tuple(step_values), before


def _step_at(
    horizon: float, step_times: tuple[float, ...], step_values: tuple[float, ...]
) -> float:
    index = bisect.bisect_right(step_times, horizon) - 1
    return 1.0 if index < 0 else step_values[index]


def _weighted_dynamic_auc(
    case_predictions: list[tuple[float, float]],
    control_predictions: list[tuple[float, float]],
) -> float | None:
    if not case_predictions or not control_predictions:
        return None
    ordered_controls = sorted(control_predictions)
    control_values = [value for value, _ in ordered_controls]
    prefix = [0.0]
    for _, weight in ordered_controls:
        prefix.append(prefix[-1] + weight)
    control_weight = prefix[-1]
    case_weight = sum(weight for _, weight in case_predictions)
    if case_weight <= 0.0 or control_weight <= 0.0:
        return None
    concordant = 0.0
    for prediction, weight in case_predictions:
        left = bisect.bisect_left(control_values, prediction)
        right = bisect.bisect_right(control_values, prediction)
        equal_weight = prefix[right] - prefix[left]
        greater_weight = control_weight - prefix[right]
        concordant += weight * (greater_weight + 0.5 * equal_weight)
    return min(1.0, max(0.0, concordant / (case_weight * control_weight)))


def _prediction_groups(
    predictions: tuple[float, ...],
    weights: tuple[float, ...],
    group_count: int,
) -> tuple[tuple[int, ...], ...]:
    ordered = sorted(range(len(predictions)), key=lambda index: predictions[index])
    total_weight = sum(weights)
    grouped: list[list[int]] = []
    current: list[int] = []
    cumulative = 0.0
    start = 0
    while start < len(ordered):
        stop = start + 1
        while (
            stop < len(ordered)
            and predictions[ordered[stop]] == predictions[ordered[start]]
        ):
            stop += 1
        tied_indices = ordered[start:stop]
        tied_weight = sum(weights[index] for index in tied_indices)
        midpoint = cumulative + 0.5 * tied_weight
        target_group = min(group_count - 1, int(midpoint * group_count / total_weight))
        if current and len(grouped) < target_group:
            grouped.append(current)
            current = []
        current.extend(tied_indices)
        cumulative += tied_weight
        start = stop
    if current:
        grouped.append(current)
    return tuple(tuple(group) for group in grouped)


def _survival_calibration_groups(
    times: tuple[float, ...],
    events: tuple[int, ...],
    predictions: tuple[float, ...],
    weights: tuple[float, ...],
    *,
    horizon: float,
    group_count: int,
) -> tuple[SurvivalCalibrationGroup, ...]:
    groups = _prediction_groups(predictions, weights, group_count)
    result: list[SurvivalCalibrationGroup] = []
    for number, indices in enumerate(groups, start=1):
        group_times = tuple(times[index] for index in indices)
        group_events = tuple(events[index] for index in indices)
        group_weights = tuple(weights[index] for index in indices)
        group_predictions = tuple(predictions[index] for index in indices)
        step_times, step_values, _ = _kaplan_meier_steps(
            group_times, group_events, group_weights
        )
        observed = _step_at(horizon, step_times, step_values)
        total_weight = sum(group_weights)
        mean_prediction = (
            sum(
                prediction * weight
                for prediction, weight in zip(
                    group_predictions, group_weights, strict=True
                )
            )
            / total_weight
        )
        result.append(
            SurvivalCalibrationGroup(
                horizon=horizon,
                group=number,
                observation_count=len(indices),
                total_weight=total_weight,
                minimum_predicted_survival=min(group_predictions),
                maximum_predicted_survival=max(group_predictions),
                mean_predicted_survival=mean_prediction,
                observed_survival=observed,
                calibration_error=observed - mean_prediction,
            )
        )
    return tuple(result)


def _survival_threshold_metrics(
    predictions: tuple[float, ...],
    case_weights: tuple[float, ...],
    control_weights: tuple[float, ...],
    *,
    horizon: float,
    thresholds: tuple[float, ...],
) -> tuple[SurvivalThresholdMetrics, ...]:
    result: list[SurvivalThresholdMetrics] = []
    for threshold in thresholds:
        true_positive = false_positive = true_negative = false_negative = 0.0
        for survival, case_weight, control_weight in zip(
            predictions, case_weights, control_weights, strict=True
        ):
            predicted_event = 1.0 - survival >= threshold
            if case_weight > 0.0:
                if predicted_event:
                    true_positive += case_weight
                else:
                    false_negative += case_weight
            elif control_weight > 0.0:
                if predicted_event:
                    false_positive += control_weight
                else:
                    true_negative += control_weight
        case_total = true_positive + false_negative
        control_total = true_negative + false_positive
        positive_total = true_positive + false_positive
        negative_total = true_negative + false_negative
        evaluable = case_total + control_total
        result.append(
            SurvivalThresholdMetrics(
                horizon=horizon,
                risk_threshold=threshold,
                true_positive_weight=true_positive,
                false_positive_weight=false_positive,
                true_negative_weight=true_negative,
                false_negative_weight=false_negative,
                sensitivity=(None if case_total == 0.0 else true_positive / case_total),
                specificity=(
                    None if control_total == 0.0 else true_negative / control_total
                ),
                positive_predictive_value=(
                    None if positive_total == 0.0 else true_positive / positive_total
                ),
                negative_predictive_value=(
                    None if negative_total == 0.0 else true_negative / negative_total
                ),
                accuracy=(
                    0.0
                    if evaluable == 0.0
                    else (true_positive + true_negative) / evaluable
                ),
            )
        )
    return tuple(result)


def _integrated_metric(
    horizons: tuple[float, ...], values: tuple[float, ...]
) -> float | None:
    if len(horizons) == 1:
        return None
    area = sum(
        (right_time - left_time) * (left_value + right_value) * 0.5
        for left_time, right_time, left_value, right_value in zip(
            horizons[:-1],
            horizons[1:],
            values[:-1],
            values[1:],
            strict=True,
        )
    )
    return area / (horizons[-1] - horizons[0])


def validate_survival_predictions(
    times: Iterable[float],
    events: Iterable[int | bool],
    predicted_survival: Iterable[Iterable[float]],
    horizons: Iterable[float],
    *,
    weights: Iterable[float] | None = None,
    calibration_groups: int = 10,
    risk_thresholds: Iterable[float] = (0.5,),
) -> SurvivalValidationResult:
    """Validate right-censored survival predictions at fixed horizons.

    Brier scores use inverse Kaplan--Meier censoring weights. AUC is the
    cumulative/dynamic definition with event cases through each horizon and
    event-free controls beyond it; ties receive half credit. Integrated Brier
    score is the normalized trapezoidal integral over the supplied horizons.
    Prediction-ranked groups use Kaplan--Meier observed survival, and declared
    risk thresholds use the same IPCW case/control definitions as AUC.
    """
    time_values = _numeric_tuple(times, name="times", positive=True)
    event_values = _event_tuple(events, len(time_values))
    horizon_values = _numeric_tuple(horizons, name="horizons", positive=True)
    if len(horizon_values) > MAX_HORIZONS or any(
        later <= earlier
        for earlier, later in zip(horizon_values, horizon_values[1:], strict=False)
    ):
        raise InputValidationError(
            "horizons must be strictly increasing within the supported limit"
        )
    predictions = _prediction_rows(
        predicted_survival, len(time_values), len(horizon_values)
    )
    weight_values = (
        (1.0,) * len(time_values)
        if weights is None
        else _numeric_tuple(weights, name="weights", positive=True)
    )
    if len(weight_values) != len(time_values):
        raise InputValidationError("weights must contain one value per observation")
    total_weight = sum(weight_values)
    raw_group_count = cast(object, calibration_groups)
    if (
        isinstance(raw_group_count, bool)
        or not isinstance(raw_group_count, Integral)
        or not 1 <= calibration_groups <= MAX_CALIBRATION_GROUPS
    ):
        raise InputValidationError(
            f"calibration_groups must be between 1 and {MAX_CALIBRATION_GROUPS}"
        )
    threshold_values = _numeric_tuple(
        risk_thresholds,
        name="risk_thresholds",
        positive=True,
    )
    if (
        not threshold_values
        or len(threshold_values) > MAX_RISK_THRESHOLDS
        or any(not 0.0 < value < 1.0 for value in threshold_values)
        or any(
            left >= right
            for left, right in zip(threshold_values, threshold_values[1:], strict=False)
        )
    ):
        raise InputValidationError(
            "risk_thresholds must be strictly increasing values between 0 and 1"
        )

    censoring_events = tuple(1 - event for event in event_values)
    censor_times, censor_steps, censor_before = _kaplan_meier_steps(
        time_values, censoring_events, weight_values
    )
    observed_times, observed_steps, _ = _kaplan_meier_steps(
        time_values, event_values, weight_values
    )

    brier_scores: list[float] = []
    aucs: list[float | None] = []
    observed_survival: list[float] = []
    mean_predictions: list[float] = []
    calibration_errors: list[float] = []
    censoring_survival: list[float] = []
    case_counts: list[int] = []
    control_counts: list[int] = []
    grouped_calibration: list[tuple[SurvivalCalibrationGroup, ...]] = []
    threshold_metrics: list[SurvivalThresholdMetrics] = []

    for column, horizon in enumerate(horizon_values):
        censor_at_horizon = _step_at(horizon, censor_times, censor_steps)
        cases: list[tuple[float, float]] = []
        controls: list[tuple[float, float]] = []
        brier_total = 0.0
        case_weights = [0.0] * len(time_values)
        control_weights = [0.0] * len(time_values)
        for row_index, (time, event, row, weight) in enumerate(
            zip(time_values, event_values, predictions, weight_values, strict=True)
        ):
            prediction = row[column]
            if event and time <= horizon:
                censor_probability = censor_before[time]
                if censor_probability <= 0.0:
                    raise InputValidationError(
                        "censoring survival is zero before an observed event"
                    )
                adjusted_weight = weight / censor_probability
                brier_total += adjusted_weight * prediction * prediction
                cases.append((prediction, adjusted_weight))
                case_weights[row_index] = adjusted_weight
            elif time > horizon:
                if censor_at_horizon <= 0.0:
                    raise InputValidationError(
                        "censoring survival is zero at an evaluation horizon"
                    )
                adjusted_weight = weight / censor_at_horizon
                brier_total += adjusted_weight * (1.0 - prediction) * (1.0 - prediction)
                controls.append((prediction, weight))
                control_weights[row_index] = adjusted_weight
        if not cases and not controls:
            raise InputValidationError(
                "each horizon requires an observed event or an event-free control"
            )
        brier_scores.append(brier_total / total_weight)
        aucs.append(_weighted_dynamic_auc(cases, controls))
        observed = _step_at(horizon, observed_times, observed_steps)
        mean_prediction = (
            sum(
                weight * row[column]
                for weight, row in zip(weight_values, predictions, strict=True)
            )
            / total_weight
        )
        observed_survival.append(observed)
        mean_predictions.append(mean_prediction)
        calibration_errors.append(observed - mean_prediction)
        censoring_survival.append(censor_at_horizon)
        case_counts.append(len(cases))
        control_counts.append(len(controls))
        horizon_predictions = tuple(row[column] for row in predictions)
        grouped_calibration.append(
            _survival_calibration_groups(
                time_values,
                event_values,
                horizon_predictions,
                weight_values,
                horizon=horizon,
                group_count=calibration_groups,
            )
        )
        threshold_metrics.extend(
            _survival_threshold_metrics(
                horizon_predictions,
                tuple(case_weights),
                tuple(control_weights),
                horizon=horizon,
                thresholds=threshold_values,
            )
        )

    integrated = _integrated_metric(horizon_values, tuple(brier_scores))
    integrated_auc = (
        None
        if any(value is None for value in aucs)
        else _integrated_metric(
            horizon_values,
            tuple(cast(float, value) for value in aucs),
        )
    )
    integrated_calibration = _integrated_metric(
        horizon_values, tuple(abs(value) for value in calibration_errors)
    )
    dxy = tuple(None if value is None else 2.0 * value - 1.0 for value in aucs)
    return SurvivalValidationResult(
        horizons=horizon_values,
        brier_scores=tuple(brier_scores),
        aucs=tuple(aucs),
        dxy=dxy,
        observed_survival=tuple(observed_survival),
        mean_predicted_survival=tuple(mean_predictions),
        calibration_errors=tuple(calibration_errors),
        censoring_survival=tuple(censoring_survival),
        case_counts=tuple(case_counts),
        control_counts=tuple(control_counts),
        integrated_brier_score=integrated,
        integrated_auc=integrated_auc,
        integrated_absolute_calibration_error=integrated_calibration,
        calibration_groups=tuple(grouped_calibration),
        threshold_metrics=tuple(threshold_metrics),
        n_observations=len(time_values),
        total_weight=total_weight,
    )


__all__ = [
    "SurvivalCalibrationGroup",
    "SurvivalThresholdMetrics",
    "SurvivalValidationResult",
    "validate_survival_predictions",
]
