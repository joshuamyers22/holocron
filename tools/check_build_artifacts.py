"""Inspect built artifacts for identity and reference-environment isolation."""

from __future__ import annotations

import argparse
import tarfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {
    "compatibility",
    "docs",
    "environments",
    "governance",
    "reference",
    "templates",
    "tests",
    "tools",
}
REMOVED_TEMPLATE_MODULES = {
    "analysis_cli.py",
    "cli.py",
    "dataset.py",
    "dataset_cli.py",
    "evidence.py",
    "ingest.py",
    "model.py",
    "regression.py",
    "time_validation_cli.py",
    "validation.py",
    "validation_evidence.py",
}


def project_identity() -> tuple[str, str]:
    parsed = cast(
        dict[str, object], tomllib.loads((ROOT / "pyproject.toml").read_text())
    )
    project = parsed["project"]
    if not isinstance(project, dict):
        raise TypeError("pyproject.toml project must be a table")
    typed_project = cast(dict[str, object], project)
    return str(typed_project["name"]), str(typed_project["version"])


def reject_forbidden(names: list[str], *, artifact: str) -> None:
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"{artifact} contains an unsafe path: {name}")
        parts = set(path.parts)
        if parts & FORBIDDEN_PARTS or "rms-master" in name or name.endswith(".R"):
            raise ValueError(f"{artifact} contains forbidden reference content: {name}")
        if "__pycache__" in parts or name.endswith((".pyc", ".pyo")):
            raise ValueError(f"{artifact} contains generated Python content: {name}")
        if path.name in REMOVED_TEMPLATE_MODULES:
            raise ValueError(f"{artifact} contains removed template module: {name}")


def validate_identity(
    metadata: str, *, distribution: str, version: str, artifact: str
) -> None:
    for field in (f"Name: {distribution}\n", f"Version: {version}\n"):
        if field not in metadata:
            raise ValueError(f"{artifact} metadata has the wrong project identity")


