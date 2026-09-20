from __future__ import annotations

import copy
import unittest
from typing import cast

from reference.contracts import JsonValue, load_json, require_object, validate_document
from tools.check_phase_9_reviews import (
    DOMAINS,
    REVIEW_SET,
    SCHEMA,
    check,
    evaluate_review_set,
)


def _review_set() -> dict[str, JsonValue]:
    return require_object(load_json(REVIEW_SET), name="review set")


def _reviews(review_set: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    return cast(list[dict[str, JsonValue]], review_set["reviews"])


class PhaseNineReviewTests(unittest.TestCase):
    def test_committed_review_set_is_approved_and_complete(self) -> None:
        summary = check()

        self.assertEqual(summary.reviewer, "Ron Mexico")
        self.assertEqual(
            summary.reviewed_revision,
            "ae43ffeb5a08c7aac508563a3e48657c53c99eed",
        )
        self.assertEqual(summary.domains, DOMAINS)
        self.assertEqual(summary.decision, "approved")

    def test_review_set_schema_is_strict(self) -> None:
        review_set = _review_set()
        mutated = copy.deepcopy(review_set)
        mutated["approval_note"] = "unexpected"

        with self.assertRaisesRegex(ValueError, "Additional properties"):
            validate_document(mutated, SCHEMA)

    def test_all_five_domains_are_required_in_order(self) -> None:
        review_set = _review_set()
        reviews = _reviews(review_set)
        reviews[0], reviews[1] = reviews[1], reviews[0]

        with self.assertRaisesRegex(ValueError, "domains differ"):
            evaluate_review_set(review_set)

    def test_missing_domain_record_is_rejected(self) -> None:
        review_set = _review_set()
        _reviews(review_set)[0]["record_path"] = "governance/missing-review.md"

        with self.assertRaisesRegex(ValueError, "missing statistical record"):
            evaluate_review_set(review_set)

    def test_unsafe_evidence_path_is_rejected(self) -> None:
        review_set = _review_set()
        _reviews(review_set)[0]["evidence"] = ["../outside"]

        with self.assertRaisesRegex(ValueError, "unsafe statistical evidence"):
            evaluate_review_set(review_set)

    def test_unresolved_findings_cannot_be_approved_by_schema(self) -> None:
        review_set = _review_set()
        review_set["unresolved_findings"] = ["finding-1"]

        with self.assertRaises(ValueError):
            validate_document(review_set, SCHEMA)


if __name__ == "__main__":
    unittest.main()
