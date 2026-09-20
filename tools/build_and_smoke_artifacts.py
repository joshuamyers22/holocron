"""Build, inspect, and install-test Holocron release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from check_build_artifacts import inspect_artifacts, project_identity

ROOT = Path(__file__).resolve().parents[1]
SMOKE_PROGRAM = """
from __future__ import annotations

import importlib.metadata
import importlib.resources
import importlib.util
import os
import sys
from pathlib import Path

import numpy as np

import holocron
from holocron.design import DataDistribution, DesignSpec, RestrictedCubicSplineSpec
from holocron.formula import Formula
from holocron.graphics import (
    AxisSpec,
    BandLayer,
    LineLayer,
    NomogramGeometry,
    PlotSpec,
    build_nomogram,
    effect_plot_spec,
    render_nomogram_svg,
    render_svg,
)
from holocron.models import (
    BinaryLogisticResult,
    BuckleyJamesResult,
    CensoredResponse,
    CoxResult,
    GeneralizedLeastSquaresResult,
    NonparametricSurvivalResult,
    OlsResult,
    OrdinalResult,
    ParametricSurvivalResult,
    ProportionalHazardsParametricResult,
    QuantileRegressionResult,
    SurvivalResponse,
    anova,
    backward_select,
    bootstrap_covariance,
    contrast,
    covariance,
    fit_cph,
    fit_buckley_james,
    fit_lrm,
    fit_gls,
    fit_npsurv,
    fit_ols,
    fit_ordinal_lrm,
    fit_orm,
    fit_penalized_lrm,
    fit_penalized_ols,
    fit_psm,
    fit_quantile_regression,
    influence_diagnostics,
    likelihood,
    predict,
    residuals,
    robust_covariance,
    robustness_diagnostics,
    summarize,
    survival_residuals,
    trace_penalty,
    to_proportional_hazards,
    validate_survival_predictions,
    variance_inflation_factors,
)
from holocron.reporting import TableSpec, model_summary_table, render_latex
from holocron.validation import (
    LikelihoodRatioAnova,
    LikelihoodRatioTest,
    MultipleImputationAnovaResult,
    PooledCalibrationResult,
    PooledModelResult,
    PooledValidationResult,
    ResamplePlan,
    calibrate_model,
    optimism_correct_calibration,
    optimism_correct_validation,
    pool_imputation_calibration,
    pool_imputation_likelihood_ratio,
    pool_imputation_models,
    pool_imputation_validation,
    report_resample_execution,
    run_resample_plan,
    take_rows,
    validate_model,
    validate_probabilities,
)

source_root = Path(os.environ["HOLOCRON_SMOKE_SOURCE_ROOT"]).resolve()
environment_root = Path(os.environ["HOLOCRON_SMOKE_ENVIRONMENT_ROOT"]).resolve()
module_path = Path(holocron.__file__).resolve()
assert module_path.is_relative_to(environment_root), module_path
assert not module_path.is_relative_to(source_root), module_path
assert Path(sys.prefix).resolve() == environment_root
assert holocron.__version__ == os.environ["HOLOCRON_SMOKE_VERSION"]
assert importlib.metadata.version("holocron-rms") == holocron.__version__
assert importlib.util.find_spec("holocron.cli") is None
assert importlib.resources.files("holocron").joinpath(
    "schemas/resample-plan.schema.json"
).is_file()
assert importlib.resources.files("holocron").joinpath(
    "schemas/plot-spec.schema.json"
).is_file()
assert importlib.resources.files("holocron").joinpath(
    "schemas/nomogram-geometry.schema.json"
).is_file()
assert importlib.resources.files("holocron").joinpath(
    "schemas/table-spec.schema.json"
).is_file()
assert importlib.resources.files("holocron").joinpath(
    "schemas/gls-result.schema.json"
).is_file()
assert importlib.resources.files("holocron").joinpath(
    "schemas/quantile-regression-result.schema.json"
).is_file()
assert importlib.resources.files("holocron").joinpath(
    "schemas/buckley-james-result.schema.json"
).is_file()
assert importlib.resources.files("holocron").joinpath(
    "schemas/proportional-hazards-result.schema.json"
).is_file()
for pooled_schema in (
    "pooled-model-result.schema.json",
    "pooled-validation-result.schema.json",
    "pooled-calibration-result.schema.json",
    "pooled-anova-result.schema.json",
):
    assert importlib.resources.files("holocron").joinpath(
        "schemas", pooled_schema
    ).is_file()

