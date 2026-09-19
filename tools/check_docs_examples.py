"""Execute explicitly marked Python examples in the documentation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
GETTING_STARTED = DOCS / "getting-started.md"
GALLERY_DIRECTORY = DOCS / "examples/gallery"
GALLERY_MANIFEST = ROOT / "governance/phase-7-gallery-manifest.json"
MKDOCS = ROOT / "mkdocs.yml"
EXECUTABLE_BLOCK = re.compile(
    r"```python\n# holocron: execute\n(?P<source>.*?)```", re.DOTALL
)
GALLERY_SCHEMA_VERSION = "holocron-documentation-gallery/v1"
REQUIRED_GALLERY_IDS = {
    "diagnostics",
    "effects-inference",
    "nomogram-reporting",
    "survival",
    "validation-calibration",
}
REQUIRED_GALLERY_HEADINGS = (
    "## Goal",
    "## Workflow",
    "## Interpretation",
    "## Boundaries",
)
GETTING_STARTED_OUTPUTS = {
    "binary_fit",
    "binary_probabilities",
    "bootstrap_estimate",
    "cluster_covariance",
    "coefficient_summary",
    "design",
    "distribution",
    "fit",
    "future_means",
    "group_contrast",
    "penalized_binary",
    "penalized_fit",
    "restored_binary",
    "restored_fit",
    "specification",
    "term_tests",
}


@dataclass(frozen=True, slots=True)
class GalleryContract:
    """One registered executable gallery workflow."""

    gallery_id: str
    path: Path
    task: str
    required_outputs: frozenset[str]


def _exact_object(
    value: object, expected_keys: set[str], *, role: str
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{role} must be an object")
    result = cast(dict[object, object], value)
    if set(result) != expected_keys or any(not isinstance(key, str) for key in result):
        raise ValueError(f"{role} has invalid fields")
    return cast(dict[str, object], result)


def gallery_contracts() -> tuple[GalleryContract, ...]:
    """Load and validate the complete Phase 7 gallery inventory."""
    raw: object = json.loads(GALLERY_MANIFEST.read_text())
    document = _exact_object(raw, {"schema_version", "galleries"}, role="manifest")
    if document["schema_version"] != GALLERY_SCHEMA_VERSION:
        raise ValueError("unsupported gallery manifest version")
    raw_galleries = document["galleries"]
    if not isinstance(raw_galleries, list):
        raise ValueError("manifest galleries must be an array")
    contracts: list[GalleryContract] = []
    for index, raw_gallery in enumerate(cast(list[object], raw_galleries)):
        gallery = _exact_object(
            raw_gallery,
            {"gallery_id", "path", "task", "required_outputs"},
            role=f"gallery {index}",
        )
        gallery_id = gallery["gallery_id"]
        raw_path = gallery["path"]
        task = gallery["task"]
        outputs = gallery["required_outputs"]
        if (
            not isinstance(gallery_id, str)
            or not gallery_id
            or not isinstance(raw_path, str)
            or not raw_path.startswith("docs/examples/gallery/")
            or not raw_path.endswith(".md")
            or ".." in Path(raw_path).parts
            or not isinstance(task, str)
            or not task.strip()
            or not isinstance(outputs, list)
        ):
            raise ValueError(f"gallery {index} has invalid values")
        raw_outputs = cast(list[object], outputs)
        if (
            not raw_outputs
            or any(
                not isinstance(value, str) or not value.isidentifier()
                for value in raw_outputs
            )
            or len(set(cast(list[str], raw_outputs))) != len(raw_outputs)
        ):
            raise ValueError(f"gallery {index} has invalid required outputs")
        contracts.append(
            GalleryContract(
                gallery_id,
                ROOT / raw_path,
                task,
                frozenset(cast(list[str], raw_outputs)),
            )
        )
    if {contract.gallery_id for contract in contracts} != REQUIRED_GALLERY_IDS or len(
        {contract.path for contract in contracts}
    ) != len(contracts):
        raise ValueError("gallery inventory is incomplete or contains duplicates")
    actual_pages = set(GALLERY_DIRECTORY.glob("*.md"))
    registered_pages = {contract.path for contract in contracts}
    if actual_pages != registered_pages:
        raise ValueError("gallery directory and manifest do not contain the same pages")
    nav = MKDOCS.read_text()
    for contract in contracts:
        relative = contract.path.relative_to(DOCS).as_posix()
        if relative not in nav:
            raise ValueError(f"gallery is missing from navigation: {relative}")
    return tuple(contracts)


def main() -> None:
    galleries = {contract.path: contract for contract in gallery_contracts()}
    executed = 0
    getting_started_blocks = 0
    gallery_blocks: dict[Path, int] = {path: 0 for path in galleries}
    for path in sorted(DOCS.rglob("*.md")):
        text = path.read_text()
        if path in galleries:
            missing_headings = [
                heading for heading in REQUIRED_GALLERY_HEADINGS if heading not in text
            ]
            if missing_headings:
                raise ValueError(
                    f"gallery {path.relative_to(ROOT)} is missing headings: "
                    + ", ".join(missing_headings)
                )
        for index, match in enumerate(EXECUTABLE_BLOCK.finditer(text), start=1):
            source = match.group("source")
            code = compile(source, f"{path.relative_to(ROOT)}:example-{index}", "exec")
            namespace: dict[str, object] = {"__name__": "__holocron_docs_example__"}
            exec(code, namespace)  # noqa: S102
            executed += 1
            if path == GETTING_STARTED:
                getting_started_blocks += 1
                missing = sorted(GETTING_STARTED_OUTPUTS - namespace.keys())
                if missing:
                    raise ValueError(
                        "getting-started workflow outputs are incomplete: "
                        + ", ".join(missing)
                    )
            if path in galleries:
                gallery_blocks[path] += 1
                contract = galleries[path]
                missing = sorted(contract.required_outputs - namespace.keys())
                if missing:
                    raise ValueError(
                        f"gallery {contract.gallery_id} outputs are incomplete: "
                        + ", ".join(missing)
                    )
    if executed == 0:
        raise ValueError("documentation contains no executable Python examples")
    if getting_started_blocks != 1:
        raise ValueError("getting-started must contain one coherent executable block")
    incoherent = sorted(
        contract.gallery_id
        for path, contract in galleries.items()
        if gallery_blocks[path] != 1
    )
    if incoherent:
        raise ValueError(
            "each gallery must contain one coherent executable block: "
            + ", ".join(incoherent)
        )
    print(
        f"documentation examples verified: {executed} blocks; "
        f"complete getting-started workflow and {len(galleries)} galleries passed"
    )


if __name__ == "__main__":
    main()
