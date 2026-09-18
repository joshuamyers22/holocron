"""Verify the frozen Python environment and R oracle identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import tomllib
from importlib.metadata import distributions
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
PYTHON_MANIFEST = ROOT / "environments/python-3.12.14-lock.json"
R_MANIFEST = ROOT / "environments/r-oracle-8.2-0-lock.json"
R_ENVIRONMENT = ROOT / "reference/expected/oracle-environment.json"


def load_object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return cast(dict[str, object], value)


def object_field(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be an object")
    return cast(dict[str, object], value)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def check_file_hashes(raw_files: object, *, name: str) -> None:
    files = object_field(raw_files, name=name)
    for relative, raw_digest in files.items():
        expected_digest = str(raw_digest)
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"frozen input is missing: {relative}")
        actual_digest = sha256(path)
        if actual_digest != expected_digest:
            raise ValueError(
                f"frozen input changed: {relative}; "
                f"expected {expected_digest}, received {actual_digest}"
            )


def check_python_environment() -> None:
    manifest = load_object(PYTHON_MANIFEST)
    python = object_field(manifest["python"], name="python")
    uv = object_field(manifest["uv"], name="uv")
    lock = object_field(manifest["dependency_lock"], name="dependency_lock")
    build = object_field(manifest["build"], name="build")

    expected_python = str(python["version"])
    if platform.python_implementation() != python["implementation"]:
        raise ValueError("the Python implementation does not match the freeze")
    if platform.python_version() != expected_python:
        raise ValueError(
            f"Python {platform.python_version()} does not match {expected_python}"
        )
    version_file = ROOT / str(python["version_file"])
    if version_file.read_text().strip() != expected_python:
        raise ValueError(".python-version does not match the environment manifest")
    if sha256(version_file) != python["version_file_sha256"]:
        raise ValueError(
            ".python-version digest does not match the environment manifest"
        )

    uv_process = subprocess.run(
        ["uv", "--version"], capture_output=True, check=True, text=True
    )
    actual_uv = uv_process.stdout.strip().split()[1]
    if actual_uv != uv["version"]:
        raise ValueError(f"uv {actual_uv} does not match frozen uv {uv['version']}")

    pyproject = cast(
        dict[str, object], tomllib.loads((ROOT / "pyproject.toml").read_text())
    )
    project = object_field(pyproject["project"], name="project")
    uv_config = object_field(
        object_field(pyproject["tool"], name="tool")["uv"], name="tool.uv"
    )
    if uv_config["required-version"] != uv["required_version"]:
        raise ValueError("tool.uv.required-version does not match the freeze")
    if uv_config["no-build-isolation-package"] != ["holocron-rms"]:
        raise ValueError("uv does not enforce non-isolated Holocron builds")
    build_system = object_field(pyproject["build-system"], name="build-system")
    if build_system["build-backend"] != build["backend"]:
        raise ValueError("build backend does not match the freeze")
    requirements = build_system["requires"]
    if not isinstance(requirements, list) or build["backend_requirement"] not in cast(
        list[object], requirements
    ):
        raise ValueError("build backend requirement does not match the freeze")
    dependency_groups = object_field(
        pyproject["dependency-groups"], name="dependency-groups"
    )
    dev_dependencies = dependency_groups["dev"]
    if not isinstance(dev_dependencies, list):
        raise TypeError("dependency-groups.dev must be a list")
    dev_requirements = {str(item) for item in cast(list[object], dev_dependencies)}
    required_build_tools = {"editables==0.5", str(build["backend_requirement"])}
    if not required_build_tools <= dev_requirements:
        raise ValueError("non-isolated build tools are missing from the dev lock")
    if build["isolation"] is not False:
        raise ValueError("canonical builds must be declared non-isolated")

    makefile = (ROOT / "Makefile").read_text()
    required_make_commands = (
        "uv lock --check",
        "uv sync --frozen --dev --no-install-project",
        "uv sync --frozen --dev --no-build-isolation",
        "uv run --frozen",
        "tools/build_and_smoke_artifacts.py",
        "tools.run_phase_1_vertical_slice",
    )
    if any(command not in makefile for command in required_make_commands):
        raise ValueError("Makefile does not enforce the frozen build sequence")
    artifact_builder = (ROOT / "tools/build_and_smoke_artifacts.py").read_text()
    required_artifact_controls = (
        '"--offline"',
        '"--no-python-downloads"',
        '"--no-build-isolation"',
        '"--frozen"',
        '"--require-clean"',
    )
    if any(control not in artifact_builder for control in required_artifact_controls):
        raise ValueError("artifact builder does not enforce the frozen build contract")
    for relative_workflow in (
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    ):
        workflow = (ROOT / relative_workflow).read_text()
        if (
            'version: "0.12.7"' not in workflow
            or "run: make setup" not in workflow
            or "clean-build" not in workflow
            or "phase-1-exit-gate" not in workflow
        ):
            raise ValueError(
                f"{relative_workflow} does not use the frozen acceptance gates"
            )
    ci_workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    required_evidence_controls = (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        ".work/phase-1-evidence/*.json",
        "if-no-files-found: error",
    )
    if any(control not in ci_workflow for control in required_evidence_controls):
        raise ValueError("CI does not retain the required Phase 1 parity evidence")

    lock_path = ROOT / str(lock["path"])
    if sha256(lock_path) != lock["sha256"]:
        raise ValueError("uv.lock digest does not match the environment manifest")
    lock_data = cast(dict[str, object], tomllib.loads(lock_path.read_text()))
    if lock_data["requires-python"] != project["requires-python"]:
        raise ValueError("uv.lock Python range does not match project metadata")

    expected_packages_raw = object_field(
        manifest["selected_packages"], name="selected_packages"
    )
    expected_packages = {
        canonical_name(name): str(version)
        for name, version in expected_packages_raw.items()
    }
    installed_packages: dict[str, str] = {}
    for distribution in distributions():
        package_name = canonical_name(str(distribution.metadata["Name"]))
        if package_name in installed_packages:
            raise ValueError(f"duplicate installed distribution: {package_name}")
        installed_packages[package_name] = distribution.version
    if installed_packages != expected_packages:
        missing = sorted(expected_packages.keys() - installed_packages.keys())
        extra = sorted(installed_packages.keys() - expected_packages.keys())
        changed = sorted(
            name
            for name in expected_packages.keys() & installed_packages.keys()
            if expected_packages[name] != installed_packages[name]
        )
        raise ValueError(
            "installed Python environment differs from freeze; "
            f"missing={missing}, extra={extra}, changed={changed}"
        )


def check_r_environment(*, live: bool) -> None:
    manifest = load_object(R_MANIFEST)
    image = object_field(manifest["image"], name="image")
    base = object_field(manifest["base_image"], name="base_image")
    r_contract = object_field(manifest["r"], name="r")
    rms = object_field(manifest["rms"], name="rms")
    hmisc = object_field(manifest["hmisc"], name="hmisc")
    check_file_hashes(manifest["files"], name="files")

    environment = load_object(R_ENVIRONMENT)
    response = object_field(environment["response"], name="response")
    packages = object_field(response["packages"], name="response.packages")
    if environment["oracle_image"] != image["tag"]:
        raise ValueError("oracle tag does not match the R freeze")
    if environment["oracle_image_digest"] != image["id"]:
        raise ValueError("oracle image ID does not match the R freeze")
    if environment["rms_commit"] != rms["commit"]:
        raise ValueError("rms commit does not match the R freeze")
    if environment["rms_file_manifest_sha256"] != rms["source_file_manifest_sha256"]:
        raise ValueError("rms source manifest does not match the R freeze")
    if environment["hmisc_commit"] != hmisc["commit"]:
        raise ValueError("Hmisc commit does not match the R freeze")
    if response["r_version"] != r_contract["version"]:
        raise ValueError("R version does not match the R freeze")
    if response["platform"] != r_contract["platform"]:
        raise ValueError("R platform does not match the R freeze")
    if response["package_repository"] != r_contract["repository_snapshot"]:
        raise ValueError("R repository snapshot does not match the R freeze")
    if len(packages) != r_contract["package_count"]:
        raise ValueError("R package count does not match the R freeze")
    if packages.get("rms") != rms["version"]:
        raise ValueError("installed rms version does not match the R freeze")
    if packages.get("Hmisc") != hmisc["version"]:
        raise ValueError("installed Hmisc version does not match the R freeze")
    external_libraries_value = response["external_libraries"]
    expected_library_count = r_contract["external_library_count"]
    if not isinstance(external_libraries_value, list):
        raise TypeError("external library inventory must be a list")
    external_libraries = cast(list[object], external_libraries_value)
    if len(external_libraries) != expected_library_count:
        raise ValueError("external library inventory does not match the R freeze")
    if response["timezone"] != r_contract["timezone"]:
        raise ValueError("R timezone does not match the R freeze")

    dockerfile = (ROOT / "reference/r/Dockerfile").read_text()
    base_identity = f"{base['name']}@{base['digest']}"
    if dockerfile.count(base_identity) != 2:
        raise ValueError("both oracle stages must use the frozen base image")
    for required_value in (
        str(r_contract["repository_snapshot"]),
        str(rms["commit"]),
        str(hmisc["commit"]),
    ):
        if required_value not in dockerfile:
            raise ValueError(f"Dockerfile is missing frozen identity: {required_value}")

    if live:
        completed = subprocess.run(
            ["docker", "image", "inspect", str(image["tag"])],
            capture_output=True,
            check=True,
            text=True,
        )
        inspection_value: object = json.loads(completed.stdout)
        if not isinstance(inspection_value, list):
            raise TypeError("docker inspect response must be a list")
        inspection_items = cast(list[object], inspection_value)
        if len(inspection_items) != 1:
            raise ValueError("docker inspect returned an unexpected response")
        inspection = object_field(inspection_items[0], name="docker image")
        actual_platform = f"{inspection['Os']}/{inspection['Architecture']}"
        if inspection["Id"] != image["id"]:
            raise ValueError("local oracle image ID does not match the R freeze")
        if actual_platform != image["platform"]:
            raise ValueError("local oracle platform does not match the R freeze")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument(
        "--live-r-oracle",
        action="store_true",
        help="also inspect the locally built Docker image",
    )
    return command


def main() -> None:
    args = parser().parse_args()
    check_python_environment()
    check_r_environment(live=cast(bool, args.live_r_oracle))
    mode = "including live R image" if args.live_r_oracle else "static manifests"
    print(f"frozen Python and R environments verified ({mode})")


if __name__ == "__main__":
    main()
