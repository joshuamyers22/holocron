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
import importlib.util
import os
import sys
from pathlib import Path

import numpy as np

import holocron
from holocron.design import RestrictedCubicSplineSpec
from holocron.models import fit_ols

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
spec = RestrictedCubicSplineSpec((-2.0, 0.0, 1.5, 3.0))
design = spec.transform(x)
fit = fit_ols(y, design, feature_names=("x", "x'", "x''"))
predictions = fit.predict(design)

assert design.shape == (6, 3)
assert fit.coefficient_names == ("Intercept", "x", "x'", "x''")
assert fit.rank == 4
assert fit.residual_degrees_of_freedom == 2
assert np.allclose(predictions, fit.fitted_values)
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
