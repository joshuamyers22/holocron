from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast

import numpy as np

from holocron.design import RestrictedCubicSplineSpec
from holocron.exceptions import InputValidationError
from reference.contracts import (
    JsonValue,
    compare_json,
    output_payload,
    validate_case_pair,
)


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

    def test_matches_rms_oracle_fixture(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        case, expected, policy = validate_case_pair(
            repository / "reference/cases/rcs-explicit.json",
            repository / "reference/expected/rcs-explicit.json",
        )
        knots = tuple(cast(list[float], case["knots"]))
        spec = RestrictedCubicSplineSpec(knots)
        x = cast(list[float], case["x"])
        basis = spec.transform(x)
        actual: dict[str, JsonValue] = {
            "ok": True,
            "protocol_version": "1",
            "operation": "rcs",
            "x": cast(JsonValue, x),
            "knots": cast(JsonValue, list(spec.knots)),
            "nonlinear_mask": cast(JsonValue, list(spec.nonlinear_mask)),
            "nonlinear_columns": cast(JsonValue, list(spec.nonlinear_columns)),
            "column_names": ["x", "x'", "x''"],
            "basis": cast(JsonValue, basis.tolist()),
        }
        compare_json(actual, output_payload(expected), policy).require_match()


if __name__ == "__main__":
    unittest.main()
