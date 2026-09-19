"""Run the locked Phase 5 survival-model simulation evidence package."""

# pyright: reportUnknownMemberType=false

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
import platform
import subprocess
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias, cast

import numpy as np
import numpy.typing as npt

from holocron.exceptions import HolocronError
from holocron.models import (
    SurvivalResponse,
    fit_cph,
    fit_npsurv,
    fit_psm,
    validate_survival_predictions,
)
from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "governance/phase-5-simulation-plan.json"
PLAN_SCHEMA = ROOT / "schemas/phase-5-simulation-plan.schema.json"
REPORT_SCHEMA = ROOT / "schemas/phase-5-simulation-report.schema.json"
DEFAULT_OUTPUT = ROOT / ".work/phase-5-evidence/simulation-report.json"

FloatVector: TypeAlias = npt.NDArray[np.float64]
ScenarioRunner: TypeAlias = Callable[
    [dict[str, JsonValue]],
    tuple[dict[str, float], list[dict[str, JsonValue]], list[int]],
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: JsonValue) -> str:
    encoded = json.dumps(
        value, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return bool(result.stdout)


def _environment() -> dict[str, JsonValue]:
    return {
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "operating_system": platform.system(),
        "machine": platform.machine(),
    }


def _number(value: JsonValue, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    return float(value)


def _parameters(scenario: dict[str, JsonValue]) -> dict[str, float]:
    raw = require_object(scenario["parameters"], name="scenario.parameters")
    return {
        name: _number(value, name=f"scenario.parameters.{name}")
        for name, value in raw.items()
    }


def _setup(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], int, int, np.random.Generator]:
    replications = cast(int, scenario["replications"])
    sample_size = cast(int, scenario["sample_size"])
    return (
        _parameters(scenario),
        replications,
        sample_size,
        np.random.default_rng(cast(int, scenario["seed"])),
    )


def _features(values: FloatVector) -> tuple[tuple[float], ...]:
    return tuple((float(value),) for value in values)


def _values(values: npt.NDArray[Any]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _events(values: npt.NDArray[Any]) -> tuple[int, ...]:
    return tuple(int(value) for value in values)


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _rmse(values: list[float], target: float) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.sqrt(np.mean((array - target) ** 2)))


def _covered(estimate: float, variance: float, target: float) -> float:
    standard_error = math.sqrt(max(variance, 0.0))
    return float(
        estimate - 1.959963984540054 * standard_error
        <= target
        <= estimate + 1.959963984540054 * standard_error
    )


def _event_and_censor_times(
    rng: np.random.Generator,
    x: FloatVector,
    *,
    slope: float,
    baseline_hazard: FloatVector | float,
    censor_hazard: float,
    offsets: FloatVector | None = None,
) -> tuple[FloatVector, npt.NDArray[np.int64]]:
    predictor = slope * x
    if offsets is not None:
        predictor = predictor + offsets
    hazard = np.asarray(baseline_hazard, dtype=np.float64) * np.exp(predictor)
    event_time = rng.exponential(1.0 / hazard)
    censor_time = rng.exponential(1.0 / censor_hazard, size=x.size)
    event = event_time <= censor_time
    observed = np.minimum(event_time, censor_time)
    return observed.astype(np.float64), event.astype(np.int64)


def _cox_continuous(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters, replications, sample_size, rng = _setup(scenario)
    slopes: list[float] = []
    coverage: list[float] = []
    censoring: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        time, event = _event_and_censor_times(
            rng,
            x,
            slope=parameters["slope"],
            baseline_hazard=parameters["baseline_hazard"],
            censor_hazard=parameters["censor_hazard"],
        )
        try:
            result = fit_cph(_values(time), _events(event), _features(x))
        except HolocronError:
            failures.append(replication)
            continue
        slope = result.coefficients[0]
        covered = _covered(slope, result.covariance[0][0], parameters["slope"])
        censor_fraction = 1.0 - float(np.mean(event))
        slopes.append(slope)
        coverage.append(covered)
        censoring.append(censor_fraction)
        details.append(
            {
                "replication": replication,
                "slope": slope,
                "covered": bool(covered),
                "censoring_fraction": censor_fraction,
            }
        )
    return (
        {
            "slope_abs_bias": abs(_mean(slopes) - parameters["slope"]),
            "slope_rmse": _rmse(slopes, parameters["slope"]),
            "slope_coverage": _mean(coverage),
            "mean_censoring_fraction": _mean(censoring),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _cox_tied(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters, replications, sample_size, rng = _setup(scenario)
    efron_slopes: list[float] = []
    breslow_slopes: list[float] = []
    differences: list[float] = []
    tied_fractions: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    width = parameters["rounding_width"]
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        time, event = _event_and_censor_times(
            rng,
            x,
            slope=parameters["slope"],
            baseline_hazard=parameters["baseline_hazard"],
            censor_hazard=parameters["censor_hazard"],
        )
        rounded = np.maximum(width, np.ceil(time / width) * width)
        try:
            efron = fit_cph(
                _values(rounded), _events(event), _features(x), method="efron"
            )
            breslow = fit_cph(
                _values(rounded), _events(event), _features(x), method="breslow"
            )
        except HolocronError:
            failures.append(replication)
            continue
        event_times = [float(value) for value in rounded[event == 1]]
        counts = Counter(event_times)
        tied = sum(counts[value] > 1 for value in event_times) / len(event_times)
        difference = abs(efron.coefficients[0] - breslow.coefficients[0])
        efron_slopes.append(efron.coefficients[0])
        breslow_slopes.append(breslow.coefficients[0])
        differences.append(difference)
        tied_fractions.append(tied)
        details.append(
            {
                "replication": replication,
                "efron_slope": efron.coefficients[0],
                "breslow_slope": breslow.coefficients[0],
                "absolute_difference": difference,
                "tied_event_fraction": tied,
            }
        )
    return (
        {
            "efron_slope_abs_bias": abs(_mean(efron_slopes) - parameters["slope"]),
            "breslow_slope_abs_bias": abs(_mean(breslow_slopes) - parameters["slope"]),
            "mean_abs_coefficient_difference": _mean(differences),
            "mean_tied_event_fraction": _mean(tied_fractions),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _cox_stratified(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters, replications, sample_size, rng = _setup(scenario)
    slopes: list[float] = []
    coverage: list[float] = []
    ordering: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    strata = tuple(
        "A" if index < sample_size // 2 else "B" for index in range(sample_size)
    )
    baseline = np.asarray(
        [
            parameters["baseline_hazard_a"]
            if value == "A"
            else parameters["baseline_hazard_b"]
            for value in strata
        ],
        dtype=np.float64,
    )
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        offsets = rng.normal(scale=parameters["offset_sigma"], size=sample_size)
        time, event = _event_and_censor_times(
            rng,
            x,
            slope=parameters["slope"],
            baseline_hazard=baseline,
            censor_hazard=parameters["censor_hazard"],
            offsets=offsets,
        )
        try:
            result = fit_cph(
                _values(time),
                _events(event),
                _features(x),
                strata=strata,
                offsets=_values(offsets),
            )
            predicted = result.predict_survival(
                ((0.0,), (0.0,)),
                (parameters["evaluation_time"],),
                strata=("A", "B"),
            )
        except HolocronError:
            failures.append(replication)
            continue
        slope = result.coefficients[0]
        covered = _covered(slope, result.covariance[0][0], parameters["slope"])
        ordered = float(predicted[0][0] > predicted[1][0])
        slopes.append(slope)
        coverage.append(covered)
        ordering.append(ordered)
        details.append(
            {
                "replication": replication,
                "slope": slope,
                "covered": bool(covered),
                "baseline_ordered": bool(ordered),
            }
        )
    return (
        {
            "slope_abs_bias": abs(_mean(slopes) - parameters["slope"]),
            "slope_rmse": _rmse(slopes, parameters["slope"]),
            "slope_coverage": _mean(coverage),
            "baseline_ordering_rate": _mean(ordering),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _weibull_times(
    rng: np.random.Generator,
    x: FloatVector,
    *,
    intercept: float,
    slope: float,
    scale: float,
) -> FloatVector:
    extreme_value = np.log(rng.exponential(size=x.size))
    return np.exp(intercept + slope * x + scale * extreme_value).astype(np.float64)


def _psm_right(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters, replications, sample_size, rng = _setup(scenario)
    slopes: list[float] = []
    scales: list[float] = []
    coverage: list[float] = []
    censoring: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        event_time = _weibull_times(
            rng,
            x,
            intercept=parameters["intercept"],
            slope=parameters["slope"],
            scale=parameters["scale"],
        )
        censor_time = rng.exponential(
            1.0 / parameters["censor_hazard"], size=sample_size
        )
        event = event_time <= censor_time
        time = np.minimum(event_time, censor_time)
        try:
            result = fit_psm(_values(time), _events(event), _features(x))
        except HolocronError:
            failures.append(replication)
            continue
        assert result.scale is not None
        slope = result.coefficients[1]
        covered = _covered(slope, result.covariance[1][1], parameters["slope"])
        censor_fraction = 1.0 - float(np.mean(event))
        slopes.append(slope)
        scales.append(result.scale)
        coverage.append(covered)
        censoring.append(censor_fraction)
        details.append(
            {
                "replication": replication,
                "slope": slope,
                "scale": result.scale,
                "covered": bool(covered),
                "censoring_fraction": censor_fraction,
            }
        )
    return (
        {
            "slope_abs_bias": abs(_mean(slopes) - parameters["slope"]),
            "slope_rmse": _rmse(slopes, parameters["slope"]),
            "slope_coverage": _mean(coverage),
            "scale_abs_bias": abs(_mean(scales) - parameters["scale"]),
            "mean_censoring_fraction": _mean(censoring),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _psm_mixed(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters, replications, sample_size, rng = _setup(scenario)
    slopes: list[float] = []
    scales: list[float] = []
    left_fractions: list[float] = []
    interval_fractions: list[float] = []
    right_fractions: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        event_time = _weibull_times(
            rng,
            x,
            intercept=parameters["intercept"],
            slope=parameters["slope"],
            scale=parameters["scale"],
        )
        lower = np.empty(sample_size, dtype=np.float64)
        upper = np.empty(sample_size, dtype=np.float64)
        kinds: list[str] = []
        for index, time in enumerate(event_time):
            if time <= parameters["left_limit"]:
                lower[index], upper[index] = -math.inf, parameters["left_limit"]
                kinds.append("left")
            elif time >= parameters["right_limit"]:
                lower[index], upper[index] = parameters["right_limit"], math.inf
                kinds.append("right")
            elif rng.random() < parameters["exact_probability"]:
                lower[index] = upper[index] = time
                kinds.append("exact")
            else:
                left = (
                    math.floor(time / parameters["interval_width"])
                    * parameters["interval_width"]
                )
                lower[index], upper[index] = left, left + parameters["interval_width"]
                kinds.append("interval")
        try:
            result = fit_psm(
                SurvivalResponse.from_intervals(lower, upper), _features(x)
            )
        except HolocronError:
            failures.append(replication)
            continue
        assert result.scale is not None
        counts = Counter(kinds)
        slopes.append(result.coefficients[1])
        scales.append(result.scale)
        left_fractions.append(counts["left"] / sample_size)
        interval_fractions.append(counts["interval"] / sample_size)
        right_fractions.append(counts["right"] / sample_size)
        details.append(
            {
                "replication": replication,
                "slope": result.coefficients[1],
                "scale": result.scale,
                "left_fraction": counts["left"] / sample_size,
                "interval_fraction": counts["interval"] / sample_size,
                "right_fraction": counts["right"] / sample_size,
            }
        )
    return (
        {
            "slope_abs_bias": abs(_mean(slopes) - parameters["slope"]),
            "slope_rmse": _rmse(slopes, parameters["slope"]),
            "scale_abs_bias": abs(_mean(scales) - parameters["scale"]),
            "mean_left_fraction": _mean(left_fractions),
            "mean_interval_fraction": _mean(interval_fractions),
            "mean_right_fraction": _mean(right_fractions),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _kaplan_meier(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters, replications, sample_size, rng = _setup(scenario)
    estimates: list[float] = []
    coverage: list[float] = []
    censoring: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    horizon = parameters["evaluation_time"]
    target = math.exp(-parameters["event_hazard"] * horizon)
    for replication in range(replications):
        event_time = rng.exponential(1.0 / parameters["event_hazard"], size=sample_size)
        censor_time = rng.exponential(
            1.0 / parameters["censor_hazard"], size=sample_size
        )
        event = event_time <= censor_time
        time = np.minimum(event_time, censor_time)
        try:
            result = fit_npsurv(_values(time), _events(event))
        except HolocronError:
            failures.append(replication)
            continue
        index = bisect.bisect_right(result.time, horizon) - 1
        estimate = 1.0 if index < 0 else result.survival[index]
        lower = 1.0 if index < 0 else result.lower[index]
        upper = 1.0 if index < 0 else result.upper[index]
        covered = float(lower <= target <= upper)
        censor_fraction = 1.0 - float(np.mean(event))
        estimates.append(estimate)
        coverage.append(covered)
        censoring.append(censor_fraction)
        details.append(
            {
                "replication": replication,
                "survival": estimate,
                "lower": lower,
                "upper": upper,
                "covered": bool(covered),
                "censoring_fraction": censor_fraction,
            }
        )
    return (
        {
            "survival_abs_bias": abs(_mean(estimates) - target),
            "survival_rmse": _rmse(estimates, target),
            "interval_coverage": _mean(coverage),
            "mean_censoring_fraction": _mean(censoring),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _complete_auc(
    event_time: FloatVector, predictions: FloatVector, horizon: float
) -> float:
    cases = predictions[event_time <= horizon]
    controls = np.sort(predictions[event_time > horizon])
    if cases.size == 0 or controls.size == 0:
        raise ValueError("complete-data AUC requires cases and controls")
    concordant = 0.0
    values = controls.tolist()
    for prediction in cases:
        left = bisect.bisect_left(values, float(prediction))
        right = bisect.bisect_right(values, float(prediction))
        concordant += controls.size - right + 0.5 * (right - left)
    return concordant / (cases.size * controls.size)


def _validation(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters, replications, sample_size, rng = _setup(scenario)
    horizons = (
        parameters["horizon_1"],
        parameters["horizon_2"],
        parameters["horizon_3"],
    )
    brier_differences: list[float] = []
    auc_differences: list[float] = []
    calibration_errors: list[float] = []
    integrated_differences: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        hazard = parameters["baseline_hazard"] * np.exp(parameters["slope"] * x)
        event_time = rng.exponential(1.0 / hazard)
        censor_time = rng.exponential(
            1.0 / parameters["censor_hazard"], size=sample_size
        )
        event = event_time <= censor_time
        observed = np.minimum(event_time, censor_time)
        prediction_array = np.column_stack(
            tuple(np.exp(-hazard * horizon) for horizon in horizons)
        )
        predictions = tuple(
            tuple(float(value) for value in row) for row in prediction_array
        )
        try:
            result = validate_survival_predictions(
                _values(observed), _events(event), predictions, horizons
            )
            complete_brier = tuple(
                float(
                    np.mean(
                        (
                            (event_time > horizon).astype(np.float64)
                            - prediction_array[:, column]
                        )
                        ** 2
                    )
                )
                for column, horizon in enumerate(horizons)
            )
            complete_auc = tuple(
                _complete_auc(event_time, prediction_array[:, column], horizon)
                for column, horizon in enumerate(horizons)
            )
        except (HolocronError, ValueError):
            failures.append(replication)
            continue
        complete_integrated = sum(
            (right_time - left_time) * (left_score + right_score) * 0.5
            for left_time, right_time, left_score, right_score in zip(
                horizons[:-1],
                horizons[1:],
                complete_brier[:-1],
                complete_brier[1:],
                strict=True,
            )
        ) / (horizons[-1] - horizons[0])
        assert result.integrated_brier_score is not None
        replication_brier = _mean(
            [
                actual - expected
                for actual, expected in zip(
                    result.brier_scores, complete_brier, strict=True
                )
            ]
        )
        replication_auc = _mean(
            [
                actual - expected
                for actual, expected in zip(result.aucs, complete_auc, strict=True)
                if actual is not None
            ]
        )
        brier_differences.append(replication_brier)
        auc_differences.append(replication_auc)
        calibration_errors.extend(abs(value) for value in result.calibration_errors)
        integrated_differences.append(
            result.integrated_brier_score - complete_integrated
        )
        details.append(
            {
                "replication": replication,
                "mean_brier_difference": replication_brier,
                "mean_auc_difference": replication_auc,
                "mean_abs_calibration_error": _mean(
                    [abs(value) for value in result.calibration_errors]
                ),
                "integrated_brier_difference": (
                    result.integrated_brier_score - complete_integrated
                ),
            }
        )
    return (
        {
            "brier_abs_bias": abs(_mean(brier_differences)),
            "auc_abs_bias": abs(_mean(auc_differences)),
            "mean_abs_calibration_error": _mean(calibration_errors),
            "integrated_brier_abs_bias": abs(_mean(integrated_differences)),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


SCENARIO_RUNNERS: dict[str, ScenarioRunner] = {
    "cox-continuous-recovery": _cox_continuous,
    "cox-tied-methods": _cox_tied,
    "cox-stratified-offset-recovery": _cox_stratified,
    "psm-weibull-right-recovery": _psm_right,
    "psm-weibull-mixed-censoring": _psm_mixed,
    "kaplan-meier-recovery": _kaplan_meier,
    "survival-validation-recovery": _validation,
}


def _metric_records(
    metrics: dict[str, float], acceptance: dict[str, JsonValue]
) -> tuple[list[dict[str, JsonValue]], bool]:
    if set(metrics) != set(acceptance):
        raise AssertionError(
            f"simulation metric contract differs: actual={sorted(metrics)}, "
            f"planned={sorted(acceptance)}"
        )
    records: list[dict[str, JsonValue]] = []
    all_passed = True
    for name, value in metrics.items():
        bounds = require_object(acceptance[name], name=f"acceptance.{name}")
        minimum = (
            _number(bounds["minimum"], name=f"acceptance.{name}.minimum")
            if "minimum" in bounds
            else None
        )
        maximum = (
            _number(bounds["maximum"], name=f"acceptance.{name}.maximum")
            if "maximum" in bounds
            else None
        )
        passed = (minimum is None or value >= minimum) and (
            maximum is None or value <= maximum
        )
        all_passed &= passed
        records.append(
            {
                "name": name,
                "value": value,
                "minimum": minimum,
                "maximum": maximum,
                "outcome": "passed" if passed else "failed",
            }
        )
    return records, all_passed


def run_simulations(
    *, revision: str, dirty: bool, evaluated_at: datetime
) -> dict[str, JsonValue]:
    """Execute the locked simulations and return schema-valid evidence."""
    raw_plan = load_json(PLAN)
    validate_document(raw_plan, PLAN_SCHEMA)
    plan = require_object(raw_plan, name=str(PLAN))
    scenario_records: list[dict[str, JsonValue]] = []
    total_replications = 0
    all_passed = True
    seen: set[str] = set()
    for raw_scenario in require_array(plan["scenarios"], name="plan.scenarios"):
        scenario = require_object(raw_scenario, name="simulation scenario")
        scenario_id = cast(str, scenario["scenario_id"])
        if scenario_id in seen or scenario_id not in SCENARIO_RUNNERS:
            raise ValueError(f"invalid simulation scenario: {scenario_id}")
        seen.add(scenario_id)
        metrics, details, failures = SCENARIO_RUNNERS[scenario_id](scenario)
        replications = cast(int, scenario["replications"])
        total_replications += replications
        metric_records, passed = _metric_records(
            metrics,
            require_object(scenario["acceptance"], name="scenario.acceptance"),
        )
        all_passed &= passed
        scenario_records.append(
            {
                "scenario_id": scenario_id,
                "kind": scenario["kind"],
                "seed": scenario["seed"],
                "replications": replications,
                "successful_replications": replications - len(failures),
                "failed_replications": cast(list[JsonValue], failures),
                "replication_sha256": _digest(cast(JsonValue, details)),
                "metrics": cast(list[JsonValue], metric_records),
                "outcome": "passed" if passed else "failed",
            }
        )
    if seen != set(SCENARIO_RUNNERS):
        raise AssertionError("simulation plan does not cover every scenario runner")
    review = require_object(plan["independent_review"], name="independent_review")
    review_approved = review["status"] == "approved"
    report: dict[str, JsonValue] = {
        "schema_version": "holocron-phase-5-simulation-report/v1",
        "evaluated_at_utc": evaluated_at.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "plan_id": plan["plan_id"],
        "plan_sha256": _sha256(PLAN),
        "source": {"code_revision": revision, "working_tree_dirty": dirty},
        "environment": _environment(),
        "detail_policy": plan["detail_policy"],
        "total_replications": total_replications,
        "scenarios": cast(list[JsonValue], scenario_records),
        "platform_policy": {
            "required_platforms": plan["required_platforms"],
            "ci_artifact": (
                "phase-5-platform-evidence-${runner.os}-${runner.arch}-${github.sha}"
            ),
        },
        "independent_review": review,
        "technical_status": "pass" if all_passed else "fail",
        "phase_5_exit_gate": (
            "closed"
            if all_passed and review_approved
            else "awaiting-independent-review"
            if all_passed
            else "failed"
        ),
    }
    validate_document(report, REPORT_SCHEMA)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-clean", action="store_true")
    return parser


def main() -> None:
    args = _parser().parse_args()
    dirty = _dirty()
    if args.require_clean and dirty:
        raise SystemExit("Phase 5 clean evidence requires a clean working tree")
    report = run_simulations(
        revision=_revision(), dirty=dirty, evaluated_at=datetime.now(UTC)
    )
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, allow_nan=False, indent=2) + "\n")
    scenarios = cast(list[JsonValue], report["scenarios"])
    print(
        f"Phase 5 simulation evidence: scenarios={len(scenarios)}, "
        f"replications={report['total_replications']}, "
        f"technical={report['technical_status']}, gate={report['phase_5_exit_gate']}, "
        f"output={output.relative_to(ROOT)}"
    )
    if report["technical_status"] != "pass":
        raise SystemExit("Phase 5 simulation evidence failed")


if __name__ == "__main__":
    main()
