# Restricted cubic splines

Restricted cubic splines allow a predictor's association to bend between knots
while constraining both tails to be linear. Holocron's initial design primitive
accepts explicit knots only, which keeps the statistical specification visible
and reproducible.

```python
# holocron: execute
from holocron.design import RestrictedCubicSplineSpec

spec = RestrictedCubicSplineSpec((0.0, 2.0, 5.0, 10.0))
basis = spec.transform((0.0, 1.0, 3.0, 8.0, 12.0))

assert basis.shape == (5, 3)
assert spec.nonlinear_mask == (False, True, True)
assert basis[:, 0].tolist() == [0.0, 1.0, 3.0, 8.0, 12.0]
```

## Contract

- Supply at least three finite, strictly increasing knots.
- Supply a one-dimensional iterable of finite values.
- Expect one linear column followed by `len(knots) - 2` nonlinear columns.
- Expect linear tails beyond the boundary knots.
- Treat column order as part of the public design contract.

The nonlinear columns use the explicit-knot normalization matched to the pinned
`rms::rcs` oracle cases. The precise signature is in the generated
[design API reference](../api/design.md).

## Current boundary

Automatic knot placement, formula parsing, principal-component rotation, and
interaction restrictions are not implemented. Data-distribution metadata can
retain labels and units, but it is not yet connected to spline construction. Do
not infer support for the full R `rcs` function from this primitive. See the
[compatibility page](../compatibility.md) for the exact claim.

Tests of nonlinearity and simultaneous inference require a fitted-model
inference contract that is not part of this slice. The nonlinear mask identifies
the relevant columns, but it is not itself a statistical test.