x = (-2.0, -1.0, 0.0, 1.0, 2.0, 3.0)
y = (0.2, 0.8, 1.1, 1.7, 2.5, 3.6)
metadata = DataDistribution.from_data({"x": x}, labels={"x": "Predictor"})
formula_spec = DesignSpec.from_formula(Formula.parse("y ~ rcs(x, [-2, 0, 1.5, 3])"))
formula_design = formula_spec.transform({"x": x})
spec = RestrictedCubicSplineSpec((-2.0, 0.0, 1.5, 3.0))
design = spec.transform(x)
fit = fit_ols(y, formula_design)
predictions = fit.predict(formula_design)

assert design.shape == (6, 3)
assert metadata.adjustments == {"x": 0.5}
assert DataDistribution.from_json(metadata.to_json()) == metadata
assert DesignSpec.from_json(formula_spec.to_json()) == formula_spec
assert type(formula_design).from_json(formula_design.to_json()) == formula_design
assert np.allclose(formula_design.to_numpy(), design)
assert fit.coefficient_names == (
    "Intercept",
    "rcs(x,linear)",
    "rcs(x,nonlinear=1)",
    "rcs(x,nonlinear=2)",
)
assert fit.design_fingerprint == formula_spec.fingerprint
assert OlsResult.from_json(fit.to_json()) == fit
assert fit.rank == 4
assert fit.residual_degrees_of_freedom == 2
assert np.allclose(predictions, fit.fitted_values)
assert covariance(fit).coefficient_names == fit.coefficient_names
assert likelihood(fit).parameter_count == fit.rank + 1
assert len(residuals(fit, kind="standardized").values) == len(y)
assert summarize(fit).model_type == "ols"
assert len(anova(fit, formula_spec).tests) == 1
assert contrast(fit, {"rcs(x,linear)": 1.0}).estimate == fit.coefficients[1]
prediction_result = predict(fit, formula_design)
assert len(prediction_result.values) == len(y)

linear_spec = DesignSpec.from_formula("y ~ x")
linear_design = linear_spec.transform({"x": x})
linear_fit = fit_ols(y, linear_design)
gls_fit = fit_gls(y, linear_design)
quantile_fit = fit_quantile_regression(y, linear_design)
assert GeneralizedLeastSquaresResult.from_json(gls_fit.to_json()) == gls_fit
assert QuantileRegressionResult.from_json(quantile_fit.to_json()) == quantile_fit
penalized_linear = fit_penalized_ols(y, linear_design, penalty=1.0)
robust = robust_covariance(
    linear_fit, y, linear_design, clusters=("a", "a", "b", "b", "c", "c")
)
schedule = (
    (0, 1, 2, 3, 4, 5),
    (5, 4, 3, 2, 1, 0),
    (0, 1, 1, 3, 4, 5),
    (0, 1, 2, 3, 4, 4),
)
bootstrapped = bootstrap_covariance(
    linear_fit,
    y,
    linear_design,
    replicates=4,
    seed=7,
    resample_indices=schedule,
)
assert penalized_linear.penalty_weights == (1.0,)
assert robust.cluster_count == 3
assert bootstrapped.replicate_count == 4
influence = influence_diagnostics(linear_fit, y, linear_design)
vifs = variance_inflation_factors(linear_fit)
robustness = robustness_diagnostics(
    linear_fit, y, linear_design, clusters=("a", "a", "b", "b", "c", "c")
)
penalty_trace = trace_penalty(
    linear_fit, y, linear_design, (0.0, 0.5, 2.0), criterion="bic"
)
selection = backward_select(
    linear_fit, y, linear_design, {"x": ("asis(x)",)}
)
assert len(influence.observations) == len(y)
assert len(vifs) == 1 and vifs[0].value == 1.0
assert robustness.covariance == robust
assert penalty_trace.selected_point in penalty_trace.points
assert selection.selected_terms == ("x",)

