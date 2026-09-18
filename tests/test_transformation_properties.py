from __future__ import annotations

import math
import random
import unittest
from collections.abc import Iterable
from typing import TypeAlias, cast

import numpy as np

from holocron.design import DesignSpec, RestrictedCubicSplineSpec
from holocron.exceptions import InputValidationError
from holocron.formula import (
    CategoricalTerm,
    Formula,
    IdentityTerm,
    LinearSplineTerm,
    OrderedTerm,
    PolynomialTerm,
    RestrictedCubicSplineTerm,
    RestrictedInteractionTerm,
    Variable,
)

MainTerm: TypeAlias = (
    IdentityTerm
    | PolynomialTerm
    | LinearSplineTerm
    | RestrictedCubicSplineTerm
    | CategoricalTerm
    | OrderedTerm
)

KINDS = (
    "identity",
    "polynomial",
    "linear_spline",
    "restricted_cubic_spline",
    "categorical",
    "ordered",
)
MAIN_TRIALS_PER_KIND = 64
RCS_TAIL_TRIALS = 64
SEED = 20_260_918
TRANSFORM_ABSOLUTE_TOLERANCE = 1e-12
TRANSFORM_RELATIVE_TOLERANCE = 1e-12


def _numbers(values: Iterable[object]) -> tuple[float, ...]:
    return tuple(float(cast(int | float, value)) for value in values)


def _positive_cube(value: float) -> float:
    return max(value, 0.0) ** 3


def _reference_rcs_row(value: float, knots: tuple[float, ...]) -> tuple[float, ...]:
    lower = knots[0]
    penultimate = knots[-2]
    upper = knots[-1]
    boundary_scale = (upper - lower) ** 2
    final_span = upper - penultimate
    nonlinear: list[float] = []
    for knot in knots[:-2]:
        upper_weight = (penultimate - knot) / final_span
        penultimate_weight = (upper - knot) / final_span
        nonlinear.append(
            (
                _positive_cube(value - knot)
                - penultimate_weight * _positive_cube(value - penultimate)
                + upper_weight * _positive_cube(value - upper)
            )
            / boundary_scale
        )
    return (value, *nonlinear)


def _reference_main(
    term: MainTerm, values: tuple[object, ...]
) -> tuple[tuple[float, ...], ...]:
    if isinstance(term, IdentityTerm):
        return tuple((value,) for value in _numbers(values))
    if isinstance(term, PolynomialTerm):
        return tuple(
            tuple(value**power for power in range(1, term.degree + 1))
            for value in _numbers(values)
        )
    if isinstance(term, LinearSplineTerm):
        return tuple(
            (value, *(max(value - knot, 0.0) for knot in term.knots))
            for value in _numbers(values)
        )
    if isinstance(term, RestrictedCubicSplineTerm):
        return tuple(
            _reference_rcs_row(value, term.knots) for value in _numbers(values)
        )
    if isinstance(term, CategoricalTerm):
        return tuple(
            tuple(float(value == level) for level in term.levels[1:])
            for value in values
        )
    return tuple(
        (
            value,
            *(float(value == level) for level in term.levels[2:]),
        )
        for value in _numbers(values)
    )


def _nonlinear_mask(term: MainTerm) -> tuple[bool, ...]:
    if isinstance(term, IdentityTerm):
        return (False,)
    if isinstance(term, CategoricalTerm):
        return (False,) * (len(term.levels) - 1)
    if isinstance(term, PolynomialTerm):
        width = term.degree
    elif isinstance(term, LinearSplineTerm):
        width = len(term.knots) + 1
    elif isinstance(term, RestrictedCubicSplineTerm):
        width = len(term.knots) - 1
    else:
        width = len(term.levels) - 1
    return (False, *(True for _ in range(width - 1)))


def _reference_interaction(
    left: MainTerm,
    right: MainTerm,
    left_values: tuple[object, ...],
    right_values: tuple[object, ...],
) -> tuple[tuple[float, ...], ...]:
    left_rows = _reference_main(left, left_values)
    right_rows = _reference_main(right, right_values)
    left_flags = _nonlinear_mask(left)
    right_flags = _nonlinear_mask(right)
    return tuple(
        tuple(
            left_value * right_value
            for left_value, left_nonlinear in zip(left_row, left_flags, strict=True)
            for right_value, right_nonlinear in zip(right_row, right_flags, strict=True)
            if not (left_nonlinear and right_nonlinear)
        )
        for left_row, right_row in zip(left_rows, right_rows, strict=True)
    )


