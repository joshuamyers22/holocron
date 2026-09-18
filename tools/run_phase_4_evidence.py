"""Build the reproducible Phase 4 ordinal/censoring exit-gate evidence."""

# pyright: reportUnknownMemberType=false, reportReturnType=false

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np

from holocron.exceptions import (
    ConvergenceError,
    HolocronError,
    InputValidationError,
    RankDeficiencyError,
)
from holocron.models import CensoredResponse, fit_orm, fit_random_intercept_orm
from reference.contracts import (
    EXPECTED,
    JsonValue,
    compare_json,
    load_json,
    output_payload,
    require_object,
    validate_case_pair,
    validate_document,
)
from reference.python_parity import build_python_output

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "governance/phase-4-evidence-plan.json"
CORPUS = ROOT / "reference/phase-4-edge-cases.json"
PLAN_SCHEMA = ROOT / "schemas/phase-4-evidence-plan.schema.json"
CORPUS_SCHEMA = ROOT / "schemas/phase-4-edge-corpus.schema.json"
REPORT_SCHEMA = ROOT / "schemas/phase-4-evidence-report.schema.json"
DEFAULT_OUTPUT = ROOT / ".work/phase-4-evidence/phase-4-exit.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
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


def _features(
    values: np.ndarray[Any, np.dtype[np.float64]],
) -> tuple[tuple[float], ...]:
    return tuple((float(value),) for value in values)


def _ordinal_sample(
    rng: np.random.Generator,
    sample_size: int,
    thresholds: tuple[float, float],
    slope: float,
    random_effect: np.ndarray[Any, np.dtype[np.float64]] | None = None,
) -> tuple[np.ndarray[Any, np.dtype[np.float64]], np.ndarray[Any, np.dtype[np.int64]]]:
    x = rng.normal(size=sample_size)
    predictor = slope * x
    if random_effect is not None:
        predictor += random_effect
    p2 = 1.0 / (1.0 + np.exp(-(thresholds[0] + predictor)))
    p3 = 1.0 / (1.0 + np.exp(-(thresholds[1] + predictor)))
    draw = rng.random(sample_size)
    y = np.where(draw < 1.0 - p2, 1, np.where(draw < 1.0 - p3, 2, 3))
    return x, cast(np.ndarray[Any, np.dtype[np.int64]], y.astype(np.int64))


def _parity() -> dict[str, JsonValue]:
    rows: list[dict[str, JsonValue]] = []
    exact = numeric = 0
    passed = True
    operations = {"orm", "orm_censored", "orm_random"}
    for case_path in sorted((ROOT / "reference/cases").glob("*.json")):
        raw = require_object(load_json(case_path), name=str(case_path))
        if raw.get("operation") not in operations:
            continue
        case, expected, policy = validate_case_pair(
            case_path, EXPECTED / str(raw["expected_output"])
        )
        comparison = compare_json(
            build_python_output(case), output_payload(expected), policy
        )
        exact += comparison.exact_comparisons
        numeric += comparison.numeric_comparisons
        passed &= comparison.passed
        rows.append(
            {
                "case_id": case["case_id"],
                "operation": case["operation"],
                "profile": comparison.profile,
                "passed": comparison.passed,
                "exact_comparisons": comparison.exact_comparisons,
                "numeric_comparisons": comparison.numeric_comparisons,
                "maximum_absolute_error": comparison.maximum_absolute_error,
                "maximum_relative_error": comparison.maximum_relative_error,
                "mismatches": list(comparison.mismatches),
            }
        )
    return {
        "passed": passed and len(rows) == 6,
        "case_count": len(rows),
        "exact_comparisons": exact,
        "numeric_comparisons": numeric,
        "cases": rows,
    }


