from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from reference.contracts import (
    CASE_SCHEMA,
    ROOT,
    ContractValidationError,
    JsonValue,
    build_evidence,
    compare_json,
    load_json,
    output_payload,
    validate_case_pair,
    validate_document,
    validate_repository_contracts,
    write_evidence,
)


class ParityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_path = ROOT / "reference/cases/ols-rcs-explicit.json"
        self.expected_path = ROOT / "reference/expected/ols-rcs-explicit.json"
        self.case, self.expected, self.policy = validate_case_pair(
            self.case_path, self.expected_path
        )
        self.payload = output_payload(self.expected)

    def test_all_schemas_policies_and_fixtures_are_valid(self) -> None:
        self.assertEqual(validate_repository_contracts(), 3)

    def test_policy_applies_field_specific_numeric_tolerances(self) -> None:
        actual = copy.deepcopy(self.payload)
        coefficients = cast(dict[str, JsonValue], actual["coefficients"])
        covariance = cast(list[JsonValue], actual["covariance"])
        covariance_row = cast(list[JsonValue], covariance[3])
        coefficients["Intercept"] = cast(float, coefficients["Intercept"]) + 5e-7
        covariance_row[3] = cast(float, covariance_row[3]) + 5e-7

        report = compare_json(actual, self.payload, self.policy)

        self.assertFalse(report.passed)
        self.assertEqual(len(report.mismatches), 1)
        self.assertIn("/coefficients/Intercept", report.mismatches[0])

    def test_unlisted_metadata_fields_are_exact(self) -> None:
        actual = copy.deepcopy(self.payload)
        names = cast(list[JsonValue], actual["coefficient_names"])
        names[0] = "intercept"

        report = compare_json(actual, self.payload, self.policy)

        self.assertFalse(report.passed)
        self.assertIn("(exact)", report.mismatches[0])

    def test_case_schema_rejects_undeclared_fields(self) -> None:
        invalid_case = copy.deepcopy(self.case)
        invalid_case["r_expression"] = "system('not allowed')"

        with self.assertRaises(ContractValidationError):
            validate_document(invalid_case, CASE_SCHEMA)

    def test_unlisted_numeric_fields_do_not_inherit_a_global_tolerance(self) -> None:
        actual = copy.deepcopy(self.payload)
        knots = cast(list[JsonValue], actual["knots"])
        knots[0] = cast(float, knots[0]) + 1e-14

        report = compare_json(actual, self.payload, self.policy)

        self.assertFalse(report.passed)
        self.assertIn("/knots/0", report.mismatches[0])

    def test_evidence_is_schema_valid_and_written_atomically(self) -> None:
        report = compare_json(self.payload, self.payload, self.policy)
        evidence = build_evidence(
            case_path=self.case_path,
            expected_path=self.expected_path,
            case=self.case,
            expected=self.expected,
            actual=self.payload,
            report=report,
            code_revision="a" * 40,
            source_is_dirty=False,
            evaluated_at=datetime(2026, 9, 17, 20, 0, tzinfo=UTC),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested/evidence.json"
            digest = write_evidence(path, evidence)
            written = load_json(path)

        self.assertEqual(len(digest), 64)
        self.assertEqual(written, evidence)
        validate_document(evidence, ROOT / "schemas/parity-evidence.schema.json")

    def test_evidence_rejects_naive_timestamps(self) -> None:
        report = compare_json(self.payload, self.payload, self.policy)

        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_evidence(
                case_path=self.case_path,
                expected_path=self.expected_path,
                case=self.case,
                expected=self.expected,
                actual=self.payload,
                report=report,
                code_revision="a" * 40,
                source_is_dirty=False,
                evaluated_at=datetime(2026, 9, 17, 20, 0),
            )


if __name__ == "__main__":
    unittest.main()
