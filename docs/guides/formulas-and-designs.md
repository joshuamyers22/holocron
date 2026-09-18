# Formulas and deterministic designs

Holocron owns a small formula language instead of evaluating Python or R code.
The grammar covers unchanged predictors, raw polynomials, linear and restricted
cubic splines, explicitly leveled categorical and scored-ordered predictors,
and restricted two-way interactions.

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.formula import Formula

formula = Formula.parse(
    "outcome ~ age + pol(marker, 2) + lsp(time, [1, 3]) + rcs(exposure, [0, 2, 5, 9])"
)
specification = DesignSpec.from_formula(formula)
matrix = specification.transform(
    {
        "age": (30, 45, 60),
        "marker": (-1, 0.5, 2),
        "time": (0, 2, 5),
        "exposure": (-1, 3, 10),
    }
)

assert matrix.shape == (3, 9)
assert matrix.term_slices == ((0, 1), (1, 3), (3, 6), (6, 9))
assert specification.response_values({"outcome": (0, 1, 1)}) == (0.0, 1.0, 1.0)
assert DesignSpec.from_json(specification.to_json()) == specification
assert type(matrix).from_json(matrix.to_json()) == matrix
```

The design omits an intercept column. `formula.include_intercept` records the
policy for a later estimator. Every generated column has a stable name,
originating variables, transformation kind, term index, within-term index,
nonlinear flag, and—for an interaction—the two component-column identities.
`DesignMatrix.to_numpy()` returns an independent array.
The matrix JSON carries the design-specification fingerprint, so fitted results
can retain and check transformation identity. See
[serialization and reconstruction](serialization.md) for the wire contract.

## Grammar

The supported spellings are:

```text
response ~ x + asis(z) + pol(score, 3)
         + lsp(time, [1, 4]) + rcs(age, [20, 40, 60, 80])
         + catg(group, ["control", "treated"])
         + scored(stage, [1, 2, 3, 4])
         + ia(x, rcs(age, [20, 40, 60, 80]))
~ 0 + x
```

Use backticks for names containing spaces, operators, parentheses, or reserved
transformation names. A literal backtick is doubled: `` `tick``name` ``. Quoted
contents remain column names; they are never interpreted.

Only `+`, `~`, the registered term forms, JSON string literals inside `catg`
level lists, and a leading `0` or `-1` intercept control are accepted. Calls
such as `log(x)`, arbitrary operators, keyword arguments, callbacks, and Python
expressions fail explicitly.

## Factors and ordered predictors

`catg` requires two or more explicit, unique levels of one type. The first is
the reference and produces no column; each later level produces a 0/1 column.
`scored` requires three or more strictly increasing numeric levels. Its first
column is the numeric score, and levels three onward produce nonlinear 0/1
columns, matching `rms::scored` contrast construction. The second level is
represented by the score and therefore has no separate indicator.

The serialized AST records `unknown_level: "error"`. Transformations reject
missing values, values outside the declared levels, mixed string/numeric level
declarations, and non-finite numeric levels. Level order is never inferred from
prediction data.

## Restricted interactions

`ia(left, right)` implements the `rms` restricted-interaction rule. Both
components must also occur as identical main effects, and variables must be
distinct. The compiler forms component-column products in left-major order and
omits a product when both columns are nonlinear. The result is nonlinear when
either retained component is nonlinear.

Nested interactions, self-interactions, reversed duplicates, unrestricted `*`
or `:` operators, and three-way interactions fail explicitly. Use
`DesignSpec.interactions_containing(name)` to retrieve zero-based owning term
indices.

## Current boundary

Inputs are named, equal-length iterables. Numeric terms require finite numeric
values; factor terms require declared values. Missing values are rejected at
design construction; model-level row exclusion is not yet defined. Polynomial
degrees are 2–10. Linear splines require at least one strictly increasing knot
and restricted cubic splines at least three. Formulas are limited to 64 terms,
256 generated columns, 64 factor levels per term, and 4,096 source characters.
Automatic knots or levels, offsets, strata, matrices, three-way interactions,
and dataframe adapters are deferred.

See the [acceptance record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_2_FORMULA_DESIGN.md)
and [categorical/interactions record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_2_CATEGORICAL_INTERACTIONS.md),
and generated [compatibility inventory](../compatibility.md) for the exact
experimental claim.
