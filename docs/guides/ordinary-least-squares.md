# Ordinary least squares

`fit_ols` estimates a classical full-rank linear model from an already
constructed numeric design matrix. It uses QR factorization and reports an
immutable `OlsResult`.

```python
# holocron: execute
from holocron.models import fit_ols

fit = fit_ols(
    response=(1.2, 2.0, 2.9, 4.1, 5.2),
    features=((0.0,), (1.0,), (2.0,), (3.0,), (4.0,)),
    feature_names=("dose",),
)

future = fit.predict(((5.0,), (6.0,)))
assert fit.coefficient_names == ("Intercept", "dose")
assert fit.residual_degrees_of_freedom == 3
assert len(future) == 2
```

## Reported quantities

The result contains coefficients, the classical covariance matrix, fitted
values, residuals, residual scale, residual degrees of freedom, rank, dimensions,
and the intercept policy. The covariance uses the unbiased residual variance
estimate. Prediction requires feature columns in the original fitted order.

## Failure behavior

Holocron rejects empty or non-finite inputs, unequal row widths, row-count
mismatches, duplicate or missing feature names, non-positive residual degrees of
freedom, and rank-deficient designs. It does not silently discard aliased
columns.

Formula parsing, weights, offsets, robust or clustered covariance, penalization,
ANOVA, contrasts, missing-data policies, and R `rms` model objects are deferred.
Consult the generated [models API](../api/models.md) and
[compatibility inventory](../compatibility.md) for the authoritative boundary.
