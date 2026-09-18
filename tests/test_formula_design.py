from __future__ import annotations

import unittest
from typing import cast

import numpy as np

from holocron.design import DesignSpec, RestrictedCubicSplineSpec
from holocron.exceptions import InputValidationError, UnsupportedFeatureError
from holocron.formula import (
    Formula,
    IdentityTerm,
    LinearSplineTerm,
    PolynomialTerm,
    RestrictedCubicSplineTerm,
    Variable,
)
from reference.contracts import (
    CASES,
    EXPECTED,
    FORMULA_SCHEMA,
    compare_json,
    load_json,
    output_payload,
    require_object,
    validate_case_pair,
    validate_document,
)
from reference.python_parity import build_python_output


class FormulaTests(unittest.TestCase):
    def test_parses_every_core_term_and_round_trips_canonical_expression(self) -> None:
        formula = Formula.parse(
            "outcome ~ 0 + age + asis(weight) + pol(score, 3) + "
            "lsp(marker, [-1, 2.5]) + rcs(time, [0, 1, 4, 9])"
        )

        self.assertEqual(formula.response, Variable("outcome"))
        self.assertFalse(formula.include_intercept)
        self.assertEqual(
            tuple(type(term) for term in formula.terms),
            (
                IdentityTerm,
                IdentityTerm,
                PolynomialTerm,
                LinearSplineTerm,
                RestrictedCubicSplineTerm,
            ),
        )
        self.assertEqual(Formula.parse(formula.expression), formula)
        self.assertEqual(Formula.from_json(formula.to_json()), formula)
        self.assertEqual(len(formula.fingerprint), 64)
        validate_document(formula.to_dict(), FORMULA_SCHEMA)

    def test_quoted_adversarial_names_are_data_not_syntax(self) -> None:
        formula = Formula.parse(
            "`response ~ value` ~ `x + system('bad')` + pol(`tick``name`, 2)"
        )

        self.assertEqual(formula.response, Variable("response ~ value"))
        self.assertEqual(
            formula.predictor_names,
            ("x + system('bad')", "tick`name"),
        )
        self.assertEqual(Formula.parse(formula.expression), formula)

    def test_rejects_code_and_unsupported_formula_operators(self) -> None:
        rejected = (
            "y ~ log(x)",
            "y ~ x * z",
            "y ~ x:z",
            "y ~ x - z",
            "y ~ __import__('os')",
            "y ~ pol(x, degree=2)",
            "y ~ rcs(x, [0, 1])",
            "y ~ lsp(x, [2, 1])",
            "y ~ pol(x, 2.5)",
            "y ~ x + x",
        )
        for expression in rejected:
            with (
                self.subTest(expression=expression),
                self.assertRaises((InputValidationError, UnsupportedFeatureError)),
            ):
                Formula.parse(expression)

    def test_rejects_malformed_and_resource_exhausting_formulas(self) -> None:
        rejected = (
            "",
            "x",
            "y ~",
            "y ~ x +",
            "y ~ 0",
            "y ~ 0 x",
            "y ~ `unterminated",
            "y ~ rcs(x, [0, nan, 2])",
            "y ~ pol(x, 11)",
            "y ~ " + " + ".join(f"x{index}" for index in range(65)),
            "y ~ " + "x" * 4097,
        )
        for expression in rejected:
            with (
                self.subTest(expression=expression),
                self.assertRaises((InputValidationError, UnsupportedFeatureError)),
            ):
                Formula.parse(expression)

        with self.assertRaises(InputValidationError):
            IdentityTerm(cast(Variable, "x"))
        with self.assertRaises(InputValidationError):
            Formula(response=None, terms=cast(tuple[IdentityTerm, ...], []))

    def test_document_validation_rejects_unknown_or_tampered_nodes(self) -> None:
        document = Formula.parse("y ~ pol(x, 2)").to_dict()
        cases: list[object] = []
        wrong_version = dict(document)
        wrong_version["schema_version"] = "other"
        cases.append(wrong_version)
        extra = dict(document)
        extra["extra"] = True
        cases.append(extra)
        unknown_term = Formula.parse("y ~ pol(x, 2)").to_dict()
        unknown_terms = cast(list[object], unknown_term["terms"])
        cast(dict[str, object], unknown_terms[0])["kind"] = "callback"
        cases.append(unknown_term)
        bad_degree = Formula.parse("y ~ pol(x, 2)").to_dict()
        bad_terms = cast(list[object], bad_degree["terms"])
        cast(dict[str, object], bad_terms[0])["degree"] = True
        cases.append(bad_degree)
        for candidate in cases:
            with (
                self.subTest(candidate=candidate),
                self.assertRaises(InputValidationError),
            ):
                Formula.from_dict(candidate)


