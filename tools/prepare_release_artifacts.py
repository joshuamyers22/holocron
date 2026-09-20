"""Create an exact-commit release manifest and deterministic checksum index."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from reference.contracts import JsonValue, load_json, validate_document
from tools.check_build_artifacts import inspect_artifacts, project_identity
from tools.verify_release import verify_changelog

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA = ROOT / "schemas/phase-9-release-manifest.schema.json"
SBOM_NAME = "release-sbom.cdx.json"
MANIFEST_NAME = "release-manifest.json"
CHECKSUM_NAME = "SHA256SUMS"
SOURCE_REPOSITORY = "https://github.com/joshuamyers22/holocron"
WORKFLOW = ".github/workflows/release.yml"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source_revision(value: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("source revision must be a full lowercase Git commit SHA")
    return value


def repository_file(value: str, *, name: str) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{name} must be a safe repository-relative path")
    resolved = (ROOT / path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_file():
        raise ValueError(f"{name} does not identify an existing repository file")
    return path.as_posix()


def validate_sbom(path: Path) -> None:
    value = load_json(path)
    if not isinstance(value, dict):
        raise ValueError("release SBOM must be a JSON object")
    if value.get("bomFormat") != "CycloneDX":
        raise ValueError("release SBOM is not CycloneDX")
    spec = value.get("specVersion")
    if not isinstance(spec, str) or re.fullmatch(r"[0-9]+\.[0-9]+", spec) is None:
        raise ValueError("release SBOM has no valid CycloneDX specVersion")
    major, minor = (int(part) for part in spec.split("."))
    if (major, minor) < (1, 4):
        raise ValueError("release SBOM must use CycloneDX 1.4 or newer")


def artifact_record(role: str, path: Path) -> dict[str, JsonValue]:
    size = path.stat().st_size
    if size < 1:
        raise ValueError(f"release artifact is empty: {path.name}")
    return {
        "role": role,
        "filename": path.name,
        "sha256": sha256(path),
        "size": size,
    }


def build_manifest(
    *,
    wheel: Path,
    sdist: Path,
    sbom: Path,
    source_revision: str,
    release_tag: str,
    approval_record: str,
    generated_at: str,
    workflow_ref: str,
    run_url: str | None,
) -> dict[str, JsonValue]:
    distribution, version = project_identity()
    if release_tag != f"v{version}":
        raise ValueError("release tag does not match project version")
    validate_source_revision(source_revision)
    verify_changelog(ROOT / "CHANGELOG.md", version)
    approval = repository_file(approval_record, name="approval record")
    try:
        parsed_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("generated_at must be an ISO 8601 timestamp") from error
    if parsed_time.tzinfo is None:
        raise ValueError("generated_at must include a timezone")
    document: dict[str, JsonValue] = {
        "schema_version": "holocron-release-manifest/v1",
        "distribution": distribution,
        "version": version,
        "release_tag": release_tag,
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": source_revision,
        "generated_at": generated_at,
        "builder": {
            "workflow": WORKFLOW,
            "workflow_ref": workflow_ref,
            "run_url": run_url,
            "oidc_issuer": OIDC_ISSUER,
        },
        "authorization": {"approval_record": approval},
        "materials": {
            "changelog": "CHANGELOG.md",
            "support_policy": "SUPPORT.md",
            "contribution_provenance": "governance/PROVENANCE.md",
            "artifact_policy": "governance/phase-9-artifact-policy.json",
        },
        "artifacts": [
            artifact_record("wheel", wheel),
            artifact_record("sdist", sdist),
            artifact_record("sbom", sbom),
        ],
    }
    validate_document(document, MANIFEST_SCHEMA)
    return document


def write_manifest(path: Path, document: dict[str, JsonValue]) -> None:
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_checksums(path: Path, artifacts: Sequence[Path]) -> None:
    names = [artifact.name for artifact in artifacts]
    if len(names) != len(set(names)):
        raise ValueError("checksum inputs contain duplicate filenames")
    lines = [f"{sha256(artifact)}  {artifact.name}" for artifact in artifacts]
    path.write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")


def prepare(
    directory: Path,
    *,
    source_revision: str,
    release_tag: str,
    approval_record: str,
    generated_at: str,
    workflow_ref: str,
    run_url: str | None,
) -> tuple[Path, Path]:
    directory = directory.resolve()
    sdist, wheel = inspect_artifacts(directory)
    sbom = directory / SBOM_NAME
    if not sbom.is_file():
        raise FileNotFoundError(f"release SBOM is missing: {sbom}")
    validate_sbom(sbom)
    manifest = directory / MANIFEST_NAME
    document = build_manifest(
        wheel=wheel,
        sdist=sdist,
        sbom=sbom,
        source_revision=source_revision,
        release_tag=release_tag,
        approval_record=approval_record,
        generated_at=generated_at,
        workflow_ref=workflow_ref,
        run_url=run_url,
    )
    write_manifest(manifest, document)
    checksums = directory / CHECKSUM_NAME
    write_checksums(checksums, (wheel, sdist, sbom, manifest))
    return manifest, checksums


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--directory", type=Path, default=ROOT / "dist")
    command.add_argument("--source-revision", required=True)
    command.add_argument("--release-tag", required=True)
    command.add_argument("--approval-record", required=True)
    command.add_argument(
        "--generated-at", default=datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    command.add_argument("--workflow-ref", required=True)
    command.add_argument("--run-url")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest, checksums = prepare(
        cast(Path, args.directory),
        source_revision=cast(str, args.source_revision),
        release_tag=cast(str, args.release_tag),
        approval_record=cast(str, args.approval_record),
        generated_at=cast(str, args.generated_at),
        workflow_ref=cast(str, args.workflow_ref),
        run_url=cast(str | None, args.run_url),
    )
    print(f"release traceability files created: {manifest.name}, {checksums.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