def inspect_artifacts(directory: Path) -> tuple[Path, Path]:
    """Inspect the expected sdist and wheel, then return their paths."""
    distribution, version = project_identity()
    normalized = distribution.replace("-", "_")
    sdist = directory / f"{normalized}-{version}.tar.gz"
    wheel = directory / f"{normalized}-{version}-py3-none-any.whl"
    if not sdist.is_file() or not wheel.is_file():
        raise FileNotFoundError("expected wheel and source distribution are missing")

    sdist_root = f"{normalized}-{version}"
    with tarfile.open(sdist, mode="r:gz") as archive:
        sdist_members = archive.getmembers()
        sdist_names = [member.name for member in sdist_members]
        if any(member.issym() or member.islnk() for member in sdist_members):
            raise ValueError("source distribution contains links")
        metadata_member = next(
            member
            for member in sdist_members
            if member.name == f"{sdist_root}/PKG-INFO"
        )
        metadata_file = archive.extractfile(metadata_member)
        if metadata_file is None:
            raise ValueError("source distribution metadata is not a regular file")
        sdist_metadata = metadata_file.read().decode()
    reject_forbidden(sdist_names, artifact=sdist.name)
    expected_sdist_files = {
        f"{sdist_root}/LICENSE",
        f"{sdist_root}/README.md",
        f"{sdist_root}/pyproject.toml",
        f"{sdist_root}/src/holocron/__init__.py",
        f"{sdist_root}/src/holocron/py.typed",
        f"{sdist_root}/schemas/binary-logistic-result.schema.json",
        f"{sdist_root}/schemas/buckley-james-result.schema.json",
        f"{sdist_root}/schemas/cox-result.schema.json",
        f"{sdist_root}/schemas/cox-result-v2.schema.json",
        f"{sdist_root}/schemas/data-distribution.schema.json",
        f"{sdist_root}/schemas/design-matrix.schema.json",
        f"{sdist_root}/schemas/design-spec.schema.json",
        f"{sdist_root}/schemas/formula.schema.json",
        f"{sdist_root}/schemas/gls-result.schema.json",
        f"{sdist_root}/schemas/ols-result.schema.json",
        f"{sdist_root}/schemas/nonparametric-survival-result.schema.json",
        f"{sdist_root}/schemas/nonparametric-survival-result-v2.schema.json",
        f"{sdist_root}/schemas/nomogram-geometry.schema.json",
        f"{sdist_root}/schemas/ordinal-result.schema.json",
        f"{sdist_root}/schemas/parametric-survival-result.schema.json",
        f"{sdist_root}/schemas/parametric-survival-result-v2.schema.json",
        f"{sdist_root}/schemas/plot-spec.schema.json",
        f"{sdist_root}/schemas/proportional-hazards-result.schema.json",
        f"{sdist_root}/schemas/quantile-regression-result.schema.json",
        f"{sdist_root}/schemas/resample-plan.schema.json",
        f"{sdist_root}/schemas/table-spec.schema.json",
        f"{sdist_root}/schemas/serialization-manifest.json",
    }
    if not expected_sdist_files <= set(sdist_names):
        raise ValueError("source distribution is missing required project files")
    validate_identity(
        sdist_metadata,
        distribution=distribution,
        version=version,
        artifact=sdist.name,
    )

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
        metadata_name = next(
            name for name in wheel_names if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode()
    reject_forbidden(wheel_names, artifact=wheel.name)
    expected_wheel_roots = {"holocron", f"{normalized}-{version}.dist-info"}
    actual_wheel_roots = {PurePosixPath(name).parts[0] for name in wheel_names}
    if actual_wheel_roots != expected_wheel_roots:
        raise ValueError(
            f"wheel has unexpected top-level content: {actual_wheel_roots}"
        )
    if "holocron/__init__.py" not in wheel_names:
        raise ValueError("wheel does not contain the holocron import package")
    if "holocron/py.typed" not in wheel_names:
        raise ValueError("wheel does not contain the PEP 561 marker")
    expected_schema_files = {
        "holocron/schemas/binary-logistic-result.schema.json",
        "holocron/schemas/buckley-james-result.schema.json",
        "holocron/schemas/cox-result.schema.json",
        "holocron/schemas/cox-result-v2.schema.json",
        "holocron/schemas/data-distribution.schema.json",
        "holocron/schemas/design-matrix.schema.json",
        "holocron/schemas/design-spec.schema.json",
        "holocron/schemas/formula.schema.json",
        "holocron/schemas/gls-result.schema.json",
        "holocron/schemas/ols-result.schema.json",
        "holocron/schemas/nonparametric-survival-result.schema.json",
        "holocron/schemas/nonparametric-survival-result-v2.schema.json",
        "holocron/schemas/nomogram-geometry.schema.json",
        "holocron/schemas/ordinal-result.schema.json",
        "holocron/schemas/parametric-survival-result.schema.json",
        "holocron/schemas/parametric-survival-result-v2.schema.json",
        "holocron/schemas/plot-spec.schema.json",
        "holocron/schemas/proportional-hazards-result.schema.json",
        "holocron/schemas/quantile-regression-result.schema.json",
        "holocron/schemas/resample-plan.schema.json",
        "holocron/schemas/table-spec.schema.json",
        "holocron/schemas/serialization-manifest.json",
    }
    if not expected_schema_files <= set(wheel_names):
        raise ValueError("wheel is missing public serialization schemas")
    if any(name.endswith(".dist-info/entry_points.txt") for name in wheel_names):
        raise ValueError("library wheel unexpectedly declares console entry points")
    validate_identity(
        metadata,
        distribution=distribution,
        version=version,
        artifact=wheel.name,
    )
    for removed_dependency in ("polars", "statsmodels"):
        if f"requires-dist: {removed_dependency}" in metadata.lower():
            raise ValueError(
                f"wheel retains removed runtime dependency: {removed_dependency}"
            )
    return sdist, wheel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory",
        type=Path,
        default=ROOT / "dist",
        help="directory containing the wheel and source distribution",
    )
    args = parser.parse_args()
    sdist, wheel = inspect_artifacts(args.directory.resolve())
    print(f"build artifacts verified: {sdist.name}, {wheel.name}")


if __name__ == "__main__":
    main()