plot_spec = PlotSpec(
    plot_id="artifact-calibration",
    kind="calibration",
    title="Calibration",
    alt_text="Estimated calibration line with an uncertainty interval.",
    x_axis=AxisSpec("Predicted", scale="probability"),
    y_axis=AxisSpec("Observed", scale="probability"),
    layers=(
        BandLayer("interval", (0.1, 0.5, 0.9), (0.0, 0.4, 0.8),
                  (0.2, 0.6, 1.0), label="Interval"),
        LineLayer("estimate", (0.1, 0.5, 0.9), (0.1, 0.5, 0.9),
                  label="Estimate"),
    ),
    legend_order=("estimate", "interval"),
)
assert PlotSpec.from_json(plot_spec.to_json()) == plot_spec
effect_spec = effect_plot_spec(prediction_result, x, predictor_label="x")
effect_svg = render_svg(effect_spec)
assert 'role="img"' in effect_svg and "holocron-plot-spec/v1" in effect_svg
nomogram = build_nomogram(fit, formula_spec, metadata)
assert NomogramGeometry.from_json(nomogram.to_json()) == nomogram
nomogram_svg = render_nomogram_svg(nomogram)
assert 'role="img"' in nomogram_svg and "Total points" in nomogram_svg
summary_table = model_summary_table(summarize(fit))
assert TableSpec.from_json(summary_table.to_json()) == summary_table
summary_latex = render_latex(summary_table)
assert "\\\\begin{table}" in summary_latex and "Estimate" in summary_latex

resample_plan = ResamplePlan.k_fold(6, folds=3, repeats=2, seed=7)
assert ResamplePlan.from_json(resample_plan.to_json()) == resample_plan
resample_execution = run_resample_plan(
    resample_plan,
    lambda split: sum(take_rows(y, split.assessment_indices, plan=resample_plan)),
)
assert resample_execution.status == "complete"
assert resample_execution.plan_fingerprint == resample_plan.fingerprint
model_validation = validate_model(linear_fit, y, linear_design, resample_plan)
model_calibration = calibrate_model(
    linear_fit, y, linear_design, resample_plan, grid_points=5
)
assert model_validation.status == "complete"
assert model_validation.resamples.plan_fingerprint == resample_plan.fingerprint
assert model_calibration.status == "complete"
assert len(model_calibration.apparent_curve) == 5
corrected_validation = optimism_correct_validation(model_validation)
corrected_calibration = optimism_correct_calibration(model_calibration)
pooled_fit = pool_imputation_models((linear_fit, linear_fit))
pooled_validation = pool_imputation_validation(
    (corrected_validation, corrected_validation)
)
pooled_calibration = pool_imputation_calibration(
    (corrected_calibration, corrected_calibration)
)
pooled_anova = pool_imputation_likelihood_ratio(
    (
        LikelihoodRatioAnova((LikelihoodRatioTest("x", ("asis(x)",), 2.0, 1),)),
        LikelihoodRatioAnova((LikelihoodRatioTest("x", ("asis(x)",), 3.0, 1),)),
    ),
    stacked=LikelihoodRatioAnova(
        (LikelihoodRatioTest("x", ("asis(x)",), 4.0, 1),)
    ),
)
resample_report = report_resample_execution(
    corrected_validation.resamples,
    metric_contributors={
        metric.name: metric.contributing_resamples
        for metric in corrected_validation.metrics
    },
)
assert corrected_validation.status == "complete"
assert corrected_validation.metric("mean_squared_error").corrected is not None
assert corrected_calibration.status == "complete"
assert len(corrected_calibration.corrected_curve) == 5
assert PooledModelResult.from_json(pooled_fit.to_json()) == pooled_fit
assert (
    PooledValidationResult.from_json(pooled_validation.to_json())
    == pooled_validation
)
assert (
    PooledCalibrationResult.from_json(pooled_calibration.to_json())
    == pooled_calibration
)
assert MultipleImputationAnovaResult.from_json(pooled_anova.to_json()) == pooled_anova
assert resample_report.aggregation_permitted
assert resample_report.failure_rate == 0.0
assert len(resample_report.metric_coverage) == 4