class DesignSpecTests(unittest.TestCase):
    def test_core_transformations_and_metadata(self) -> None:
        specification = DesignSpec.from_formula(
            "y ~ x + pol(z, 3) + lsp(w, [0, 2]) + rcs(s, [-2, 0, 3, 6])"
        )
        data = {
            "x": (-1.0, 0.5, 3.0),
            "z": (2.0, -1.0, 0.5),
            "w": (-1.0, 1.0, 4.0),
            "s": (-3.0, 1.0, 7.0),
            "y": (5.0, 6.0, 7.0),
        }
        result = specification.transform(data)

        expected = np.column_stack(  # pyright: ignore[reportUnknownMemberType]
            (
                data["x"],
                data["z"],
                np.asarray(data["z"]) ** 2,
                np.asarray(data["z"]) ** 3,
                data["w"],
                np.maximum(np.asarray(data["w"]), 0.0),
                np.maximum(np.asarray(data["w"]) - 2.0, 0.0),
                RestrictedCubicSplineSpec((-2.0, 0.0, 3.0, 6.0)).transform(data["s"]),
            )
        )
        np.testing.assert_allclose(result.to_numpy(), expected)
        self.assertEqual(result.shape, (3, 10))
        self.assertEqual(result.term_slices, ((0, 1), (1, 4), (4, 7), (7, 10)))
        self.assertEqual(
            result.nonlinear_mask,
            (False, False, True, True, False, True, True, False, True, True),
        )
        self.assertEqual(specification.response_values(data), (5.0, 6.0, 7.0))
        copied = result.to_numpy()
        copied[0, 0] = 999.0
        self.assertEqual(result.rows[0][0], -1.0)

    def test_design_serialization_reconstructs_prediction_transform(self) -> None:
        specification = DesignSpec.from_formula(
            "~ 0 + pol(`blood pressure`, 2) + lsp(age, [30, 60])"
        )
        restored = DesignSpec.from_json(specification.to_json())
        new_data = {
            "blood pressure": (110.0, 140.0),
            "age": (25.0, 70.0),
        }

        self.assertEqual(restored, specification)
        self.assertEqual(restored.fingerprint, specification.fingerprint)
        self.assertEqual(
            restored.transform(new_data), specification.transform(new_data)
        )
        self.assertFalse(restored.formula.include_intercept)

    def test_rejects_invalid_design_data_and_tampered_metadata(self) -> None:
        specification = DesignSpec.from_formula("y ~ x + pol(z, 2)")
        invalid = (
            {"x": (1.0, 2.0)},
            {"x": (1.0, 2.0), "z": (1.0,)},
            {"x": (1.0, 2.0), "z": (1.0, None)},
            {"x": (1.0, 2.0), "z": (1.0, np.inf)},
            {"x": (1.0, 2.0), "z": (1.0, True)},
            {"x": (), "z": ()},
        )
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(InputValidationError):
                specification.transform(data)

        overflowing = DesignSpec.from_formula("~ pol(x, 10)")
        with self.assertRaises(InputValidationError):
            overflowing.transform({"x": (1e100, 2e100)})

        document = specification.to_dict()
        columns = document["columns"]
        assert isinstance(columns, list)
        assert isinstance(columns[0], dict)
        columns[0]["name"] = "tampered"
        with self.assertRaises(InputValidationError):
            DesignSpec.from_dict(document)

    def test_response_is_explicit_and_not_required_for_transform(self) -> None:
        one_sided = DesignSpec.from_formula("~ x")
        self.assertEqual(one_sided.transform({"x": (1.0, 2.0)}).shape, (2, 1))
        with self.assertRaises(InputValidationError):
            one_sided.response_values({"x": (1.0, 2.0)})

        two_sided = DesignSpec.from_formula("y ~ x")
        two_sided.transform({"x": (1.0, 2.0)})
        with self.assertRaises(InputValidationError):
            two_sided.response_values({"x": (1.0, 2.0)})

    def test_matches_all_rms_core_design_fixtures(self) -> None:
        case_paths = [
            path
            for path in sorted(CASES.glob("*.json"))
            if require_object(load_json(path), name=str(path)).get("operation")
            == "design"
        ]
        self.assertEqual(len(case_paths), 4)
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
