"""Validate the retained Phase 9 independent technical review decisions."""

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

ROOT = Path(__file__).resolve().parents[1]
REVIEW_SET = ROOT / "governance/phase-9-reviews/review-set.json"
SCHEMA = ROOT / "schemas/phase-9-review-set.schema.json"
DOMAINS = ("statistical", "numerical", "security", "api", "documentation")


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    """Validated identity and coverage of one Phase 9 review set."""

    reviewer: str
    reviewed_revision: str
    domains: tuple[str, ...]
    decision: str


def _strings(value: JsonValue, *, name: str) -> tuple[str, ...]:
    result: list[str] = []
    for index, item in enumerate(require_array(value, name=name)):
        if not isinstance(item, str):
            raise ValueError(f"{name}[{index}] must be a string")
        result.append(item)
    return tuple(result)


def _safe_file(value: str, *, name: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe {name} path: {value}")
    resolved = ROOT / path
    if not resolved.is_file():
        raise ValueError(f"missing {name}: {value}")
    return resolved


def evaluate_review_set(review_set: dict[str, JsonValue]) -> ReviewSummary:
    """Enforce exact domain coverage and durable record/evidence boundaries."""
    reviewer = require_object(review_set["reviewer"], name="reviewer")
    reviewer_name = cast(str, reviewer["display_name"])
    revision = cast(str, review_set["reviewed_revision"])
    review_values = require_array(review_set["reviews"], name="reviews")
    reviews = [
        require_object(value, name=f"reviews[{index}]")
        for index, value in enumerate(review_values)
    ]
    domains = tuple(cast(str, review["domain"]) for review in reviews)
    if domains != DOMAINS:
        raise ValueError("Phase 9 review domains differ or are out of order")

    for review in reviews:
        domain = cast(str, review["domain"])
        title_domain = "API" if domain == "api" else domain
        record = _safe_file(cast(str, review["record_path"]), name=f"{domain} record")
        document = record.read_text(encoding="utf-8")
        required_text = (
            f"# Phase 9 {title_domain} review decision",
            f"Reviewer: {reviewer_name}",
            "Independence: attested",
            f"Reviewed revision: `{revision}`",
            "Decision: approved",
            "Unresolved findings: none",
        )
        missing = [text for text in required_text if text not in document]
        if missing:
            raise ValueError(f"{domain} review record is missing: {', '.join(missing)}")
        for evidence in _strings(review["evidence"], name=f"{domain}.evidence"):
            _safe_file(evidence, name=f"{domain} evidence")
        if not _strings(review["exclusions"], name=f"{domain}.exclusions"):
            raise ValueError(f"{domain} review has no exclusions")

    return ReviewSummary(
        reviewer=reviewer_name,
        reviewed_revision=revision,
        domains=domains,
        decision=cast(str, review_set["decision"]),
    )


def check(path: Path = REVIEW_SET) -> ReviewSummary:
    value = load_json(path)
    validate_document(value, SCHEMA)
    return evaluate_review_set(require_object(value, name="Phase 9 review set"))


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--review-set", type=Path, default=REVIEW_SET)
    return command


def main() -> int:
    args = parser().parse_args()
    summary = check(args.review_set)
    print(
        "Phase 9 independent reviews verified: "
        f"reviewer={summary.reviewer}, revision={summary.reviewed_revision}, "
        f"domains={len(summary.domains)}, decision={summary.decision}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
