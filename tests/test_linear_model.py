from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import cast

import numpy as np

from holocron.design import RestrictedCubicSplineSpec
from holocron.exceptions import RankDeficiencyError
from holocron.models import fit_ols


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

    def test_matches_rms_ols_rcs_oracle_fixture(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        case_object: object = json.loads(
            (repository / "reference/cases/ols-rcs-explicit.json").read_text()
        )
        expected_object: object = json.loads(
            (repository / "reference/expected/ols-rcs-explicit.json").read_text()
        )
        case = cast(dict[str, object], case_object)
        expected = cast(dict[str, object], expected_object)
        x = cast(list[float], case["x"])
        y = cast(list[float], case["y"])
        knots = tuple(cast(list[float], case["knots"]))
        basis = RestrictedCubicSplineSpec(knots).transform(x)
        result = fit_ols(
            y,
            basis,
            feature_names=("x", "x'", "x''"),
        )

        expected_coefficients = cast(dict[str, float], expected["coefficients"])
        coefficient_values = tuple(
            expected_coefficients[name] for name in result.coefficient_names
        )
        np.testing.assert_allclose(
            result.coefficients, coefficient_values, rtol=1e-13, atol=1e-14
        )
        np.testing.assert_allclose(
            result.covariance,
            cast(list[list[float]], expected["covariance"]),
            rtol=1e-13,
            atol=1e-14,
        )
        np.testing.assert_allclose(
            result.fitted_values,
            cast(list[float], expected["fitted"]),
            rtol=1e-13,
            atol=1e-14,
        )
        np.testing.assert_allclose(
            result.residuals,
            cast(list[float], expected["residuals"]),
            rtol=1e-13,
            atol=1e-14,
        )
        self.assertEqual(
            result.residual_degrees_of_freedom,
            cast(int, expected["degrees_of_freedom"]),
        )
        self.assertAlmostEqual(
            result.residual_scale, cast(float, expected["sigma"]), places=14
        )
