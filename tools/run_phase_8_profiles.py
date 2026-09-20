"""Run the locked Phase 8 performance workloads and retain cProfile evidence."""

# pyright: reportUnknownMemberType=false

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import math
import platform
import pstats
import statistics
import subprocess
import time
import tracemalloc
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias, cast

import numpy as np

from holocron.models import SurvivalResponse, fit_cph, fit_lrm, fit_ols, fit_psm
from holocron.validation import ResamplePlan, validate_model
from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "governance/phase-8-performance-plan.json"
PLAN_SCHEMA = ROOT / "schemas/phase-8-performance-plan.schema.json"
REPORT_SCHEMA = ROOT / "schemas/phase-8-performance-report.schema.json"
DEFAULT_OUTPUT = ROOT / ".work/phase-8-performance/performance-report.json"

Workload = Callable[[int, int], dict[str, JsonValue]]
ProfileKey: TypeAlias = tuple[str, int, str]
ProfileValue: TypeAlias = tuple[int, int, float, float, dict[object, object]]


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


def _rows(
    values: np.ndarray[Any, np.dtype[np.float64]],
) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(item) for item in row) for row in values)


def _ols_validation(seed: int, sample_size: int) -> dict[str, JsonValue]:
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(sample_size, 4))
    response = (
        1.2
        + features @ np.asarray((0.7, -0.4, 0.2, 0.1), dtype=np.float64)
        + rng.normal(scale=0.6, size=sample_size)
    )
    rows = _rows(features)
    values = tuple(float(value) for value in response)
    fitted = fit_ols(values, rows, feature_names=("x1", "x2", "x3", "x4"))
    plan = ResamplePlan.k_fold(sample_size, folds=5, repeats=2, seed=seed)
    result = validate_model(fitted, values, rows, plan)
    if result.status != "complete" or len(result.resamples.successes) != 10:
        raise RuntimeError("OLS validation workload did not complete all refits")
    return {
        "status": result.status,
        "successful_resamples": len(result.resamples.successes),
        "coefficient_count": len(fitted.coefficients),
    }


def _binary_validation(seed: int, sample_size: int) -> dict[str, JsonValue]:
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(sample_size, 3))
    linear = -0.15 + features @ np.asarray((0.8, -0.55, 0.3), dtype=np.float64)
    probability = 1.0 / (1.0 + np.exp(-linear))
    response = rng.binomial(1, probability).astype(np.float64)
    rows = _rows(features)
    values = tuple(float(value) for value in response)
    fitted = fit_lrm(values, rows, feature_names=("x1", "x2", "x3"))
    plan = ResamplePlan.k_fold(sample_size, folds=5, repeats=2, seed=seed)
    result = validate_model(fitted, values, rows, plan)
    if result.status != "complete" or len(result.resamples.successes) != 10:
        raise RuntimeError("binary validation workload did not complete all refits")
    return {
        "status": result.status,
        "successful_resamples": len(result.resamples.successes),
        "coefficient_count": len(fitted.coefficients),
    }


def _cox_inputs(
    seed: int, sample_size: int
) -> tuple[
    tuple[float, ...],
    tuple[int, ...],
    tuple[tuple[float, ...], ...],
]:
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(sample_size, 2))
    hazard = 0.12 * np.exp(0.45 * features[:, 0] - 0.25 * features[:, 1])
    event_time = rng.exponential(1.0 / hazard)
    censor_time = rng.exponential(1.0 / 0.05, size=sample_size)
    observed = np.minimum(event_time, censor_time)
    events = event_time <= censor_time
    return (
        tuple(float(value) for value in observed),
        tuple(int(value) for value in events),
        _rows(features),
    )


def _cox_standard(seed: int, sample_size: int) -> dict[str, JsonValue]:
    times, events, features = _cox_inputs(seed, sample_size)
    result = fit_cph(times, events, features, feature_names=("x1", "x2"))
    if not result.baseline_times or result.iterations <= 0:
        raise RuntimeError("standard Cox workload returned an incomplete result")
    return {
        "event_count": sum(events),
        "iterations": result.iterations,
        "baseline_points": len(result.baseline_times),
    }


def _cox_delayed_entry(seed: int, sample_size: int) -> dict[str, JsonValue]:
    times, events, features = _cox_inputs(seed, sample_size)
    entry = tuple(0.2 * value for value in times)
    result = fit_cph(
        times,
        events,
        features,
        feature_names=("x1", "x2"),
        entry_times=entry,
    )
    if not result.baseline_times or result.iterations <= 0:
        raise RuntimeError("delayed-entry Cox workload returned an incomplete result")
    return {
        "event_count": sum(events),
        "iterations": result.iterations,
        "baseline_points": len(result.baseline_times),
    }


def _psm_mixed(seed: int, sample_size: int) -> dict[str, JsonValue]:
    rng = np.random.default_rng(seed)
    features = rng.normal(size=(sample_size, 2))
    latent = np.exp(
        2.0
        + 0.35 * features[:, 0]
        - 0.2 * features[:, 1]
        + rng.normal(scale=0.55, size=sample_size)
    )
    lower: list[float] = []
    upper: list[float] = []
    for index, value in enumerate(latent):
        observed = float(value)
        kind = index % 4
        if kind == 0:
            lower.append(observed)
            upper.append(observed)
        elif kind == 1:
            lower.append(0.85 * observed)
            upper.append(1.15 * observed)
        elif kind == 2:
            lower.append(0.8 * observed)
            upper.append(math.inf)
        else:
            lower.append(-math.inf)
            upper.append(1.2 * observed)
    response = SurvivalResponse.from_intervals(lower, upper)
    result = fit_psm(response, _rows(features), feature_names=("x1", "x2"))
    if result.iterations <= 0 or result.n_observations != sample_size:
        raise RuntimeError("mixed-censoring PSM workload returned an incomplete result")
    return {
        "iterations": result.iterations,
        "coefficient_count": len(result.coefficients),
        "scale_count": len(result.scales),
    }