binary_x = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0) * 2
binary_y = (0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1)
binary_spec = DesignSpec.from_formula("event ~ x")
binary_design = binary_spec.transform({"x": binary_x})
binary_fit = fit_lrm(binary_y, binary_design)
penalized_binary = fit_penalized_lrm(binary_y, binary_design, penalty=1.0)
binary_restored = BinaryLogisticResult.from_json(binary_fit.to_json())
assert binary_fit.design_fingerprint == binary_spec.fingerprint
assert (
    binary_restored.predict_probability(binary_design)
    == binary_fit.fitted_probabilities
)
assert len(residuals(binary_fit, response=binary_y).values) == len(binary_y)
assert predict(binary_fit, binary_design).scale == "response"
assert likelihood(binary_fit).parameter_count == binary_fit.rank
assert penalized_binary.penalty_weights == (1.0,)
probability_validation = validate_probabilities(
    binary_y,
    binary_fit.fitted_probabilities,
    calibration_groups=4,
    thresholds=(0.4, 0.5, 0.6),
)
assert probability_validation.auc >= 0.5
assert len(probability_validation.calibration_groups) >= 1
assert len(probability_validation.threshold_metrics) == 3

ordinal_y = (1, 1, 2, 2, 3, 3, 1, 2, 3, 1, 2, 3)
ordinal_x = ((-2.0,), (-1.5,), (-1.0,), (-0.5,), (0.0,), (0.5,),
             (1.0,), (1.5,), (2.0,), (-0.75,), (0.25,), (1.25,))
ordinal_fit = fit_orm(ordinal_y, ordinal_x, feature_names=("x",))
ordinal_lrm = fit_ordinal_lrm(ordinal_y, ordinal_x, feature_names=("x",))
censored = CensoredResponse.from_intervals(
    (1, 1, 2, 2, 3, 3, -np.inf, 1, 2, 1, 2, 3),
    (1, 1, 2, 2, 3, 3, 2, np.inf, 3, 1, 2, 3),
)
turnbull = censored.turnbull()
assert turnbull.converged
assert ordinal_fit.estimator == "orm"
assert ordinal_lrm.estimator == "lrm"
assert OrdinalResult.from_json(ordinal_fit.to_json()) == ordinal_fit
assert np.allclose(np.sum(ordinal_fit.fitted_probabilities, axis=1), 1.0)

survival_time = (12, 9, 15, 7, 11, 6, 8, 4, 5, 10, 13, 7, 3, 6, 14, 9, 5, 2)
survival_event = (1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1, 0, 0, 1, 1, 1)
survival_x = tuple((value,) for value in
                   (-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2,
                    -1.8, -0.8, 0.2, 1.2, 2.2, -2.2, -1.2, 0.8, 1.8))
survival_entry = tuple(float(min(index % 3, time - 1))
                       for index, time in enumerate(survival_time))
