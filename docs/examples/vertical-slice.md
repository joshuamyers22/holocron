# End-to-end vertical slice

This historical Phase 1 example combines the initial spline and OLS
capabilities. It uses fixed knots and a tiny synthetic dataset so that the
documentation remains deterministic and offline. For the current end-to-end
surface, use the [complete Phase 3 workflow](../getting-started.md).

```python
# holocron: execute
import numpy as np

from holocron.design import RestrictedCubicSplineSpec
from holocron.models import fit_ols

age = (30.0, 38.0, 45.0, 52.0, 60.0, 68.0, 75.0, 82.0)
score = (2.1, 2.4, 2.9, 3.7, 4.8, 5.6, 5.9, 6.1)
spec = RestrictedCubicSplineSpec((30.0, 45.0, 60.0, 82.0))
design = spec.transform(age)

model = fit_ols(
    score,
    design,
    feature_names=("age", "age nonlinear 1", "age nonlinear 2"),
)
predictions = np.asarray(model.predict(design))

assert model.rank == 4
assert model.residual_degrees_of_freedom == 4
assert np.isfinite(predictions).all()
```

The model describes this synthetic sample only. A useful scientific workflow
would additionally specify the estimand, adjustment strategy, knot rationale,
missing-data policy, uncertainty target, validation plan, and external-validity
boundary. Those concerns cannot be recovered from a fitted coefficient vector.

The parity laboratory evaluates design values, coefficients, covariance, fitted
values, residuals, scale, rank, and metadata under named tolerances. It does not
establish that this example is an appropriate model for any real decision.

The Phase 1 acceptance workflow runs the same design, fit, and public prediction
path against a versioned oracle case:

```sh
make phase-1-e2e
```

It compares with the committed output from the pinned R oracle and writes
schema-valid, hashed evidence under `.work/phase-1-evidence/`.
