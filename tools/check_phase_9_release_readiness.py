"""Validate the completed Phase 9 release-readiness assessment."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from reference.contracts import (
    JsonValue,
    load_json,
    require_array,
    require_object,
    validate_document,
)
from tools.check_phase_9_reviews import check as check_reviews

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "governance/phase-9-release-readiness.json"
SCHEMA = ROOT / "schemas/phase-9-release-readiness.schema.json"
CHECKLIST = ROOT / "checklists/RELEASE_READINESS.md"

CONTROL_IDS = (
    "critical-journeys",
    "dependency-integrity",
    "stable-release-scope",
    "candidate-beta",
    "independent-reviews",
    "version-tag-identity",
    "artifact-matrix",
    "artifact-sbom-provenance",
    "secrets-private-data",
    "project-memory",
    "tracked-work",
    "threat-migration-compatibility",
    "operational-observability",
    "performance-capacity",
    "remaining-risks",
    "agent-assisted-work",
    "telemetry-events",
    "telemetry-systems",
    "support-policy",
    "response-procedures",
)


@dataclass(frozen=True, slots=True)
class ReadinessSummary:
    """Semantic result of one fully dispositioned readiness checklist."""

    status: str
    passed: int
    blocked: int
    not_applicable: int
    blockers: tuple[str, ...]
    release_ready: bool


def _items(assessment: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    return [
        require_object(item, name=f"items[{index}]")
        for index, item in enumerate(require_array(assessment["items"], name="items"))
    ]


def _strings(value: JsonValue, *, name: str) -> tuple[str, ...]:
    result: list[str] = []
    for index, item in enumerate(require_array(value, name=name)):
        if not isinstance(item, str):
            raise ValueError(f"{name}[{index}] must be a string")
        result.append(item)
    return tuple(result)


def evaluate_assessment(assessment: dict[str, JsonValue]) -> ReadinessSummary:
    """Enforce status, evidence, applicability, and summary invariants."""
    items = _items(assessment)
    control_ids = tuple(cast(str, item["control_id"]) for item in items)
    if control_ids != CONTROL_IDS:
        raise ValueError("release-readiness controls differ or are out of order")

    counts = {"passed": 0, "blocked": 0, "not-applicable": 0}
    blockers: list[str] = []
    for item in items:
        control_id = cast(str, item["control_id"])
        disposition = cast(str, item["disposition"])
        applicable = cast(bool, item["applicable"])
        resolution = item["resolution_condition"]
        counts[disposition] += 1
        if disposition == "passed":
            if not applicable or resolution is not None:
                raise ValueError(f"passed control has inconsistent state: {control_id}")
        elif disposition == "blocked":
            blockers.append(control_id)
            if not applicable or not isinstance(resolution, str) or not resolution:
                raise ValueError(f"blocked control lacks a resolution: {control_id}")
        elif applicable or resolution is not None:
            raise ValueError(
                f"not-applicable control has inconsistent state: {control_id}"
            )
        for evidence in _strings(item["evidence"], name=f"{control_id}.evidence"):
            path = Path(evidence)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe evidence path for {control_id}: {evidence}")
            if not (ROOT / path).is_file():
                raise ValueError(f"missing evidence for {control_id}: {evidence}")

    summary = require_object(assessment["summary"], name="summary")
    expected_summary = {
        "total": len(items),
        "passed": counts["passed"],
        "blocked": counts["blocked"],
        "not_applicable": counts["not-applicable"],
    }
    for name, expected in expected_summary.items():
        if summary[name] != expected:
            raise ValueError(f"readiness summary {name} differs from checklist")
    recorded_blockers = _strings(
        summary["blocking_control_ids"], name="blocking_control_ids"
    )
    if recorded_blockers != tuple(blockers):
        raise ValueError("readiness blocker summary differs from checklist")

    ready = not blockers
    expected_status = "ready" if ready else "blocked"
    if assessment["release_ready"] is not ready:
        raise ValueError("release_ready differs from checklist dispositions")
    if assessment["assessment_status"] != expected_status:
        raise ValueError("assessment status differs from checklist dispositions")
    return ReadinessSummary(
        status=expected_status,
        passed=counts["passed"],
        blocked=counts["blocked"],
        not_applicable=counts["not-applicable"],
        blockers=tuple(blockers),
        release_ready=ready,
    )


def check_checklist_document(path: Path = CHECKLIST) -> None:
    """Require the human checklist to cover every structured control once."""
    document = path.read_text(encoding="utf-8")
    markers = tuple(
        line.removeprefix("<!-- readiness:").removesuffix(" -->")
        for line in document.splitlines()
        if line.startswith("<!-- readiness:") and line.endswith(" -->")
    )
    if len(markers) != len(set(markers)) or set(markers) != set(CONTROL_IDS):
        raise ValueError("human release-readiness checklist differs from assessment")


def check(path: Path = ASSESSMENT) -> ReadinessSummary:
    check_reviews()
    value = load_json(path)
    validate_document(value, SCHEMA)
    assessment = require_object(value, name="release-readiness assessment")
    result = evaluate_assessment(assessment)
    check_checklist_document()
    return result


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--assessment", type=Path, default=ASSESSMENT)
    command.add_argument("--require-ready", action="store_true")
    return command


def main() -> int:
    args = parser().parse_args()
    summary = check(args.assessment)
    print(
        "Phase 9 release-readiness checklist verified: "
        f"status={summary.status}, passed={summary.passed}, "
        f"blocked={summary.blocked}, not_applicable={summary.not_applicable}"
    )
    if args.require_ready and not summary.release_ready:
        for blocker in summary.blockers:
            print(f"- {blocker}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