WORKLOADS: dict[str, Workload] = {
    "ols-repeated-validation": _ols_validation,
    "binary-repeated-validation": _binary_validation,
    "cox-standard-risk-sets": _cox_standard,
    "cox-delayed-entry": _cox_delayed_entry,
    "psm-mixed-censoring": _psm_mixed,
}


def _function_name(key: ProfileKey) -> str:
    filename, line, name = key
    try:
        display = Path(filename).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        display = Path(filename).name
    return f"{display}:{line}({name})"


def _profile_stats(stats: pstats.Stats) -> dict[ProfileKey, ProfileValue]:
    return cast(dict[ProfileKey, ProfileValue], vars(stats)["stats"])


def _hotspots(stats: dict[ProfileKey, ProfileValue]) -> list[JsonValue]:
    ranked: list[tuple[float, ProfileKey, ProfileValue]] = []
    for key, values in stats.items():
        if "/src/holocron/" not in key[0].replace("\\", "/"):
            continue
        ranked.append((float(values[3]), key, values))
    ranked.sort(reverse=True)
    return [
        cast(
            JsonValue,
            {
                "function": _function_name(key),
                "primitive_calls": int(values[0]),
                "total_calls": int(values[1]),
                "own_seconds": float(values[2]),
                "cumulative_seconds": cumulative,
            },
        )
        for cumulative, key, values in ranked[:12]
    ]


def _run_workload(
    specification: dict[str, JsonValue], output_directory: Path
) -> dict[str, JsonValue]:
    workload_id = cast(str, specification["workload_id"])
    runner = WORKLOADS[workload_id]
    seed = cast(int, specification["seed"])
    sample_size = cast(int, specification["sample_size"])
    repetitions = cast(int, specification["timing_repetitions"])
    maximum = cast(int, specification["max_primitive_calls"])
    maximum_peak = cast(int, specification["max_peak_bytes"])

    runner(seed, sample_size)
    timings: list[float] = []
    result: dict[str, JsonValue] = {}
    for _ in range(repetitions):
        started = time.perf_counter()
        result = runner(seed, sample_size)
        timings.append(time.perf_counter() - started)

    tracemalloc.start()
    memory_result = runner(seed, sample_size)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if memory_result != result:
        raise RuntimeError(f"{workload_id} produced a non-deterministic summary")

    profiler = cProfile.Profile()
    profiler.enable()
    profiled_result = runner(seed, sample_size)
    profiler.disable()
    if profiled_result != result:
        raise RuntimeError(f"{workload_id} produced a non-deterministic summary")
    profile_name = f"{workload_id}.prof"
    profiler.dump_stats(output_directory / profile_name)
    stats = pstats.Stats(profiler)
    profile_stats = _profile_stats(stats)
    primitive_calls = sum(values[0] for values in profile_stats.values())
    outcome = (
        "passed"
        if primitive_calls <= maximum and peak_bytes <= maximum_peak
        else "failed"
    )
    return {
        "workload_id": workload_id,
        "kind": specification["kind"],
        "sample_size": sample_size,
        "result_sha256": _digest(cast(JsonValue, result)),
        "profile_file": profile_name,
        "primitive_calls": primitive_calls,
        "max_primitive_calls": maximum,
        "peak_bytes": peak_bytes,
        "max_peak_bytes": maximum_peak,
        "median_seconds": statistics.median(timings),
        "timing_repetitions": repetitions,
        "hotspots": _hotspots(profile_stats),
        "outcome": outcome,
    }


def run(output: Path, *, require_clean: bool = False) -> dict[str, JsonValue]:
    plan_value = load_json(PLAN)
    validate_document(plan_value, PLAN_SCHEMA)
    plan = require_object(plan_value, name="performance plan")
    dirty = _dirty()
    if require_clean and dirty:
        raise RuntimeError("performance evidence requires a clean working tree")
    specifications = [
        require_object(value, name="performance workload")
        for value in require_array(plan["workloads"], name="performance workloads")
    ]
    identifiers = {cast(str, value["workload_id"]) for value in specifications}
    if identifiers != set(WORKLOADS) or len(specifications) != len(identifiers):
        raise RuntimeError("performance plan and workload registry differ")

    output.parent.mkdir(parents=True, exist_ok=True)
    results = [
        _run_workload(specification, output.parent) for specification in specifications
    ]
    technical_status = (
        "pass" if all(value["outcome"] == "passed" for value in results) else "fail"
    )
    report: dict[str, JsonValue] = {
        "schema_version": "holocron-phase-8-performance-report/v1",
        "evaluated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "plan_id": plan["plan_id"],
        "plan_sha256": _sha256(PLAN),
        "source": {"code_revision": _revision(), "working_tree_dirty": dirty},
        "environment": _environment(),
        "timing_policy": plan["timing_policy"],
        "workloads": cast(JsonValue, results),
        "technical_status": technical_status,
    }
    validate_document(report, REPORT_SCHEMA)
    output.write_text(
        json.dumps(report, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-clean", action="store_true")
    arguments = parser.parse_args()
    report = run(arguments.output, require_clean=arguments.require_clean)
    print(
        f"Phase 8 profiles: {report['technical_status']} "
        f"({len(cast(list[JsonValue], report['workloads']))} workloads)"
    )
    return 0 if report["technical_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
