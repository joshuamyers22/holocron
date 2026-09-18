# Getting started

The first qualified workflow constructs an explicit restricted cubic spline
basis, fits OLS to that design, and predicts at the same rows.

```python
# holocron: execute
import numpy as np

from holocron.design import RestrictedCubicSplineSpec
from holocron.models import fit_ols

x = (-2.0, -1.0, 0.0, 1.0, 2.0, 3.0)
y = (0.2, 0.8, 1.1, 1.7, 2.5, 3.6)

spec = RestrictedCubicSplineSpec((-2.0, 0.0, 1.5, 3.0))
design = spec.transform(x)
fit = fit_ols(y, design, feature_names=("x", "x'", "x''"))
predictions = fit.predict(design)

assert design.shape == (6, 3)
assert fit.coefficient_names == ("Intercept", "x", "x'", "x''")
assert np.allclose(predictions, fit.fitted_values)
```

`RestrictedCubicSplineSpec` retains the untransformed predictor as its first
column. The remaining columns describe nonlinear components. `fit_ols` adds an
intercept by default and requires positive residual degrees of freedom and a
full-rank design.

This example demonstrates mechanics, not a defensible analysis strategy. Knot
selection, estimands, adjustment variables, missing-data handling, validation,
and interpretation remain the caller's responsibility. Read the
[spline guide](guides/restricted-cubic-splines.md),
[OLS guide](guides/ordinary-least-squares.md), and
[limitations](interpretation-and-limitations.md) before using the result.