def _knots(rng: random.Random, count: int) -> tuple[float, ...]:
    values = sorted(rng.sample(range(-120, 121), count))
    return tuple(value / 7.0 for value in values)


def _random_term_and_values(
    kind: str,
    variable_name: str,
    trial: int,
    rng: random.Random,
    *,
    row_count: int = 23,
) -> tuple[MainTerm, tuple[object, ...]]:
    variable = Variable(variable_name)
    if kind == "identity":
        term: MainTerm = IdentityTerm(variable)
        values: tuple[object, ...] = tuple(
            rng.uniform(-20.0, 20.0) for _ in range(row_count)
        )
    elif kind == "polynomial":
        term = PolynomialTerm(variable, 2 + trial % 9)
        values = tuple(rng.uniform(-2.5, 2.5) for _ in range(row_count))
    elif kind == "linear_spline":
        knots = _knots(rng, 1 + trial % 32)
        term = LinearSplineTerm(variable, knots)
        values = tuple(
            (
                *knots,
                *(
                    rng.uniform(knots[0] - 4.0, knots[-1] + 4.0)
                    for _ in range(row_count - len(knots))
                ),
            )
        )
    elif kind == "restricted_cubic_spline":
        knots = _knots(rng, 3 + trial % 30)
        term = RestrictedCubicSplineTerm(variable, knots)
        values = tuple(
            (
                *knots,
                *(
                    rng.uniform(knots[0] - 4.0, knots[-1] + 4.0)
                    for _ in range(row_count - len(knots))
                ),
            )
        )
    elif kind == "categorical":
        levels = tuple(f"level {index}" for index in range(2 + trial % 63))
        term = CategoricalTerm(variable, levels)
        values = tuple(
            (
                *levels,
                *(rng.choice(levels) for _ in range(max(0, row_count - len(levels)))),
            )
        )
    else:
        levels = tuple(float(index * index + 1) for index in range(3 + trial % 62))
        term = OrderedTerm(variable, levels)
        values = tuple(
            (
                *levels,
                *(rng.choice(levels) for _ in range(max(0, row_count - len(levels)))),
            )
        )
    return term, values


def _example_term_and_values(
    kind: str, variable_name: str
) -> tuple[MainTerm, tuple[object, ...]]:
    variable = Variable(variable_name)
    numeric = (-3.0, -1.5, -0.25, 0.0, 0.75, 1.5, 2.5, 4.0, 6.0)
    if kind == "identity":
        return IdentityTerm(variable), numeric
    if kind == "polynomial":
        return PolynomialTerm(variable, 4), numeric
    if kind == "linear_spline":
        return LinearSplineTerm(variable, (-1.5, 0.0, 2.5)), numeric
    if kind == "restricted_cubic_spline":
        return RestrictedCubicSplineTerm(variable, (-2.0, 0.0, 3.0, 6.0)), numeric
    if kind == "categorical":
        levels = ("base", "A", "B", "C")
        return CategoricalTerm(variable, levels), (
            "base",
            "A",
            "B",
            "C",
            "A",
            "base",
            "C",
            "B",
            "A",
        )
    levels = (1.0, 2.0, 4.0, 8.0, 16.0)
    return OrderedTerm(variable, levels), (1.0, 2.0, 4.0, 8.0, 16.0, 4.0, 1.0, 8.0, 2.0)