def _fixed_simulation(
    scenario: dict[str, Any], *, censored: bool
) -> dict[str, JsonValue]:
    rng = np.random.default_rng(int(scenario["seed"]))
    estimates: list[float] = []
    failures: list[int] = []
    thresholds = tuple(float(value) for value in scenario["thresholds"])
    for replication in range(int(scenario["replications"])):
        x, y = _ordinal_sample(
            rng,
            int(scenario["sample_size"]),
            cast(tuple[float, float], thresholds),
            float(scenario["slope"]),
        )
        response: tuple[int, ...] | CensoredResponse
        if censored:
            lower = y.astype(np.float64)
            upper = y.astype(np.float64)
            selected = rng.random(y.size) < float(scenario["censoring_probability"])
            for index in np.flatnonzero(selected):
                if y[index] == 1:
                    upper[index] = 2.0
                elif y[index] == 3:
                    lower[index] = 2.0
                elif rng.random() < 0.5:
                    lower[index], upper[index] = 1.0, 2.0
                else:
                    lower[index], upper[index] = 2.0, 3.0
            response = CensoredResponse.from_intervals(lower, upper)
        else:
            response = tuple(int(value) for value in y)
        try:
            result = fit_orm(response, _features(x), feature_names=("x",))
            estimates.append(result.coefficients[0])
        except HolocronError:
            failures.append(replication)
    target = float(scenario["slope"])
    array = np.asarray(estimates, dtype=np.float64)
    metrics = {
        "slope_abs_bias": abs(float(np.mean(array)) - target),
        "slope_rmse": float(np.sqrt(np.mean((array - target) ** 2))),
        "failure_rate": len(failures) / int(scenario["replications"]),
    }
    limits = cast(dict[str, float], scenario["limits"])
    return {
        "id": str(scenario["id"]),
        "replications": int(scenario["replications"]),
        "completed": len(estimates),
        "metrics": metrics,
        "limits": limits,
        "passed": all(metrics[name] <= float(limit) for name, limit in limits.items()),
        "failed_replications": failures,
    }


def _random_simulation(scenario: dict[str, Any]) -> dict[str, JsonValue]:
    rng = np.random.default_rng(int(scenario["seed"]))
    slopes: list[float] = []
    sigmas: list[float] = []
    failures: list[int] = []
    cluster_count = int(scenario["clusters"])
    per_cluster = int(scenario["observations_per_cluster"])
    clusters = tuple(np.repeat(np.arange(cluster_count), per_cluster).tolist())
    thresholds = cast(
        tuple[float, float], tuple(float(v) for v in scenario["thresholds"])
    )
    for replication in range(int(scenario["replications"])):
        effects = rng.normal(scale=float(scenario["sigma"]), size=cluster_count)
        x, y = _ordinal_sample(
            rng,
            cluster_count * per_cluster,
            thresholds,
            float(scenario["slope"]),
            effects[np.asarray(clusters, dtype=np.int64)],
        )
        try:
            result = fit_random_intercept_orm(
                tuple(int(value) for value in y),
                _features(x),
                clusters,
                feature_names=("x",),
                quadrature_grid=(5, 7, 9, 11),
                quadrature_tolerance=5e-4,
                max_iterations=60,
                tolerance=1e-4,
            )
            slopes.append(result.fixed.coefficients[0])
            sigmas.append(cast(float, result.sigma))
        except HolocronError:
            failures.append(replication)
    metrics = {
        "slope_abs_bias": abs(float(np.mean(slopes)) - float(scenario["slope"])),
        "sigma_abs_bias": abs(float(np.mean(sigmas)) - float(scenario["sigma"])),
        "failure_rate": len(failures) / int(scenario["replications"]),
    }
    limits = cast(dict[str, float], scenario["limits"])
    return {
        "id": str(scenario["id"]),
        "replications": int(scenario["replications"]),
        "completed": len(slopes),
        "metrics": metrics,
        "limits": limits,
        "passed": bool(slopes)
        and all(metrics[name] <= float(limit) for name, limit in limits.items()),
        "failed_replications": failures,
    }


def _simulations(plan: dict[str, Any]) -> dict[str, JsonValue]:
    rows: list[dict[str, JsonValue]] = []
    for raw in cast(list[dict[str, Any]], plan["simulation_scenarios"]):
        if raw["kind"] == "random":
            rows.append(_random_simulation(raw))
        else:
            rows.append(_fixed_simulation(raw, censored=raw["kind"] == "censored"))
    return {"passed": all(bool(row["passed"]) for row in rows), "scenarios": rows}


