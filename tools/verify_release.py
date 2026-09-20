"""Reject a release tag without matching metadata and changelog identity."""

from __future__ import annotations

import argparse
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import cast


def project_version(manifest: Path) -> str:
    document = tomllib.loads(manifest.read_text(encoding="utf-8"))
    project_value: object = document.get("project")
    if not isinstance(project_value, dict):
        raise ValueError(f"{manifest} has no [project] table")
    project = cast(dict[str, object], project_value)
    version: object = project.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{manifest} has no valid project version")
    return version


def verify_release(manifest: Path, tag: str) -> None:
    expected = f"v{project_version(manifest)}"
    if tag != expected:
        raise ValueError(f"release tag {tag!r} does not match {expected!r}")


def verify_changelog(changelog: Path, version: str) -> None:
    """Require one dated release heading for the exact project version."""
    text = changelog.read_text(encoding="utf-8")
    heading = re.compile(
        rf"^## \[{re.escape(version)}\] - [0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$",
        re.MULTILINE,
    )
    matches = heading.findall(text)
    if len(matches) != 1:
        raise ValueError(
            f"{changelog} must contain exactly one dated [{version}] release heading"
        )


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--tag", required=True)
    command.add_argument("--manifest", type=Path, default=Path("pyproject.toml"))
    command.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    manifest = cast(Path, args.manifest)
    version = project_version(manifest)
    verify_release(manifest, cast(str, args.tag))
    verify_changelog(cast(Path, args.changelog), version)
    print(f"release tag {args.tag} matches project metadata and changelog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