class TransformationDifferentialTests(unittest.TestCase):
    def test_every_main_effect_matches_independent_scalar_reference(self) -> None:
        rng = random.Random(SEED)
        for kind in KINDS:
            for trial in range(MAIN_TRIALS_PER_KIND):
                with self.subTest(kind=kind, trial=trial):
                    term, values = _random_term_and_values(
                        kind, f"{kind}_value", trial, rng
                    )
                    formula = Formula(response=None, terms=(term,))
                    specification = DesignSpec.from_formula(formula)
                    actual = specification.transform({term.variable.name: iter(values)})
                    expected = _reference_main(term, values)
                    expected_width = len(expected[0])

                    np.testing.assert_allclose(
                        actual.to_numpy(),
                        np.asarray(expected, dtype=float),
                        rtol=TRANSFORM_RELATIVE_TOLERANCE,
                        atol=TRANSFORM_ABSOLUTE_TOLERANCE,
                    )
                    self.assertEqual(actual.shape, (len(values), expected_width))
                    self.assertEqual(term.n_columns, expected_width)
                    self.assertEqual(actual.term_slices, ((0, expected_width),))
                    self.assertEqual(actual.nonlinear_mask, _nonlinear_mask(term))
                    self.assertEqual(Formula.parse(formula.expression), formula)
                    restored = DesignSpec.from_json(specification.to_json())
                    self.assertEqual(
                        restored.transform({term.variable.name: values}), actual
                    )

    def test_all_ordered_interaction_kind_pairs_match_product_reference(self) -> None:
        for left_kind in KINDS:
            for right_kind in KINDS:
                with self.subTest(left=left_kind, right=right_kind):
                    left, left_values = _example_term_and_values(left_kind, "left")
                    right, right_values = _example_term_and_values(right_kind, "right")
                    interaction = RestrictedInteractionTerm(left, right)
                    formula = Formula(
                        response=None,
                        terms=(left, right, interaction),
                        include_intercept=False,
                    )
                    specification = DesignSpec.from_formula(formula)
                    actual = specification.transform(
                        {"left": left_values, "right": right_values}
                    )
                    left_expected = _reference_main(left, left_values)
                    right_expected = _reference_main(right, right_values)
                    interaction_expected = _reference_interaction(
                        left, right, left_values, right_values
                    )
                    expected = tuple(
                        (*left_row, *right_row, *interaction_row)
                        for left_row, right_row, interaction_row in zip(
                            left_expected,
                            right_expected,
                            interaction_expected,
                            strict=True,
                        )
                    )

                    np.testing.assert_allclose(
                        actual.to_numpy(),
                        np.asarray(expected),
                        rtol=TRANSFORM_RELATIVE_TOLERANCE,
                        atol=TRANSFORM_ABSOLUTE_TOLERANCE,
                    )
                    left_width = len(left_expected[0])
                    right_width = len(right_expected[0])
                    interaction_width = len(interaction_expected[0])
                    self.assertEqual(left.n_columns, left_width)
                    self.assertEqual(right.n_columns, right_width)
                    self.assertEqual(interaction.n_columns, interaction_width)
                    left_stop = left_width
                    right_stop = left_stop + right_width
                    self.assertEqual(
                        actual.term_slices,
                        (
                            (0, left_stop),
                            (left_stop, right_stop),
                            (right_stop, right_stop + interaction_width),
                        ),
                    )
                    expected_interaction_mask = tuple(
                        left_flag or right_flag
                        for left_flag in _nonlinear_mask(left)
                        for right_flag in _nonlinear_mask(right)
                        if not (left_flag and right_flag)
                    )
                    self.assertEqual(
                        actual.nonlinear_mask,
                        (
                            *_nonlinear_mask(left),
                            *_nonlinear_mask(right),
                            *expected_interaction_mask,
                        ),
                    )
                    self.assertFalse(actual.include_intercept)
                    self.assertEqual(
                        DesignSpec.from_json(specification.to_json()), specification
                    )