def _random_case(case_id: str) -> tuple[dict[str, Any], Any]:
    case = cast(dict[str, Any], load_json(ROOT / "reference/cases" / f"{case_id}.json"))
    result = fit_random_intercept_orm(
        case["y"],
        tuple((float(value),) for value in case["x"]),
        case["clusters"],
        feature_names=("x",),
        mix_re=case["mix_re"],
        quadrature_grid=case["quadrature_grid"],
        quadrature_tolerance=float(case["quadrature_tolerance"]),
        tolerance=2e-5,
    )
    return case, result


def _quadrature(plan: dict[str, Any]) -> dict[str, JsonValue]:
    fits: list[dict[str, JsonValue]] = []
    maximum = float(plan["quadrature"]["maximum_last_step_scaled_difference"])
    for case_id in ("orm-random-logistic", "orm-random-mix-re"):
        _, result = _random_case(case_id)
        previous, final = result.quadrature_history[-2:]
        scaled = abs(final[1] - previous[1]) / (1.0 + abs(final[1]))
        fits.append(
            {
                "case_id": case_id,
                "history": [list(item) for item in result.quadrature_history],
                "final_points": result.quadrature_points,
                "last_step_scaled_difference": scaled,
                "passed": scaled <= maximum,
            }
        )
    return {"passed": all(bool(row["passed"]) for row in fits), "fits": fits}


def _sparsity(plan: dict[str, Any]) -> dict[str, JsonValue]:
    rows: list[dict[str, JsonValue]] = []
    specification = cast(dict[str, Any], plan["sparsity"])
    for level_count in cast(list[int], specification["levels"]):
        response: list[int] = []
        features: list[tuple[float]] = []
        for replicate in range(4):
            for level in range(1, level_count + 1):
                response.append(level)
                features.append((math.sin(level * 1.7 + replicate),))
        started = time.perf_counter()
        result = fit_orm(response, features, feature_names=("x",))
        elapsed = time.perf_counter() - started
        diagnostics = result.diagnostics()
        covariance_bytes = np.asarray(result.covariance, dtype=np.float64).nbytes
        passed = diagnostics.covariance_condition <= float(
            specification["maximum_covariance_condition"]
        ) and diagnostics.maximum_simplex_error <= float(
            specification["maximum_simplex_error"]
        )
        rows.append(
            {
                "levels": level_count,
                "parameters": len(result.parameter_values),
                "elapsed_seconds": elapsed,
                "covariance_bytes": covariance_bytes,
                "covariance_condition": diagnostics.covariance_condition,
                "maximum_simplex_error": diagnostics.maximum_simplex_error,
                "passed": passed,
            }
        )
    return {
        "passed": all(bool(row["passed"]) for row in rows),
        "fits": rows,
        "published_limit": (
            "The Newton step is bordered-tridiagonal for exact outcomes; the "
            "public covariance remains O(K^2), and general censoring uses a "
            "dense solve."
        ),
    }


