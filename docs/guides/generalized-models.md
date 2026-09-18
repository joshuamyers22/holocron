# Generalized linear and binary logistic models

The first Phase 3 estimator envelope provides three explicit entry points:

- `fit_ols` for classical Gaussian linear models;
- `fit_glm` for Gaussian/identity or binomial/logit models; and
- `fit_lrm` for the supported binary subset of R `rms::lrm`.

`fit_glm` and `fit_lrm` consume an already constructed numeric matrix or a
`DesignMatrix`. They do not parse formulas or learn transformation parameters
during fitting.

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.models import BinaryLogisticResult, fit_glm, fit_lrm

specification = DesignSpec.from_formula("event ~ rcs(age, [30, 45, 60, 75])")
ages = (28, 34, 39, 44, 49, 54, 59, 64, 69, 74, 79, 84)
events = (0, 0, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1)
design = specification.transform({"age": ages})

lrm_fit = fit_lrm(events, design)
glm_fit = fit_glm(events, design, family="binomial")
future = specification.transform({"age": (42, 57, 72)})
probabilities = lrm_fit.predict_probability(future)
restored = BinaryLogisticResult.from_json(lrm_fit.to_json())

assert lrm_fit.estimator == "lrm"
assert glm_fit.estimator == "glm"
assert restored.design_fingerprint == specification.fingerprint
assert probabilities == restored.predict_probability(future)
```

## What is preserved

Both binary paths fit the same unpenalized logit likelihood, but their numerical
contracts are intentionally distinct. `fit_glm(..., family="binomial")` matches
R `Glm`/`glm.fit` initialization, deviance stopping, and working-information
covariance. `fit_lrm` uses step-halved Newton iteration to the finite maximum and
matches binary `rms::lrm` coefficients, covariance, linear predictors, deviance,
and probabilities. Do not assume their covariance matrices are bitwise
interchangeable.

A `BinaryLogisticResult` retains coefficients, covariance, training linear
predictors and probabilities, null and residual deviance, iteration count,
rank, dimensions, intercept policy, and the optional design fingerprint. Its
strict canonical JSON representation is data-only and rejects unknown fields.

Gaussian/identity `fit_glm` deliberately uses the accepted OLS implementation
and returns `OlsResult`. This makes the current identity-family behavior
explicit without introducing a second linear-result contract.

## Failure behavior and limits

The estimators reject non-binary or single-class responses, non-finite values,
row-count mismatches, rank-deficient designs, invalid controls, and inconsistent
design identities. Iteration exhaustion raises `ConvergenceError`; detected
complete or quasi-complete separation raises `SeparationError`. Neither state
returns a plausible-looking fitted result.

Only Gaussian/identity and binomial/logit `Glm` are supported. Poisson, Gamma,
inverse-Gaussian and quasi families; alternate links; weights; offsets;
penalized `Glm`; aliased columns; and formula-level fitting fail closed or
remain absent. Diagonal OLS/lrm penalties and alternative covariance estimates
are documented in the [regularization and covariance guide](regularization-and-covariance.md).
The supported covariance, likelihood, residual,
prediction, coefficient-summary, ANOVA, and contrast surface is documented in
the [post-estimation guide](post-estimation.md). Its narrow parity evidence does
not establish calibration, coverage, or production suitability.
