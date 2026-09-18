# Ordinary least squares

`fit_ols` estimates a classical full-rank linear model from an already
constructed numeric design matrix. It uses QR factorization and reports an
immutable `OlsResult`.

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.models import OlsResult, fit_ols

specification = DesignSpec.from_formula("response ~ dose")
design = specification.transform({"dose": (0.0, 1.0, 2.0, 3.0, 4.0)})
fit = fit_ols((1.2, 2.0, 2.9, 4.1, 5.2), design)

future_design = specification.transform({"dose": (5.0, 6.0)})
future = fit.predict(future_design)
restored = OlsResult.from_json(fit.to_json())
assert fit.coefficient_names == ("Intercept", "asis(dose)")
assert fit.residual_degrees_of_freedom == 3
assert restored.design_fingerprint == specification.fingerprint
assert len(future) == 2
```

## Reported quantities

The result contains coefficients, the classical covariance matrix, fitted
values, residuals, residual scale, residual degrees of freedom, rank, dimensions,
the intercept policy, and an optional design-specification fingerprint. The
covariance uses the unbiased residual variance estimate. Passing a
`DesignMatrix` to both fit and prediction preserves and verifies transformation
identity; raw arrays require feature columns in the original fitted order but
cannot provide that check.

The complete result has a versioned non-executable JSON representation. See
[serialization and reconstruction](serialization.md) before persisting it;
fitted values and residuals may be sensitive.

## Failure behavior

Holocron rejects empty or non-finite inputs, unequal row widths, row-count
mismatches, duplicate or missing feature names, non-positive residual degrees of
freedom, and rank-deficient designs. It does not silently discard aliased
columns.

Formula parsing, weights, offsets, robust or clustered covariance, penalization,
ANOVA, contrasts, missing-data policies, and R `rms` model objects are deferred.
Consult the generated [models API](../api/models.md) and
[compatibility inventory](../compatibility.md) for the authoritative boundary.