def _edge_action(action: str) -> JsonValue:
    response = (1, 1, 2, 2, 3, 3, 1, 2, 3, 1, 2, 3)
    features = tuple((float(index % 5) - 2.0,) for index in range(12))
    if action == "two_levels":
        return fit_orm((1, 1, 2, 2), ((0.0,), (1.0,), (2.0,), (3.0,)))  # type: ignore[return-value]
    if action == "rank_deficient":
        return fit_orm(response, tuple((v[0], 2.0 * v[0]) for v in features))  # type: ignore[return-value]
    if action == "invalid_interval":
        return CensoredResponse.from_intervals((1, 2, 3), (1, 1, 3))  # type: ignore[return-value]
    if action == "no_exact":
        return CensoredResponse.from_intervals((1, 1, 2), (2, 3, 3))  # type: ignore[return-value]
    if action == "one_sided":
        value = CensoredResponse.from_intervals(
            (1, 1, 2, 2, 3, 3, -math.inf, 1, 2, 1, 2, 3),
            (1, 1, 2, 2, 3, 3, 2, math.inf, 3, 1, 2, 3),
        ).turnbull()
        if (value.first[6], value.last[6], value.first[7], value.last[7]) != (
            0,
            0,
            1,
            2,
        ):
            raise AssertionError("one-sided exact-grid mapping changed")
        return {
            "mapping": [value.first[6], value.last[6], value.first[7], value.last[7]]
        }
    clusters = tuple(index // 2 for index in range(12))
    if action == "constant_mix":
        return fit_random_intercept_orm(
            response, features, clusters, mix_re=(0.0,) * 12
        )  # type: ignore[return-value]
    if action == "single_cluster":
        return fit_random_intercept_orm(response, features, (0,) * 12)  # type: ignore[return-value]
    if action == "invalid_grid":
        return fit_random_intercept_orm(
            response, features, clusters, quadrature_grid=(4, 7)
        )  # type: ignore[return-value]
    if action == "fixed_nonconvergence":
        return fit_orm(response, features, max_iterations=1)  # type: ignore[return-value]
    raise AssertionError(f"unknown edge action {action}")


def _failure_modes() -> dict[str, JsonValue]:
    corpus = require_object(load_json(CORPUS), name=str(CORPUS))
    validate_document(corpus, CORPUS_SCHEMA)
    rows: list[dict[str, JsonValue]] = []
    for raw in cast(list[dict[str, JsonValue]], corpus["cases"]):
        expected = raw["expected_exception"]
        actual: str | None = None
        detail: JsonValue = None
        try:
            detail = _edge_action(str(raw["action"]))
        except (InputValidationError, RankDeficiencyError, ConvergenceError) as error:
            actual = type(error).__name__
            detail = str(error)
        passed = actual == expected
        rows.append(
            {
                "id": raw["id"],
                "expected_exception": expected,
                "actual_exception": actual,
                "detail": detail,
                "passed": passed,
            }
        )
    return {"passed": all(bool(row["passed"]) for row in rows), "cases": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    source_dirty = _dirty()
    if args.require_clean and source_dirty:
        raise SystemExit("Phase 4 clean evidence requires a clean working tree")
    plan = require_object(load_json(PLAN), name=str(PLAN))
    validate_document(plan, PLAN_SCHEMA)
    parity = _parity()
    simulations = _simulations(cast(dict[str, Any], plan))
    quadrature = _quadrature(cast(dict[str, Any], plan))
    sparsity = _sparsity(cast(dict[str, Any], plan))
    failure_modes = _failure_modes()
    technical_pass = all(
        bool(section["passed"])
        for section in (parity, simulations, quadrature, sparsity, failure_modes)
    )
    review = require_object(plan["independent_review"], name="independent_review")
    review_approved = (
        review.get("required") is True
        and review.get("status") == "approved"
        and isinstance(review.get("reviewer"), str)
        and bool(review["reviewer"])
        and isinstance(review.get("approved_at"), str)
        and bool(review["approved_at"])
    )
    report: dict[str, JsonValue] = {
        "schema_version": "holocron-phase-4-evidence-report/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "revision": _revision(),
        "source_dirty": source_dirty,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "operating_system": platform.system(),
            "machine": platform.machine(),
        },
        "inputs": {"plan_sha256": _sha256(PLAN), "edge_corpus_sha256": _sha256(CORPUS)},
        "parity": parity,
        "simulations": simulations,
        "quadrature": quadrature,
        "sparsity": sparsity,
        "failure_modes": failure_modes,
        "platform_policy": {
            "required_platforms": plan["platforms"],
            "ci_artifacts": (
                "phase-4-platform-evidence-${runner.os}-${runner.arch}-${github.sha}"
            ),
        },
        "independent_review": review,
        "technical_status": "pass" if technical_pass else "fail",
        "phase_4_exit_gate": (
            "closed"
            if technical_pass and review_approved
            else "awaiting-independent-review"
            if technical_pass
            else "failed"
        ),
    }
    validate_document(report, REPORT_SCHEMA)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, allow_nan=False, indent=2) + "\n")
    print(
        f"wrote {output.relative_to(ROOT)}: technical={report['technical_status']}, "
        f"gate={report['phase_4_exit_gate']}"
    )
    if not technical_pass:
        raise SystemExit("Phase 4 technical evidence failed")


if __name__ == "__main__":
    main()
