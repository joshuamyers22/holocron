"""Validate the Phase 9 release supply-chain contract and optional artifact set."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)
from tools.check_build_artifacts import inspect_artifacts
from tools.prepare_release_artifacts import (
    CHECKSUM_NAME,
    MANIFEST_NAME,
    MANIFEST_SCHEMA,
    SBOM_NAME,
    sha256,
    validate_sbom,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "governance/phase-9-artifact-policy.json"
POLICY_SCHEMA = ROOT / "schemas/phase-9-artifact-policy.schema.json"
WORKFLOW = ROOT / ".github/workflows/release.yml"
REQUIRED_ROLES = ("wheel", "sdist", "sbom", "provenance", "checksums")


def check_policy() -> dict[str, JsonValue]:
    value = load_json(POLICY)
    validate_document(value, POLICY_SCHEMA)
    policy = require_object(value, name="artifact policy")
    artifact_set = require_array(policy["artifact_set"], name="artifact_set")
    roles = tuple(
        cast(str, require_object(item, name="artifact_set item")["role"])
        for item in artifact_set
    )
    if roles != REQUIRED_ROLES:
        raise ValueError("artifact policy roles differ or are out of order")
    signing = require_object(policy["signing"], name="signing")
    signed_roles = tuple(cast(list[str], signing["signed_roles"]))
    if set(signed_roles) != set(REQUIRED_ROLES):
        raise ValueError("every release artifact role must be signed")
    traceability = require_object(policy["traceability"], name="traceability")
    for key in (
        "manifest_schema",
        "changelog",
        "support_policy",
        "contribution_provenance",
    ):
        path = ROOT / cast(str, traceability[key])
        if not path.is_file():
            raise ValueError(f"artifact policy references missing file: {path}")
    return policy


def check_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    requirements = (
        "id-token: write",
        "persist-credentials: false",
        "tools.prepare_release_artifacts",
        "release-sbom.cdx.json",
        "verify: true",
        "verify-cert-identity:",
        "verify-oidc-issuer: https://token.actions.githubusercontent.com",
        '--expected-revision "$GITHUB_SHA"',
        "files: dist/*",
    )
    missing = [requirement for requirement in requirements if requirement not in text]
    if missing:
        raise ValueError(f"release workflow lacks supply-chain controls: {missing}")
    action = re.search(
        r"sigstore/gh-action-sigstore-python@([0-9a-f]{40}) # v3\.4\.0", text
    )
    if action is None:
        raise ValueError("Sigstore action must be pinned to the reviewed v3.4.0 SHA")
    if text.index("tools.prepare_release_artifacts") > text.index(
        "sigstore/gh-action-sigstore-python"
    ):
        raise ValueError("release metadata must be created before signing")
    signing_index = text.index("sigstore/gh-action-sigstore-python")
    evidence_index = text.index('--expected-revision "$GITHUB_SHA"')
    publication_index = text.index("softprops/action-gh-release")
    if signing_index > publication_index:
        raise ValueError("release assets must be signed before publication")
    if not signing_index < evidence_index < publication_index:
        raise ValueError("the complete signed set must be checked before publication")


def parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)", line)
        if match is None:
            raise ValueError(f"invalid checksum line {number}")
        digest, filename = match.groups()
        if filename in result:
            raise ValueError(f"duplicate checksum filename: {filename}")
        result[filename] = digest
    return result


def check_artifact_set(
    directory: Path,
    *,
    expected_tag: str | None = None,
    expected_revision: str | None = None,
) -> None:
    directory = directory.resolve()
    sdist, wheel = inspect_artifacts(directory)
    sbom = directory / SBOM_NAME
    manifest_path = directory / MANIFEST_NAME
    checksums_path = directory / CHECKSUM_NAME
    for path in (sbom, manifest_path, checksums_path):
        if not path.is_file():
            raise FileNotFoundError(f"release artifact is missing: {path.name}")
    validate_sbom(sbom)
    manifest_value = load_json(manifest_path)
    validate_document(manifest_value, MANIFEST_SCHEMA)
    manifest = require_object(manifest_value, name="release manifest")
    release_tag = cast(str, manifest["release_tag"])
    if release_tag != f"v{manifest['version']}":
        raise ValueError("release manifest tag differs from its version")
    builder = require_object(manifest["builder"], name="manifest builder")
    expected_workflow_ref = (
        f"joshuamyers22/holocron/.github/workflows/release.yml@refs/tags/{release_tag}"
    )
    if builder["workflow_ref"] != expected_workflow_ref:
        raise ValueError("release manifest workflow ref differs from its tag")
    authorization = require_object(
        manifest["authorization"], name="manifest authorization"
    )
    approval = Path(cast(str, authorization["approval_record"]))
    if approval.is_absolute() or ".." in approval.parts:
        raise ValueError("release manifest approval record is unsafe")
    if expected_tag is not None and manifest["release_tag"] != expected_tag:
        raise ValueError("release manifest tag differs from expected tag")
    if (
        expected_revision is not None
        and manifest["source_revision"] != expected_revision
    ):
        raise ValueError("release manifest revision differs from expected revision")

    primary = (wheel, sdist, sbom, manifest_path)
    expected_checksums = {path.name: sha256(path) for path in primary}
    if parse_checksums(checksums_path) != expected_checksums:
        raise ValueError("SHA256SUMS does not exactly match the release artifact set")

    records = require_array(manifest["artifacts"], name="manifest artifacts")
    actual_by_role = {
        "wheel": wheel,
        "sdist": sdist,
        "sbom": sbom,
    }
    seen: set[str] = set()
    for item in records:
        record = require_object(item, name="manifest artifact")
        role = cast(str, record["role"])
        if role in seen or role not in actual_by_role:
            raise ValueError("release manifest artifact roles are invalid")
        seen.add(role)
        path = actual_by_role[role]
        if (
            record["filename"] != path.name
            or record["sha256"] != sha256(path)
            or record["size"] != path.stat().st_size
        ):
            raise ValueError(f"release manifest record differs for {role}")
    if seen != set(actual_by_role):
        raise ValueError("release manifest does not cover every primary artifact")

    signed = (*primary, checksums_path)
    expected_filenames = {artifact.name for artifact in signed}
    for artifact in signed:
        bundle = directory / f"{artifact.name}.sigstore.json"
        expected_filenames.add(bundle.name)
        if not bundle.is_file() or bundle.stat().st_size < 1:
            raise FileNotFoundError(f"Sigstore bundle is missing: {bundle.name}")
        try:
            parsed = json.loads(bundle.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Sigstore bundle is not valid JSON: {bundle.name}"
            ) from error
        if not isinstance(parsed, dict) or not parsed:
            raise ValueError(f"Sigstore bundle is empty: {bundle.name}")
    actual_filenames = {path.name for path in directory.iterdir() if path.is_file()}
    if actual_filenames != expected_filenames:
        raise ValueError("release directory contains missing or unexpected files")


def check() -> None:
    check_policy()
    check_workflow()


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--artifact-directory", type=Path)
    command.add_argument("--expected-tag")
    command.add_argument("--expected-revision")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    check()
    artifact_directory = cast(Path | None, args.artifact_directory)
    if artifact_directory is not None:
        check_artifact_set(
            artifact_directory,
            expected_tag=cast(str | None, args.expected_tag),
            expected_revision=cast(str | None, args.expected_revision),
        )
        print("Phase 9 signed release artifact set verified")
    else:
        print("Phase 9 release supply-chain contract verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
