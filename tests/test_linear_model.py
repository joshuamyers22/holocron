from __future__ import annotations

import unittest
from typing import cast

import numpy as np

from holocron.design import DesignSpec
from holocron.exceptions import InputValidationError, RankDeficiencyError
from holocron.models import OlsResult, fit_ols
from reference.contracts import (
    CASES,
    EXPECTED,
    OLS_RESULT_SCHEMA,
    compare_json,
    load_json,
    output_payload,
    require_object,
    validate_case_pair,
    validate_document,
)
from reference.python_parity import build_python_output


class OlsTests(unittest.TestCase):
    def test_rejects_rank_deficient_design(self) -> None:
        with self.assertRaisesRegex(RankDeficiencyError, "full column rank"):
            fit_ols(
                (1.0, 2.0, 3.0, 4.0),
                ((1.0, 2.0), (2.0, 4.0), (3.0, 6.0), (4.0, 8.0)),
            )

    def test_predicts_new_rows(self) -> None:
        result = fit_ols(
            (1.0, 3.0, 5.0, 7.0),
            ((0.0,), (1.0,), (2.0,), (3.0,)),
            feature_names=("x",),
        )
        np.testing.assert_allclose(result.coefficients, (1.0, 2.0), atol=1e-14)
        np.testing.assert_allclose(result.predict(((4.0,), (5.0,))), (9.0, 11.0))

    def test_result_serialization_preserves_design_identity(self) -> None:
        specification = DesignSpec.from_formula("y ~ pol(x, 2)")
        design = specification.transform({"x": (-2.0, -1.0, 0.0, 1.0, 2.0)})
        result = fit_ols((5.0, 2.0, 1.0, 2.0, 5.0), design)
        restored = OlsResult.from_json(result.to_json())

        self.assertEqual(restored, result)
        self.assertEqual(restored.design_fingerprint, specification.fingerprint)
        self.assertEqual(len(restored.fingerprint), 64)
        self.assertEqual(restored.predict(design), result.fitted_values)
        validate_document(result.to_dict(), OLS_RESULT_SCHEMA)

        other = DesignSpec.from_formula("~ x + pol(z, 2)").transform(
            {"x": (1.0,), "z": (2.0,)}
        )
        with self.assertRaisesRegex(InputValidationError, "fingerprint"):
            restored.predict(other)

    def test_design_matrix_controls_intercept_policy(self) -> None:
        specification = DesignSpec.from_formula("y ~ 0 + x")
        design = specification.transform({"x": (1.0, 2.0, 3.0, 4.0)})
        result = fit_ols((2.0, 4.0, 6.0, 8.0), design)

        self.assertFalse(result.includes_intercept)
        self.assertEqual(result.coefficient_names, ("asis(x)",))
        with self.assertRaisesRegex(InputValidationError, "include_intercept"):
            fit_ols((2.0, 4.0, 6.0, 8.0), design, include_intercept=True)

    def test_result_reader_rejects_unknown_fields_and_inconsistent_shapes(self) -> None:
        result = fit_ols(
            (1.0, 3.0, 5.0, 7.0),
            ((0.0,), (1.0,), (2.0,), (3.0,)),
        )
        document = result.to_dict()
        document["future_field"] = True
        with self.assertRaises(InputValidationError):
            OlsResult.from_dict(document)

        inconsistent = result.to_dict()
        coefficients = cast(list[object], inconsistent["coefficients"])
        coefficients.pop()
        with self.assertRaises(InputValidationError):
            OlsResult.from_dict(inconsistent)

        with self.assertRaises(InputValidationError):
            OlsResult.from_json('{"schema_version":NaN}')

    def test_matches_all_rms_ols_rcs_oracle_fixtures(self) -> None:
        case_paths = [
            path
            for path in sorted(CASES.glob("*.json"))
            if require_object(load_json(path), name=str(path)).get("operation")
            == "ols_rcs"
        ]
        self.assertEqual(len(case_paths), 6)
        for case_path in case_paths:
            raw_case = require_object(load_json(case_path), name=str(case_path))
            with self.subTest(case_id=raw_case["case_id"]):
                case, expected, policy = validate_case_pair(
                    case_path, EXPECTED / str(raw_case["expected_output"])
                )
                actual = build_python_output(case)
                compare_json(actual, output_payload(expected), policy).require_match()
