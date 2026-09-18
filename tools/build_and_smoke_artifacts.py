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
from holocron.models import (
    BinaryLogisticResult,
    OlsResult,
    anova,
    bootstrap_covariance,
    contrast,
    covariance,
    fit_lrm,
    fit_ols,
    fit_penalized_lrm,
    fit_penalized_ols,
    likelihood,
    predict,
    residuals,
    robust_covariance,
    summarize,
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
assert len(predict(fit, formula_design).values) == len(y)

linear_spec = DesignSpec.from_formula("y ~ x")
linear_design = linear_spec.transform({"x": x})
linear_fit = fit_ols(y, linear_design)
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
schema_root = importlib.resources.files("holocron").joinpath("schemas")
assert schema_root.joinpath("serialization-manifest.json").is_file()
assert schema_root.joinpath("ols-result.schema.json").is_file()
assert schema_root.joinpath("binary-logistic-result.schema.json").is_file()
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
