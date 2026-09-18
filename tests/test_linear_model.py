from __future__ import annotations

import unittest

import numpy as np

from holocron.exceptions import RankDeficiencyError
from holocron.models import fit_ols
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
