"""Inspect built artifacts for identity and reference-environment isolation."""

from __future__ import annotations

import tarfile
import tomllib
import zipfile
from pathlib import Path
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
        parts = set(Path(name).parts)
        if parts & FORBIDDEN_PARTS or "rms-master" in name or name.endswith(".R"):
            raise ValueError(f"{artifact} contains forbidden reference content: {name}")
        if Path(name).name in REMOVED_TEMPLATE_MODULES:
            raise ValueError(f"{artifact} contains removed template module: {name}")


def main() -> None:
    distribution, version = project_identity()
    normalized = distribution.replace("-", "_")
    sdist = ROOT / f"dist/{normalized}-{version}.tar.gz"
    wheel = ROOT / f"dist/{normalized}-{version}-py3-none-any.whl"
    if not sdist.is_file() or not wheel.is_file():
        raise FileNotFoundError("expected wheel and source distribution are missing")

    with tarfile.open(sdist, mode="r:gz") as archive:
        sdist_names = archive.getnames()
    reject_forbidden(sdist_names, artifact=sdist.name)

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
        metadata_name = next(
            name for name in wheel_names if name.endswith(".dist-info/METADATA")
        )
        metadata = archive.read(metadata_name).decode()
    reject_forbidden(wheel_names, artifact=wheel.name)
    if "holocron/__init__.py" not in wheel_names:
        raise ValueError("wheel does not contain the holocron import package")
    if "holocron/py.typed" not in wheel_names:
        raise ValueError("wheel does not contain the PEP 561 marker")
    if any(name.endswith(".dist-info/entry_points.txt") for name in wheel_names):
        raise ValueError("library wheel unexpectedly declares console entry points")
    if f"Name: {distribution}\n" not in metadata:
        raise ValueError("wheel metadata has the wrong distribution name")
    for removed_dependency in ("polars", "statsmodels"):
        if f"requires-dist: {removed_dependency}" in metadata.lower():
            raise ValueError(
                f"wheel retains removed runtime dependency: {removed_dependency}"
            )
    print(f"build artifacts verified: {sdist.name}, {wheel.name}")


if __name__ == "__main__":
    main()
