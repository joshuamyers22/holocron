"""Run the locked Phase 3 simulations and numerical edge-case corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist
from typing import TypeAlias, cast

import numpy as np
import numpy.typing as npt

from holocron.exceptions import (
    ConvergenceError,
    HolocronError,
    InputValidationError,
    NumericalError,
    RankDeficiencyError,
    SeparationError,
)
from holocron.models import (
    BinaryLogisticResult,
    CovarianceEstimate,
    OlsResult,
    PenalizedResult,
    bootstrap_covariance,
    fit_glm,
    fit_lrm,
    fit_ols,
    fit_penalized_lrm,
    fit_penalized_ols,
    robust_covariance,
    summarize,
)
from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "governance/phase-3-simulation-plan.json"
CORPUS = ROOT / "reference/phase-3-edge-cases.json"
PLAN_SCHEMA = ROOT / "schemas/phase-3-simulation-plan.schema.json"
CORPUS_SCHEMA = ROOT / "schemas/phase-3-edge-corpus.schema.json"
SIMULATION_REPORT_SCHEMA = ROOT / "schemas/phase-3-simulation-report.schema.json"
EDGE_REPORT_SCHEMA = ROOT / "schemas/phase-3-edge-report.schema.json"
DEFAULT_SIMULATION_OUTPUT = ROOT / ".work/phase-3-evidence/simulation-report.json"
DEFAULT_EDGE_OUTPUT = ROOT / ".work/phase-3-evidence/numerical-edge-report.json"

FloatVector: TypeAlias = npt.NDArray[np.float64]
FloatMatrix: TypeAlias = npt.NDArray[np.float64]
FitResult: TypeAlias = OlsResult | BinaryLogisticResult | PenalizedResult
EvidenceResult: TypeAlias = FitResult | CovarianceEstimate
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


def _current_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _working_tree_dirty() -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return bool(completed.stdout)


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


def _integer(value: JsonValue, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _numeric_parameters(scenario: dict[str, JsonValue]) -> dict[str, float]:
    raw = require_object(scenario["parameters"], name="scenario.parameters")
    return {
        name: _number(value, name=f"scenario.parameters.{name}")
        for name, value in raw.items()
    }


def _features(values: FloatVector | FloatMatrix) -> tuple[tuple[float, ...], ...]:
    matrix = values[:, None] if values.ndim == 1 else values
    return tuple(tuple(float(item) for item in row) for row in matrix)


def _binary(rng: np.random.Generator, probabilities: FloatVector) -> tuple[int, ...]:
    values = rng.binomial(1, probabilities)
    return tuple(int(value) for value in values)


def _expit(values: FloatVector) -> FloatVector:
    output = np.empty_like(values)
    positive = values >= 0.0
    output[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponential = np.exp(values[~positive])
    output[~positive] = exponential / (1.0 + exponential)
    return output


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _rmse(values: list[float], target: float) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.sqrt(np.mean((array - target) ** 2)))


def _auc(response: tuple[int, ...], probabilities: tuple[float, ...]) -> float:
    pairs = sorted(zip(probabilities, response, strict=True), key=lambda item: item[0])
    positive_count = sum(response)
    negative_count = len(response) - positive_count
    rank_sum = 0.0
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][0] == pairs[index][0]:
            end += 1
        average_rank = 0.5 * ((index + 1) + end)
        rank_sum += average_rank * sum(item[1] for item in pairs[index:end])
        index = end
    return (rank_sum - positive_count * (positive_count + 1) / 2.0) / (
        positive_count * negative_count
    )


def _ols_gaussian(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters = _numeric_parameters(scenario)
    replications = int(cast(int, scenario["replications"]))
    sample_size = int(cast(int, scenario["sample_size"]))
    rng = np.random.default_rng(cast(int, scenario["seed"]))
    estimates: list[tuple[float, float]] = []
    coverage: list[float] = []
    failures: list[int] = []
    details: list[dict[str, JsonValue]] = []
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        y = (
            parameters["intercept"]
            + parameters["slope"] * x
            + rng.normal(scale=parameters["sigma"], size=sample_size)
        )
        try:
            result = fit_ols(y, _features(x), feature_names=("x",))
            inference = summarize(result).coefficients[1]
        except HolocronError:
            failures.append(replication)
            continue
        estimates.append((result.coefficients[0], result.coefficients[1]))
        covered = float(inference.lower <= parameters["slope"] <= inference.upper)
        coverage.append(covered)
        details.append(
            {
                "replication": replication,
                "intercept": result.coefficients[0],
                "slope": result.coefficients[1],
                "slope_standard_error": inference.standard_error,
                "covered": bool(covered),
            }
        )
    intercepts = [value[0] for value in estimates]
    slopes = [value[1] for value in estimates]
    metrics = {
        "intercept_abs_bias": abs(_mean(intercepts) - parameters["intercept"]),
        "slope_abs_bias": abs(_mean(slopes) - parameters["slope"]),
        "slope_rmse": _rmse(slopes, parameters["slope"]),
        "slope_coverage": _mean(coverage),
        "failure_rate": len(failures) / replications,
    }
    return metrics, details, failures


def _ols_null(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters = _numeric_parameters(scenario)
    replications = int(cast(int, scenario["replications"]))
    sample_size = int(cast(int, scenario["sample_size"]))
    rng = np.random.default_rng(cast(int, scenario["seed"]))
    rejected: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        y = parameters["intercept"] + rng.normal(
            scale=parameters["sigma"], size=sample_size
        )
        try:
            inference = summarize(
                fit_ols(y, _features(x), feature_names=("x",))
            ).coefficients[1]
        except HolocronError:
            failures.append(replication)
            continue
        is_rejected = inference.p_value < 0.05
        rejected.append(float(is_rejected))
        details.append(
            {
                "replication": replication,
                "p_value": inference.p_value,
                "rejected": is_rejected,
            }
        )
    return (
        {
            "type_i_error": _mean(rejected),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _binary_recovery(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters = _numeric_parameters(scenario)
    replications = int(cast(int, scenario["replications"]))
    sample_size = int(cast(int, scenario["sample_size"]))
    validation_size = int(parameters["validation_size"])
    rng = np.random.default_rng(cast(int, scenario["seed"]))
    glm_slopes: list[float] = []
    lrm_slopes: list[float] = []
    glm_coverage: list[float] = []
    lrm_coverage: list[float] = []
    coefficient_differences: list[float] = []
    calibration_intercepts: list[float] = []
    calibration_slopes: list[float] = []
    briers: list[float] = []
    aucs: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    normal_limit = NormalDist().inv_cdf(0.975)
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        probabilities = _expit(parameters["intercept"] + parameters["slope"] * x)
        y = _binary(rng, probabilities)
        validation_x = rng.normal(size=validation_size)
        validation_probability = _expit(
            parameters["intercept"] + parameters["slope"] * validation_x
        )
        validation_y = _binary(rng, validation_probability)
        try:
            glm = fit_glm(y, _features(x), family="binomial", feature_names=("x",))
            lrm = fit_lrm(y, _features(x), feature_names=("x",))
            assert isinstance(glm, BinaryLogisticResult)
            glm_se = math.sqrt(glm.covariance[1][1])
            lrm_se = math.sqrt(lrm.covariance[1][1])
            validation_linear = glm.coefficients[0] + glm.coefficients[1] * validation_x
            validation_predictions = _expit(validation_linear)
            calibration = fit_lrm(
                validation_y,
                _features(validation_linear),
                feature_names=("linear_predictor",),
            )
        except HolocronError:
            failures.append(replication)
            continue
        glm_slopes.append(glm.coefficients[1])
        lrm_slopes.append(lrm.coefficients[1])
        glm_coverage.append(
            float(
                abs(glm.coefficients[1] - parameters["slope"]) <= normal_limit * glm_se
            )
        )
        lrm_coverage.append(
            float(
                abs(lrm.coefficients[1] - parameters["slope"]) <= normal_limit * lrm_se
            )
        )
        difference = max(
            abs(left - right)
            for left, right in zip(glm.coefficients, lrm.coefficients, strict=True)
        )
        coefficient_differences.append(difference)
        calibration_intercepts.append(calibration.coefficients[0])
        calibration_slopes.append(calibration.coefficients[1])
        brier = float(
            np.mean(
                (np.asarray(validation_y, dtype=np.float64) - validation_predictions)
                ** 2
            )
        )
        auc = _auc(
            validation_y, tuple(float(value) for value in validation_predictions)
        )
        briers.append(brier)
        aucs.append(auc)
        details.append(
            {
                "replication": replication,
                "glm_slope": glm.coefficients[1],
                "lrm_slope": lrm.coefficients[1],
                "calibration_intercept": calibration.coefficients[0],
                "calibration_slope": calibration.coefficients[1],
                "brier": brier,
                "auc": auc,
            }
        )
    metrics = {
        "glm_slope_abs_bias": abs(_mean(glm_slopes) - parameters["slope"]),
        "glm_slope_rmse": _rmse(glm_slopes, parameters["slope"]),
        "glm_slope_coverage": _mean(glm_coverage),
        "lrm_slope_abs_bias": abs(_mean(lrm_slopes) - parameters["slope"]),
        "lrm_slope_rmse": _rmse(lrm_slopes, parameters["slope"]),
        "lrm_slope_coverage": _mean(lrm_coverage),
        "glm_lrm_max_coefficient_difference": max(coefficient_differences),
        "calibration_intercept_abs_mean": abs(_mean(calibration_intercepts)),
        "calibration_slope_abs_error": abs(_mean(calibration_slopes) - 1.0),
        "brier_mean": _mean(briers),
        "auc_mean": _mean(aucs),
        "failure_rate": len(failures) / replications,
    }
    return metrics, details, failures


def _binary_null(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters = _numeric_parameters(scenario)
    replications = int(cast(int, scenario["replications"]))
    sample_size = int(cast(int, scenario["sample_size"]))
    rng = np.random.default_rng(cast(int, scenario["seed"]))
    glm_rejected: list[float] = []
    lrm_rejected: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    normal = NormalDist()
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        probabilities = _expit(np.full(sample_size, parameters["intercept"]))
        y = _binary(rng, probabilities)
        try:
            glm = fit_glm(y, _features(x), family="binomial", feature_names=("x",))
            lrm = fit_lrm(y, _features(x), feature_names=("x",))
            assert isinstance(glm, BinaryLogisticResult)
        except HolocronError:
            failures.append(replication)
            continue
        glm_z = glm.coefficients[1] / math.sqrt(glm.covariance[1][1])
        lrm_z = lrm.coefficients[1] / math.sqrt(lrm.covariance[1][1])
        glm_p = 2.0 * normal.cdf(-abs(glm_z))
        lrm_p = 2.0 * normal.cdf(-abs(lrm_z))
        glm_rejected.append(float(glm_p < 0.05))
        lrm_rejected.append(float(lrm_p < 0.05))
        details.append(
            {
                "replication": replication,
                "glm_p_value": glm_p,
                "lrm_p_value": lrm_p,
            }
        )
    return (
        {
            "glm_type_i_error": _mean(glm_rejected),
            "lrm_type_i_error": _mean(lrm_rejected),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _clustered_covariance(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters = _numeric_parameters(scenario)
    replications = int(cast(int, scenario["replications"]))
    cluster_count = int(parameters["cluster_count"])
    cluster_size = int(parameters["cluster_size"])
    rng = np.random.default_rng(cast(int, scenario["seed"]))
    cluster_ids = tuple(
        cluster for cluster in range(cluster_count) for _ in range(cluster_size)
    )
    robust_covered: list[float] = []
    naive_covered: list[float] = []
    robust_ses: list[float] = []
    slopes: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    limit = NormalDist().inv_cdf(0.975)
    for replication in range(replications):
        cluster_x = rng.normal(size=cluster_count)
        individual_x = rng.normal(scale=0.3, size=cluster_count * cluster_size)
        x: FloatVector = (
            np.repeat(  # pyright: ignore[reportUnknownMemberType]
                cluster_x, cluster_size
            )
            + individual_x
        )
        cluster_error = rng.normal(
            scale=parameters["cluster_sigma"], size=cluster_count
        )
        error: FloatVector = np.repeat(  # pyright: ignore[reportUnknownMemberType]
            cluster_error, cluster_size
        ) + rng.normal(scale=parameters["noise_sigma"], size=x.size)
        y = parameters["intercept"] + parameters["slope"] * x + error
        try:
            result = fit_ols(y, _features(x), feature_names=("x",))
            robust = robust_covariance(result, y, _features(x), clusters=cluster_ids)
        except HolocronError:
            failures.append(replication)
            continue
        slope = result.coefficients[1]
        naive_se = math.sqrt(result.covariance[1][1])
        robust_se = math.sqrt(robust.matrix[1][1])
        slopes.append(slope)
        robust_ses.append(robust_se)
        robust_covered.append(
            float(abs(slope - parameters["slope"]) <= limit * robust_se)
        )
        naive_covered.append(
            float(abs(slope - parameters["slope"]) <= limit * naive_se)
        )
        details.append(
            {
                "replication": replication,
                "slope": slope,
                "naive_standard_error": naive_se,
                "robust_standard_error": robust_se,
            }
        )
    robust_coverage = _mean(robust_covered)
    naive_coverage = _mean(naive_covered)
    empirical_sd = float(np.std(np.asarray(slopes), ddof=1))
    return (
        {
            "robust_coverage": robust_coverage,
            "naive_coverage": naive_coverage,
            "coverage_gain": robust_coverage - naive_coverage,
            "robust_se_empirical_ratio": _mean(robust_ses) / empirical_sd,
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _bootstrap_variance(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters = _numeric_parameters(scenario)
    replications = int(cast(int, scenario["replications"]))
    sample_size = int(cast(int, scenario["sample_size"]))
    bootstrap_replicates = int(parameters["bootstrap_replicates"])
    rng = np.random.default_rng(cast(int, scenario["seed"]))
    slopes: list[float] = []
    variances: list[float] = []
    center_differences: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    for replication in range(replications):
        x = rng.normal(size=sample_size)
        y = (
            parameters["intercept"]
            + parameters["slope"] * x
            + rng.normal(scale=parameters["sigma"], size=sample_size)
        )
        try:
            result = fit_ols(y, _features(x), feature_names=("x",))
            estimate = bootstrap_covariance(
                result,
                y,
                _features(x),
                replicates=bootstrap_replicates,
                seed=int(rng.integers(0, 2**63 - 1)),
            )
        except HolocronError:
            failures.append(replication)
            continue
        assert estimate.coefficient_mean is not None
        slopes.append(result.coefficients[1])
        variances.append(estimate.matrix[1][1])
        center_difference = estimate.coefficient_mean[1] - result.coefficients[1]
        center_differences.append(center_difference)
        details.append(
            {
                "replication": replication,
                "slope": result.coefficients[1],
                "bootstrap_variance": estimate.matrix[1][1],
                "bootstrap_center_difference": center_difference,
            }
        )
    empirical_variance = float(np.var(np.asarray(slopes), ddof=1))
    return (
        {
            "bootstrap_empirical_variance_ratio": _mean(variances) / empirical_variance,
            "bootstrap_centering_abs_bias": abs(_mean(center_differences)),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


def _penalized_collinearity(
    scenario: dict[str, JsonValue],
) -> tuple[dict[str, float], list[dict[str, JsonValue]], list[int]]:
    parameters = _numeric_parameters(scenario)
    replications = int(cast(int, scenario["replications"]))
    sample_size = int(cast(int, scenario["sample_size"]))
    rng = np.random.default_rng(cast(int, scenario["seed"]))
    unpenalized_errors: list[float] = []
    penalized_errors: list[float] = []
    unpenalized_prediction_errors: list[float] = []
    penalized_prediction_errors: list[float] = []
    effective_df: list[float] = []
    details: list[dict[str, JsonValue]] = []
    failures: list[int] = []
    correlation = parameters["correlation"]
    for replication in range(replications):
        x1 = rng.normal(size=sample_size)
        x2 = correlation * x1 + math.sqrt(1.0 - correlation**2) * rng.normal(
            size=sample_size
        )
        matrix = np.column_stack((x1, x2))  # pyright: ignore[reportUnknownMemberType]
        y = (
            parameters["intercept"]
            + parameters["slope_1"] * x1
            + parameters["slope_2"] * x2
            + rng.normal(scale=parameters["sigma"], size=sample_size)
        )
        validation_x1 = rng.normal(size=200)
        validation_x2 = correlation * validation_x1 + math.sqrt(
            1.0 - correlation**2
        ) * rng.normal(size=200)
        validation = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (validation_x1, validation_x2)
        )
        truth = (
            parameters["intercept"]
            + parameters["slope_1"] * validation_x1
            + parameters["slope_2"] * validation_x2
        )
        try:
            ordinary = fit_ols(y, _features(matrix), feature_names=("x1", "x2"))
            penalized = fit_penalized_ols(
                y,
                _features(matrix),
                feature_names=("x1", "x2"),
                penalty=parameters["penalty"],
            )
        except HolocronError:
            failures.append(replication)
            continue
        ordinary_error = (ordinary.coefficients[1] - parameters["slope_1"]) ** 2 + (
            ordinary.coefficients[2] - parameters["slope_2"]
        ) ** 2
        penalty_error = (penalized.coefficients[1] - parameters["slope_1"]) ** 2 + (
            penalized.coefficients[2] - parameters["slope_2"]
        ) ** 2
        ordinary_prediction_error = float(
            np.mean((np.asarray(ordinary.predict(_features(validation))) - truth) ** 2)
        )
        penalized_prediction_error = float(
            np.mean(
                (np.asarray(penalized.predict_response(_features(validation))) - truth)
                ** 2
            )
        )
        unpenalized_errors.append(ordinary_error)
        penalized_errors.append(penalty_error)
        unpenalized_prediction_errors.append(ordinary_prediction_error)
        penalized_prediction_errors.append(penalized_prediction_error)
        effective_df.append(penalized.effective_degrees_of_freedom)
        details.append(
            {
                "replication": replication,
                "ordinary_coefficient_error": ordinary_error,
                "penalized_coefficient_error": penalty_error,
                "ordinary_prediction_error": ordinary_prediction_error,
                "penalized_prediction_error": penalized_prediction_error,
                "effective_degrees_of_freedom": (
                    penalized.effective_degrees_of_freedom
                ),
            }
        )
    return (
        {
            "coefficient_mse_ratio": _mean(penalized_errors)
            / _mean(unpenalized_errors),
            "prediction_mse_ratio": _mean(penalized_prediction_errors)
            / _mean(unpenalized_prediction_errors),
            "mean_effective_df": _mean(effective_df),
            "failure_rate": len(failures) / replications,
        },
        details,
        failures,
    )


SCENARIO_RUNNERS: dict[str, ScenarioRunner] = {
    "ols-gaussian-recovery": _ols_gaussian,
    "ols-null-type-i": _ols_null,
    "binary-logit-recovery": _binary_recovery,
    "binary-null-type-i": _binary_null,
    "clustered-covariance-coverage": _clustered_covariance,
    "ols-bootstrap-variance": _bootstrap_variance,
    "penalized-ols-collinearity": _penalized_collinearity,
}


def _metric_records(
    metrics: dict[str, float], acceptance: dict[str, JsonValue]
) -> list[dict[str, JsonValue]]:
    if set(metrics) != set(acceptance):
        raise AssertionError(
            f"simulation metric contract differs: actual={sorted(metrics)}, "
            f"planned={sorted(acceptance)}"
        )
    records: list[dict[str, JsonValue]] = []
    for name in acceptance:
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
        value = metrics[name]
        passed = (minimum is None or value >= minimum) and (
            maximum is None or value <= maximum
        )
        if not passed:
            raise AssertionError(
                f"simulation metric failed: {name}={value}, "
                f"minimum={minimum}, maximum={maximum}"
            )
        records.append(
            {
                "name": name,
                "value": value,
                "minimum": minimum,
                "maximum": maximum,
                "outcome": "passed",
            }
        )
    return records


def run_simulations(
    *, revision: str, dirty: bool, evaluated_at: datetime
) -> dict[str, JsonValue]:
    """Execute every locked simulation and return schema-valid evidence."""
    raw_plan = load_json(PLAN)
    validate_document(raw_plan, PLAN_SCHEMA)
    plan = require_object(raw_plan, name=str(PLAN))
    raw_scenarios = require_array(plan["scenarios"], name="plan.scenarios")
    scenarios: list[dict[str, JsonValue]] = []
    total_replications = 0
    seen: set[str] = set()
    for raw_scenario in raw_scenarios:
        scenario = require_object(raw_scenario, name="simulation scenario")
        scenario_id = cast(str, scenario["scenario_id"])
        if scenario_id in seen:
            raise ValueError(f"duplicate simulation scenario: {scenario_id}")
        seen.add(scenario_id)
        runner = SCENARIO_RUNNERS.get(scenario_id)
        if runner is None:
            raise ValueError(f"unsupported simulation scenario: {scenario_id}")
        metrics, details, failures = runner(scenario)
        replications = cast(int, scenario["replications"])
        total_replications += replications
        metric_records = _metric_records(
            metrics,
            require_object(scenario["acceptance"], name="scenario.acceptance"),
        )
        scenario_record: dict[str, JsonValue] = {
            "scenario_id": scenario_id,
            "seed": cast(int, scenario["seed"]),
            "replications": replications,
            "successful_replications": replications - len(failures),
            "failed_replications": cast(list[JsonValue], failures),
            "replication_sha256": _digest(cast(JsonValue, details)),
            "metrics": cast(list[JsonValue], metric_records),
            "outcome": "passed",
        }
        scenarios.append(scenario_record)
    if seen != set(SCENARIO_RUNNERS):
        raise AssertionError("the simulation plan does not cover every scenario runner")
    report: dict[str, JsonValue] = {
        "schema_version": "holocron-phase-3-simulation-report/v1",
        "evaluated_at_utc": evaluated_at.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "plan_id": plan["plan_id"],
        "plan_sha256": _sha256(PLAN),
        "source": {"code_revision": revision, "working_tree_dirty": dirty},
        "environment": _environment(),
        "scenarios": cast(list[JsonValue], scenarios),
        "summary": {
            "scenario_count": len(scenarios),
            "replication_count": total_replications,
            "failed_scenarios": [],
            "outcome": "passed",
        },
        "outcome": "passed",
    }
    validate_document(report, SIMULATION_REPORT_SCHEMA)
    return report


EXCEPTIONS: dict[str, type[Exception]] = {
    "InputValidationError": InputValidationError,
    "RankDeficiencyError": RankDeficiencyError,
    "ConvergenceError": ConvergenceError,
    "SeparationError": SeparationError,
    "NumericalError": NumericalError,
}


def _case_inputs(
    case: dict[str, JsonValue],
) -> tuple[tuple[float, ...], tuple[tuple[float, ...], ...], dict[str, JsonValue]]:
    response = tuple(
        _number(value, name="response value")
        for value in require_array(case["response"], name="response")
    )
    features = tuple(
        tuple(
            _number(value, name="feature value")
            for value in require_array(row, name="feature row")
        )
        for row in require_array(case["features"], name="features")
    )
    options = require_object(case["options"], name="options")
    return response, features, options


def _execute_edge(case: dict[str, JsonValue]) -> EvidenceResult:
    response, features, options = _case_inputs(case)
    operation = cast(str, case["operation"])
    if operation == "fit_ols":
        return fit_ols(response, features)
    if operation == "fit_glm":
        return fit_glm(response, features, family="binomial")
    if operation == "fit_lrm":
        return fit_lrm(
            response,
            features,
            max_iterations=_integer(
                options.get("max_iterations", 100), name="max_iterations"
            ),
        )
    if operation == "fit_penalized_ols":
        return fit_penalized_ols(
            response,
            features,
            penalty=_number(options["penalty"], name="penalty"),
        )
    if operation == "fit_penalized_lrm":
        return fit_penalized_lrm(
            response,
            features,
            penalty=_number(options["penalty"], name="penalty"),
        )
    estimator = cast(str, options.get("estimator", "ols"))
    base: OlsResult | BinaryLogisticResult
    base = (
        fit_lrm(response, features)
        if estimator == "lrm"
        else fit_ols(response, features)
    )
    analysis_features_raw = options.get("analysis_features")
    analysis_features = (
        features
        if analysis_features_raw is None
        else tuple(
            tuple(
                _number(value, name="analysis feature value")
                for value in require_array(row, name="analysis row")
            )
            for row in require_array(analysis_features_raw, name="analysis_features")
        )
    )
    if operation == "robust_covariance":
        clusters = cast(list[int] | None, options.get("clusters"))
        return robust_covariance(base, response, analysis_features, clusters=clusters)
    if operation == "bootstrap_covariance":
        schedule = cast(list[list[int]] | None, options.get("resample_indices"))
        return bootstrap_covariance(
            base,
            response,
            analysis_features,
            replicates=_integer(options["replicates"], name="replicates"),
            seed=_integer(options["seed"], name="seed"),
            resample_indices=schedule,
        )
    raise ValueError(f"unsupported edge operation: {operation}")


def _covariance(result: EvidenceResult) -> FloatMatrix | None:
    if isinstance(result, CovarianceEstimate):
        return np.asarray(result.matrix, dtype=np.float64)
    return np.asarray(result.covariance, dtype=np.float64)


def _assert_invariants(
    result: EvidenceResult,
    case: dict[str, JsonValue],
    invariants: list[JsonValue],
) -> list[str]:
    response, features, _ = _case_inputs(case)
    checks: list[str] = []
    covariance = _covariance(result)
    for raw_invariant in invariants:
        invariant = cast(str, raw_invariant)
        if invariant == "finite":
            arrays: list[FloatVector | FloatMatrix] = []
            if covariance is not None:
                arrays.append(covariance)
            if isinstance(result, CovarianceEstimate):
                if result.coefficient_mean is not None:
                    arrays.append(np.asarray(result.coefficient_mean))
            else:
                arrays.append(np.asarray(result.coefficients))
            if not all(
                bool(np.all(np.isfinite(array)))  # pyright: ignore[reportUnknownMemberType]
                for array in arrays
            ):
                raise AssertionError("edge result contains a non-finite value")
        elif invariant == "covariance-symmetric":
            assert covariance is not None
            if not np.allclose(  # pyright: ignore[reportUnknownMemberType]
                covariance, covariance.T, rtol=1e-12, atol=1e-15
            ):
                raise AssertionError("edge covariance is not symmetric")
        elif invariant == "covariance-psd":
            assert covariance is not None
            if float(np.min(np.linalg.eigvalsh(covariance))) < -1e-8:
                raise AssertionError("edge covariance is not positive semidefinite")
        elif invariant == "prediction-stable":
            if not isinstance(result, OlsResult):
                raise AssertionError("prediction-stable requires OLS")
            predictions = result.predict(features)
            if (
                max(
                    abs(left - right)
                    for left, right in zip(
                        predictions, result.fitted_values, strict=True
                    )
                )
                > 1e-10
            ):
                raise AssertionError(
                    "training prediction did not reproduce fitted values"
                )
        elif invariant == "effective-df-bounded":
            if not isinstance(result, PenalizedResult):
                raise AssertionError("effective-df-bounded requires a penalized fit")
            parameter_count = result.n_features + int(result.includes_intercept)
            if not 0.0 < result.effective_degrees_of_freedom <= parameter_count + 1e-8:
                raise AssertionError("effective degrees of freedom are outside bounds")
        elif invariant == "rms-effective-df-accounting":
            if not isinstance(result, PenalizedResult):
                raise AssertionError(
                    "rms-effective-df-accounting requires a penalized fit"
                )
            assert result.residual_degrees_of_freedom is not None
            accounted = (
                result.effective_degrees_of_freedom + result.residual_degrees_of_freedom
            )
            if not math.isclose(accounted, result.n_observations, abs_tol=1e-12):
                raise AssertionError(
                    "effective and residual degrees of freedom disagree"
                )
        elif invariant == "negative-residual-df":
            if not isinstance(result, PenalizedResult):
                raise AssertionError("negative-residual-df requires a penalized fit")
            assert result.residual_degrees_of_freedom is not None
            if result.residual_degrees_of_freedom >= 0.0:
                raise AssertionError("expected rms-compatible negative residual df")
        elif invariant == "penalty-reduces-norm":
            if not isinstance(result, PenalizedResult):
                raise AssertionError("penalty-reduces-norm requires a penalized fit")
            ordinary = fit_ols(response, features)
            penalized_norm = math.sqrt(
                sum(float(value) ** 2 for value in result.coefficients[1:])
            )
            ordinary_norm = math.sqrt(
                sum(float(value) ** 2 for value in ordinary.coefficients[1:])
            )
            if penalized_norm >= ordinary_norm:
                raise AssertionError("penalty did not reduce the slope norm")
        elif invariant == "reproducible":
            if _execute_edge(case) != result:
                raise AssertionError("declared edge computation is not reproducible")
        else:
            raise ValueError(f"unsupported edge invariant: {invariant}")
        checks.append(invariant)
    return checks


def run_edge_corpus(
    *, revision: str, dirty: bool, evaluated_at: datetime
) -> dict[str, JsonValue]:
    """Execute the data-driven numerical edge corpus."""
    raw_corpus = load_json(CORPUS)
    validate_document(raw_corpus, CORPUS_SCHEMA)
    corpus = require_object(raw_corpus, name=str(CORPUS))
    raw_cases = require_array(corpus["cases"], name="corpus.cases")
    case_ids: set[str] = set()
    categories: set[str] = set()
    records: list[dict[str, JsonValue]] = []
    for raw_case in raw_cases:
        case = require_object(raw_case, name="edge case")
        case_id = cast(str, case["case_id"])
        if case_id in case_ids:
            raise ValueError(f"duplicate edge case: {case_id}")
        case_ids.add(case_id)
        categories.add(cast(str, case["category"]))
        expected = require_object(case["expected"], name="case.expected")
        expected_outcome = cast(str, expected["outcome"])
        observed_exception: str | None = None
        checks: list[str] = []
        try:
            result = _execute_edge(case)
        except Exception as error:
            observed_exception = type(error).__name__
            if expected_outcome != "error":
                raise
            expected_name = cast(str, expected["exception"])
            expected_type = EXCEPTIONS[expected_name]
            if type(error) is not expected_type:
                raise AssertionError(
                    f"{case_id}: expected {expected_name}, received "
                    f"{observed_exception}"
                ) from error
            checks.append(f"raised:{observed_exception}")
        else:
            if expected_outcome != "success":
                raise AssertionError(f"{case_id}: expected an exception")
            checks.extend(
                _assert_invariants(
                    result,
                    case,
                    require_array(expected["invariants"], name="expected.invariants"),
                )
            )
        record: dict[str, JsonValue] = {
            "case_id": case_id,
            "expected_outcome": expected_outcome,
            "observed_exception": observed_exception,
            "checks": cast(list[JsonValue], checks),
            "outcome": "passed",
        }
        records.append(record)
    edge_summary: dict[str, JsonValue] = {
        "case_count": len(records),
        "categories": cast(list[JsonValue], sorted(categories)),
        "failed_cases": [],
        "outcome": "passed",
    }
    report: dict[str, JsonValue] = {
        "schema_version": "holocron-phase-3-edge-report/v1",
        "evaluated_at_utc": evaluated_at.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "corpus_id": corpus["corpus_id"],
        "corpus_sha256": _sha256(CORPUS),
        "source": {"code_revision": revision, "working_tree_dirty": dirty},
        "cases": cast(list[JsonValue], records),
        "summary": edge_summary,
        "outcome": "passed",
    }
    validate_document(report, EDGE_REPORT_SCHEMA)
    return report


def _write(path: Path, report: dict[str, JsonValue]) -> str:
    content = (
        json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary.write(content)
            temporary.flush()
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return hashlib.sha256(content).hexdigest()


def run(
    simulation_output: Path,
    edge_output: Path,
    *,
    require_clean: bool = False,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    dirty = _working_tree_dirty()
    if require_clean and dirty:
        raise ValueError("Phase 3 evidence requires a clean source checkout")
    revision = _current_revision()
    if require_clean and revision == "unknown":
        raise ValueError("Phase 3 evidence requires a known source revision")
    evaluated_at = datetime.now(UTC)
    simulation = run_simulations(
        revision=revision, dirty=dirty, evaluated_at=evaluated_at
    )
    edge = run_edge_corpus(revision=revision, dirty=dirty, evaluated_at=evaluated_at)
    simulation_digest = _write(simulation_output, simulation)
    edge_digest = _write(edge_output, edge)
    simulation_summary = require_object(simulation["summary"], name="summary")
    edge_summary = require_object(edge["summary"], name="summary")
    print(
        "Phase 3 simulation evidence passed: "
        f"scenarios={simulation_summary['scenario_count']}, "
        f"replications={simulation_summary['replication_count']}, "
        f"sha256={simulation_digest}"
    )
    print(
        "Phase 3 numerical edge corpus passed: "
        f"cases={edge_summary['case_count']}, "
        f"sha256={edge_digest}"
    )
    return simulation, edge


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--simulation-output", type=Path, default=DEFAULT_SIMULATION_OUTPUT
    )
    parser.add_argument("--edge-output", type=Path, default=DEFAULT_EDGE_OUTPUT)
    parser.add_argument("--require-clean", action="store_true")
    arguments = parser.parse_args(argv)
    run(
        arguments.simulation_output,
        arguments.edge_output,
        require_clean=cast(bool, arguments.require_clean),
    )


if __name__ == "__main__":
    main()
