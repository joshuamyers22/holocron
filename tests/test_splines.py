from __future__ import annotations

import unittest

import numpy as np

from holocron.design import RestrictedCubicSplineSpec
from holocron.exceptions import InputValidationError
from reference.contracts import (
    CASES,
    EXPECTED,
    compare_json,
    load_json,
    output_payload,
    require_object,
    validate_case_pair,
)
from reference.python_parity import build_python_output


class RestrictedCubicSplineSpecTests(unittest.TestCase):
    def test_rejects_invalid_knots(self) -> None:
        for knots in ((0.0, 1.0), (0.0, 1.0, 1.0), (0.0, np.nan, 2.0)):
            with self.subTest(knots=knots), self.assertRaises(InputValidationError):
                RestrictedCubicSplineSpec(knots)

    def test_rejects_nonfinite_values(self) -> None:
        spec = RestrictedCubicSplineSpec((-2.0, 0.0, 3.0, 6.0))
        with self.assertRaises(InputValidationError):
            spec.transform((0.0, np.inf))

    def test_linear_tails_have_constant_slope(self) -> None:
        spec = RestrictedCubicSplineSpec((-2.0, 0.0, 3.0, 6.0))
        x = np.asarray((-4.0, -3.0, -2.0, 6.0, 7.0, 8.0))
        basis = spec.transform(x)
        left_first = basis[1] - basis[0]
        left_second = basis[2] - basis[1]
        right_first = basis[-2] - basis[-3]
        right_second = basis[-1] - basis[-2]
        np.testing.assert_allclose(left_first, left_second)
        np.testing.assert_allclose(right_first, right_second)

    def test_metadata_identifies_nonlinear_columns(self) -> None:
        spec = RestrictedCubicSplineSpec((-2.0, 0.0, 3.0, 6.0))
        self.assertEqual(spec.n_columns, 3)
        self.assertEqual(spec.nonlinear_columns, (1, 2))
        self.assertEqual(spec.nonlinear_mask, (False, True, True))

    def test_transform_has_expected_shape_and_linear_column(self) -> None:
        values = (-3.0, 0.0, 7.0)
        spec = RestrictedCubicSplineSpec((-2.0, 0.0, 3.0, 6.0))
        basis = spec.transform(values)
        self.assertEqual(basis.shape, (3, 3))
        np.testing.assert_array_equal(basis[:, 0], values)

    def test_matches_all_rms_oracle_fixtures(self) -> None:
        case_paths = [
            path
            for path in sorted(CASES.glob("*.json"))
            if require_object(load_json(path), name=str(path)).get("operation") == "rcs"
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


if __name__ == "__main__":
    unittest.main()