survival_strata = tuple("A" if index % 2 == 0 else "B" for index in range(18))
survival_weights = tuple(1.0 + 0.5 * (index % 3) for index in range(18))
survival_offsets = tuple(0.05 * (index % 4 - 1.5) for index in range(18))
cox_fit = fit_cph(
    survival_time, survival_event, survival_x, feature_names=("x",),
    entry_times=survival_entry, strata=survival_strata,
    weights=survival_weights, offsets=survival_offsets,
)
psm_fit = fit_psm(
    survival_time, survival_event, survival_x, feature_names=("x",),
    strata=survival_strata, weights=survival_weights, offsets=survival_offsets,
)
censored_response = SurvivalResponse.from_intervals(
    (12, 8, 12, 7, 10, -np.inf, 7, -np.inf, 5, 8, 12, 7),
    (12, 10, np.inf, 7, np.inf, 7, 9, 5, 5, np.inf, 14, 7),
)
censored_psm_fit = fit_psm(
    censored_response, survival_x[:12], feature_names=("x",)
)
bj_fit = fit_buckley_james(
    (1.1, 1.7, 2.4, 3.0, 4.8, 5.5, 7.2, 8.0, 9.5, 11.0),
    (1, 1, 1, 1, 1, 0, 1, 0, 1, 0),
    tuple((float(value),) for value in range(-3, 7)),
    feature_names=("x",),
)
exponential_fit = fit_psm(
    survival_time, survival_event, survival_x, distribution="exponential"
)
ph_fit = to_proportional_hazards(exponential_fit)
km_fit = fit_npsurv(
    survival_time, survival_event, entry_times=survival_entry,
    strata=survival_strata, weights=survival_weights,
)
assert CoxResult.from_json(cox_fit.to_json()) == cox_fit
assert ParametricSurvivalResult.from_json(psm_fit.to_json()) == psm_fit
assert BuckleyJamesResult.from_json(bj_fit.to_json()) == bj_fit
assert ProportionalHazardsParametricResult.from_json(ph_fit.to_json()) == ph_fit
assert censored_psm_fit.log_likelihood[1] > censored_psm_fit.log_likelihood[0]
assert NonparametricSurvivalResult.from_json(km_fit.to_json()) == km_fit
assert len(cox_fit.predict_survival(
    ((0.0,),), (3.0, 6.0), strata=("A",), offsets=(0.1,)
)) == 1
assert len(cox_fit.predict_curve(
    ((0.0,),), (0.0, 3.0, 6.0), strata=("A",), offsets=(0.1,)
).survival) == 1
assert len(cox_fit.predict_quantile(
    ((0.0,),), strata=("A",), offsets=(0.1,)
)) == 1
assert len(cox_fit.predict_mean(
    ((0.0,),), restricted_time=6.0, strata=("A",), offsets=(0.1,)
)) == 1
assert len(psm_fit.predict_hazard(
    ((0.0,),), (3.0, 6.0), strata=("B",), offsets=(-0.1,)
)) == 1
assert len(psm_fit.predict_curve(
    ((0.0,),), (3.0, 6.0), strata=("B",), offsets=(-0.1,)
).survival) == 1
assert len(psm_fit.predict_quantile(
    ((0.0,),), strata=("B",), offsets=(-0.1,)
)) == 1
assert len(psm_fit.predict_mean(
    ((0.0,),), strata=("B",), offsets=(-0.1,)
)) == 1
validation = validate_survival_predictions(
    survival_time,
    survival_event,
    psm_fit.predict_survival(
        survival_x,
        (3.0, 6.0),
        strata=survival_strata,
        offsets=survival_offsets,
    ),
    (3.0, 6.0),
    weights=survival_weights,
)
assert validation.integrated_brier_score is not None
assert validation.integrated_auc is not None
assert validation.integrated_absolute_calibration_error is not None
assert len(validation.calibration_groups) == 2
assert len(validation.threshold_metrics) == 2
assert len(survival_residuals(
    cox_fit, survival_time, survival_event,
    entry_times=survival_entry, strata=survival_strata,
).values) == len(survival_time)
assert len(km_fit.predict((3.0, 6.0), stratum="A")) == 2
assert len(km_fit.predict_curve(strata=("A",)).survival) == 1
assert len(km_fit.predict_quantile(strata=("A",))) == 1
assert len(km_fit.predict_mean(restricted_time=6.0, strata=("A",))) == 1
schema_root = importlib.resources.files("holocron").joinpath("schemas")
assert schema_root.joinpath("serialization-manifest.json").is_file()
assert schema_root.joinpath("ols-result.schema.json").is_file()
assert schema_root.joinpath("binary-logistic-result.schema.json").is_file()
assert schema_root.joinpath("ordinal-result.schema.json").is_file()
assert schema_root.joinpath("cox-result.schema.json").is_file()
assert schema_root.joinpath("cox-result-v2.schema.json").is_file()
assert schema_root.joinpath("parametric-survival-result.schema.json").is_file()
assert schema_root.joinpath("parametric-survival-result-v2.schema.json").is_file()
assert schema_root.joinpath("nonparametric-survival-result.schema.json").is_file()
assert schema_root.joinpath("nonparametric-survival-result-v2.schema.json").is_file()
print(f"artifact smoke passed: {module_path}")
"""


def run(
    command: Sequence[str],
    *,
    cwd: Path = ROOT,
    environment: Mapping[str, str] | None = None,
    display: str | None = None,
) -> None:
    """Run one checked subprocess with stable display and no shell."""
    print("+ " + (display or " ".join(command)), flush=True)
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def require_clean_checkout() -> None:
    """Reject tracked or untracked source changes before a release-style build."""
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    if completed.stdout:
        paths = ", ".join(line[3:] for line in completed.stdout.splitlines())
        raise ValueError(f"clean artifact build requires a clean checkout: {paths}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment_python(environment_root: Path) -> Path:
    if os.name == "nt":
        return environment_root / "Scripts/python.exe"
    return environment_root / "bin/python"


def installable_artifact(artifact: Path, *, workspace: Path) -> Path:
    """Return a wheel, rebuilding an sdist with the frozen project backend."""
    if artifact.suffix == ".whl":
        return artifact
    wheel_directory = workspace / "sdist-install-wheel"
    run(
        (
            "uv",
            "build",
            "--wheel",
            "--offline",
            "--no-python-downloads",
            "--no-build-isolation",
            "--clear",
            "--no-create-gitignore",
            "--out-dir",
            str(wheel_directory),
            str(artifact),
        ),
        cwd=workspace,
    )
    wheels = sorted(wheel_directory.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("source distribution did not produce exactly one wheel")
    return wheels[0]


def smoke_install(
    artifact: Path,
    *,
    constraints: Path,
    environment_root: Path,
    workspace: Path,
    version: str,
) -> None:
    """Install one artifact into a fresh venv and exercise its public slice."""
    installable = installable_artifact(artifact, workspace=workspace)
    run(
        (
            "uv",
            "venv",
            "--offline",
            "--no-project",
            "--no-python-downloads",
            "--python",
            sys.executable,
            str(environment_root),
        ),
        cwd=workspace,
    )
    python = environment_python(environment_root)
    run(
        (
            "uv",
            "pip",
            "install",
            "--no-python-downloads",
            "--strict",
            "--constraints",
            str(constraints),
            "--python",
            str(python),
            str(installable),
        ),
        cwd=workspace,
    )
    run(
        (
            "uv",
            "pip",
            "check",
            "--offline",
            "--no-python-downloads",
            "--python",
            str(python),
        ),
        cwd=workspace,
    )
    smoke_environment = dict(os.environ)
    smoke_environment.pop("PYTHONPATH", None)
    smoke_environment["PYTHONNOUSERSITE"] = "1"
    smoke_environment["HOLOCRON_SMOKE_SOURCE_ROOT"] = str(ROOT)
    smoke_environment["HOLOCRON_SMOKE_ENVIRONMENT_ROOT"] = str(environment_root)
    smoke_environment["HOLOCRON_SMOKE_VERSION"] = version
    run(
        (str(python), "-I", "-c", SMOKE_PROGRAM),
        cwd=workspace,
        environment=smoke_environment,
        display=f"{python} -I -c <artifact-smoke-program>",
    )


def build_and_smoke(output_directory: Path, *, require_clean: bool) -> None:
    if require_clean:
        require_clean_checkout()
    output_directory.mkdir(parents=True, exist_ok=True)
    run(
        (
            "uv",
            "build",
            "--offline",
            "--no-python-downloads",
            "--no-build-isolation",
            "--clear",
            "--no-create-gitignore",
            "--out-dir",
            str(output_directory),
            str(ROOT),
        )
    )
    sdist, wheel = inspect_artifacts(output_directory)
    _, version = project_identity()
    print(
        "build artifacts verified: "
        f"{sdist.name} sha256={sha256(sdist)}, "
        f"{wheel.name} sha256={sha256(wheel)}",
        flush=True,
    )

    with tempfile.TemporaryDirectory(prefix="holocron-artifact-smoke-") as temporary:
        workspace = Path(temporary).resolve()
        constraints = workspace / "locked-constraints.txt"
        run(
            (
                "uv",
                "export",
                "--offline",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-hashes",
                "--no-header",
                "--no-annotate",
                "--quiet",
                "--output-file",
                str(constraints),
            )
        )
        smoke_install(
            wheel,
            constraints=constraints,
            environment_root=workspace / "wheel-environment",
            workspace=workspace,
            version=version,
        )
        smoke_install(
            sdist,
            constraints=constraints,
            environment_root=workspace / "sdist-environment",
            workspace=workspace,
            version=version,
        )
    print("artifact installation smoke tests passed: wheel, sdist")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "dist",
        help="cleared destination for the built wheel and source distribution",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="reject source changes before building",
    )
    args = parser.parse_args()
    build_and_smoke(args.output_directory.resolve(), require_clean=args.require_clean)


if __name__ == "__main__":
    main()
