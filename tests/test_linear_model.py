from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast

import numpy as np

from holocron.design import RestrictedCubicSplineSpec
from holocron.exceptions import RankDeficiencyError
from holocron.models import fit_ols
from reference.contracts import (
    JsonValue,
    compare_json,
    output_payload,
    validate_case_pair,
)


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
        case, expected, policy = validate_case_pair(
            repository / "reference/cases/ols-rcs-explicit.json",
            repository / "reference/expected/ols-rcs-explicit.json",
        )
        x = cast(list[float], case["x"])
        y = cast(list[float], case["y"])
        knots = tuple(cast(list[float], case["knots"]))
        basis = RestrictedCubicSplineSpec(knots).transform(x)
        result = fit_ols(
            y,
            basis,
            feature_names=("x", "x'", "x''"),
        )
        actual: dict[str, JsonValue] = {
            "ok": True,
            "protocol_version": "1",
            "operation": "ols_rcs",
            "knots": cast(JsonValue, list(knots)),
            "coefficient_names": cast(JsonValue, list(result.coefficient_names)),
            "coefficients": {
                name: value
                for name, value in zip(
                    result.coefficient_names, result.coefficients, strict=True
                )
            },
            "covariance_names": cast(JsonValue, list(result.coefficient_names)),
            "covariance": cast(JsonValue, [list(row) for row in result.covariance]),
            "design_names": ["x", "x'", "x''"],
            "design": cast(JsonValue, basis.tolist()),
            "fitted": cast(JsonValue, list(result.fitted_values)),
            "residuals": cast(JsonValue, list(result.residuals)),
            "degrees_of_freedom": result.residual_degrees_of_freedom,
            "sigma": result.residual_scale,
        }
        compare_json(actual, output_payload(expected), policy).require_match()
