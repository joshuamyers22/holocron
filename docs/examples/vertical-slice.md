# End-to-end vertical slice

This example combines the two experimental capabilities. It uses fixed knots and
a tiny synthetic dataset so that the documentation remains deterministic and
offline.

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
fitted = np.asarray(model.fitted_values)

assert model.rank == 4
assert model.residual_degrees_of_freedom == 4
assert np.isfinite(fitted).all()
```

The model describes this synthetic sample only. A useful scientific workflow
would additionally specify the estimand, adjustment strategy, knot rationale,
missing-data policy, uncertainty target, validation plan, and external-validity
boundary. Those concerns cannot be recovered from a fitted coefficient vector.

The parity laboratory evaluates design values, coefficients, covariance, fitted
values, residuals, scale, rank, and metadata under named tolerances. It does not
establish that this example is an appropriate model for any real decision.
