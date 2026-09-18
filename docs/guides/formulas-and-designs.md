# Formulas and numeric designs

Holocron owns a small formula language instead of evaluating Python or R code.
The current grammar is additive and numeric: unchanged predictors, raw
polynomials, linear splines, and restricted cubic splines with explicit knots.

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
```

The design omits an intercept column. `formula.include_intercept` records the
policy for a later estimator. Every generated column has a stable name,
originating variable, transformation kind, term index, within-term index, and
nonlinear flag. `DesignMatrix.to_numpy()` returns an independent array.

## Grammar

The supported spellings are:

```text
response ~ x + asis(z) + pol(score, 3)
         + lsp(time, [1, 4]) + rcs(age, [20, 40, 60, 80])
~ 0 + x
```

Use backticks for names containing spaces, operators, parentheses, or reserved
transformation names. A literal backtick is doubled: `` `tick``name` ``. Quoted
contents remain column names; they are never interpreted.

Only `+`, `~`, the four registered term forms, and a leading `0` or `-1`
intercept control are accepted. Calls such as `log(x)`, interactions, arbitrary
operators, keyword arguments, strings, callbacks, and Python expressions fail
explicitly.

## Current boundary

Inputs are named, equal-length iterables of finite numeric values. Missing values
are rejected at design construction; model-level row exclusion is not yet
defined. Polynomial degrees are 2–10. Linear splines require at least one
strictly increasing knot and restricted cubic splines at least three. Automatic
knots, categorical terms, interactions, offsets, strata, and dataframe adapters
are deferred.

See the [acceptance record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_2_FORMULA_DESIGN.md)
and generated [compatibility inventory](../compatibility.md) for the exact
experimental claim.
