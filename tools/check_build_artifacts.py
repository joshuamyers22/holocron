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
    "governance",
    "reference",
    "templates",
    "tests",
    "tools",
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
    if f"Name: {distribution}\n" not in metadata:
        raise ValueError("wheel metadata has the wrong distribution name")
    print(f"build artifacts verified: {sdist.name}, {wheel.name}")


if __name__ == "__main__":
    main()