class TransformationPropertyTests(unittest.TestCase):
    def test_transform_is_row_permutation_and_batch_equivariant(self) -> None:
        specification = DesignSpec.from_formula(
            "~ 0 + x + pol(p, 5) + lsp(l, [-2, 0, 3]) + "
            "rcs(s, [-3, -1, 2, 5, 8]) + "
            'catg(g, ["base", "A", "B", "C"]) + '
            "scored(o, [1, 2, 4, 8, 16])"
        )
        row_count = 41
        rng = random.Random(SEED + 1)
        data: dict[str, tuple[object, ...]] = {
            "x": tuple(rng.uniform(-10.0, 10.0) for _ in range(row_count)),
            "p": tuple(rng.uniform(-2.0, 2.0) for _ in range(row_count)),
            "l": tuple(rng.uniform(-5.0, 6.0) for _ in range(row_count)),
            "s": tuple(rng.uniform(-6.0, 11.0) for _ in range(row_count)),
            "g": tuple(rng.choice(("base", "A", "B", "C")) for _ in range(row_count)),
            "o": tuple(rng.choice((1, 2, 4, 8, 16)) for _ in range(row_count)),
        }
        complete = specification.transform(data)
        order = list(range(row_count))
        rng.shuffle(order)
        permuted = specification.transform(
            {
                name: tuple(values[index] for index in order)
                for name, values in data.items()
            }
        )
        np.testing.assert_array_equal(
            permuted.to_numpy(), complete.to_numpy()[order, :]
        )

        cut = 17
        first = specification.transform(
            {name: values[:cut] for name, values in data.items()}
        )
        second = specification.transform(
            {name: values[cut:] for name, values in data.items()}
        )
        np.testing.assert_array_equal(
            np.asarray((*first.rows, *second.rows), dtype=float), complete.to_numpy()
        )
        self.assertEqual(first.column_names, second.column_names)
        self.assertEqual(first.nonlinear_mask, second.nonlinear_mask)
        self.assertEqual(first.term_slices, second.term_slices)
        self.assertEqual(
            first.specification_fingerprint, second.specification_fingerprint
        )

    def test_random_rcs_bases_have_linear_tails_and_scalar_equivalence(self) -> None:
        rng = random.Random(SEED + 2)
        for trial in range(RCS_TAIL_TRIALS):
            with self.subTest(trial=trial):
                knots = _knots(rng, 3 + trial % 8)
                spacing = max(knots[-1] - knots[0], 1.0)
                values = (
                    knots[0] - 3.0 * spacing,
                    knots[0] - 2.0 * spacing,
                    knots[0] - spacing,
                    *knots,
                    knots[-1] + spacing,
                    knots[-1] + 2.0 * spacing,
                    knots[-1] + 3.0 * spacing,
                )
                actual = RestrictedCubicSplineSpec(knots).transform(values)
                expected = np.asarray(
                    tuple(_reference_rcs_row(value, knots) for value in values)
                )
                np.testing.assert_allclose(
                    actual,
                    expected,
                    rtol=TRANSFORM_RELATIVE_TOLERANCE,
                    atol=TRANSFORM_ABSOLUTE_TOLERANCE,
                )
                np.testing.assert_allclose(actual[:3, 1:], 0.0, atol=1e-14)
                right = actual[-3:, :]
                np.testing.assert_allclose(
                    right[2] - 2.0 * right[1] + right[0],
                    0.0,
                    rtol=2e-12,
                    atol=2e-10,
                )

    def test_numeric_terms_fail_closed_for_nonfinite_and_boolean_values(self) -> None:
        terms: tuple[MainTerm, ...] = (
            IdentityTerm(Variable("x")),
            PolynomialTerm(Variable("x"), 3),
            LinearSplineTerm(Variable("x"), (0.0,)),
            RestrictedCubicSplineTerm(Variable("x"), (-1.0, 0.0, 1.0)),
        )
        for term in terms:
            specification = DesignSpec.from_formula(
                Formula(response=None, terms=(term,))
            )
            for invalid in (True, math.nan, math.inf, -math.inf):
                with (
                    self.subTest(kind=term.kind, invalid=invalid),
                    self.assertRaises(InputValidationError),
                ):
                    specification.transform({"x": (0.0, invalid, 1.0)})

    def test_factor_terms_fail_closed_for_every_undeclared_value_class(self) -> None:
        categorical = DesignSpec.from_formula(
            Formula(
                response=None,
                terms=(CategoricalTerm(Variable("x"), ("base", "A", "B")),),
            )
        )
        ordered = DesignSpec.from_formula(
            Formula(
                response=None,
                terms=(OrderedTerm(Variable("x"), (1.0, 2.0, 4.0)),),
            )
        )
        for invalid in (None, "unknown", 1.0, math.nan, True):
            with (
                self.subTest(kind="categorical", invalid=invalid),
                self.assertRaises(InputValidationError),
            ):
                categorical.transform({"x": ("base", invalid)})
        for invalid in (None, "2", 3.0, math.nan, True):
            with (
                self.subTest(kind="ordered", invalid=invalid),
                self.assertRaises(InputValidationError),
            ):
                ordered.transform({"x": (1.0, invalid)})


if __name__ == "__main__":
    unittest.main()
