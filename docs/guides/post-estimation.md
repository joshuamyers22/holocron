# Post-estimation operations

The second Phase 3 deliverable adds typed post-estimation operations for the
supported `OlsResult` and binary `BinaryLogisticResult` contracts. The
operations consume fitted results; they do not refit a model or infer missing
design metadata.

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.models import (
    anova,
    contrast,
    covariance,
    fit_ols,
    likelihood,
    predict,
    residuals,
    summarize,
)

specification = DesignSpec.from_formula("y ~ x")
x = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0)
y = (0.8, 1.5, 2.1, 3.0, 3.7, 4.6, 5.1, 6.2)
design = specification.transform({"x": x})
fit = fit_ols(y, design)

fit_covariance = covariance(fit)
fit_likelihood = likelihood(fit)
fit_residuals = residuals(fit, kind="standardized")
fit_summary = summarize(fit)
term_tests = anova(fit, specification)
slope = contrast(fit, {"asis(x)": 1.0}, name="slope")

future = specification.transform({"x": (-1.5, 2.5)})
means = predict(fit, future, interval="mean")
individuals = predict(fit, future, interval="individual")

assert fit_covariance.coefficient_names == fit.coefficient_names
assert fit_likelihood.parameter_count == fit.rank + 1
assert len(fit_residuals.values) == len(y)
assert fit_summary.coefficients[1].name == "asis(x)"
assert term_tests.tests[0].term == "x"
assert slope.estimate == fit.coefficients[1]
assert individuals.standard_errors[0] > means.standard_errors[0]
```

## Operation contracts

- `covariance` returns the full named covariance matrix or a named principal
  submatrix.
- `likelihood` reports maximized and null log likelihoods, parameter count,
  AIC, and the overall likelihood-ratio statistic.
- `residuals` supports ordinary and standardized OLS residuals, and ordinary,
  Pearson, and deviance residuals for binary models.
- `predict` reports estimates, standard errors, and confidence limits. OLS
  supports mean and individual intervals. Binary models support mean intervals
  on either the linear-predictor or response-probability scale.
- `summarize` provides coefficient-level estimates and Wald inference plus the
  likelihood record.
- `anova` performs one joint Wald test for each declared formula term. A
  matching `DesignSpec` is preferred because its fingerprint and term slices
  prevent accidental regrouping.
- `contrast` evaluates one caller-declared linear combination of coefficients.
  A name-to-weight mapping is safer than positional weights.

OLS and binomial `Glm` inference uses the residual degrees of freedom and the
Student t distribution, matching the accepted R paths. Binary `lrm` inference
uses the normal distribution. OLS term tests are F tests; binary term tests are
chi-square Wald tests.

## Binary residuals

`BinaryLogisticResult` deliberately does not retain the observed response.
Provide it explicitly when requesting residuals:

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.models import fit_lrm, residuals

specification = DesignSpec.from_formula("event ~ x")
x = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0) * 2
event = (0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1)
design = specification.transform({"x": x})
fit = fit_lrm(event, design)
deviance = residuals(fit, kind="deviance", response=event)

assert len(deviance.values) == len(event)
```

## Compatibility boundary

These are narrow, immutable runtime result records, not serialized model
artifacts. `summarize` is a coefficient table; it is not the adjusted-effect
implementation of R `summary.rms`. `anova` does not yet provide nonlinear,
interaction, or total-effect partitions beyond the declared formula term
blocks. `contrast` accepts a single linear coefficient contrast, not R
expressions, design grids, simultaneous intervals, or nonlinear transformations.

Robust, clustered, sandwich, and bootstrap covariance and diagonal OLS/lrm
penalties are separate, accepted APIs described in the
[regularization and covariance guide](regularization-and-covariance.md).
Multiple-comparison adjustments, profile likelihood, offsets and weights,
bootstrap confidence intervals, and other GLM families remain unsupported.
Unsupported combinations fail explicitly.
