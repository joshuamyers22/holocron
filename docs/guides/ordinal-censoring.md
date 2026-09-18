# Ordinal regression and censoring

Holocron's experimental ordinal surface fits proportional cumulative-link
models from an explicit numeric design. `fit_orm` supports logistic, probit,
log-log, complementary log-log, and Cauchy links. `fit_ordinal_lrm` is the
multi-intercept proportional-odds specialization.

```python
from holocron.design import DesignSpec
from holocron.models import OrdinalResult, fit_orm

response = (1, 1, 2, 1, 2, 2, 3, 2, 3, 3)
specification = DesignSpec.from_formula("severity ~ x")
design = specification.transform({"x": (-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5)})
fit = fit_orm(response, design, family="logistic")
future = specification.transform({"x": (-0.75, 0.75)})

probabilities = fit.predict_probabilities(future)
means = fit.predict_mean(future)
medians = fit.predict_quantile(future)
exceedance = fit.predict_exceedance(future, level=2)
model_test = fit.likelihood_ratio_test()
slope_test = fit.wald_test()
diagnostics = fit.diagnostics()
restored = OrdinalResult.from_json(fit.to_json())
assert restored.predict_probabilities(future) == probabilities
```

Thresholds are stored in decreasing `P(Y >= level)` order, followed by slope
coefficients. Predictions return mutually exclusive probabilities in increasing
response-level order. Numeric levels are the scores used for predicted means;
they are not silently replaced by equally spaced ranks.

## Censored outcomes

`CensoredResponse` represents exact, left-, right-, interval-, and mixed-
censored numeric observations. At least one exact observation is required.
Finite two-sided intervals are closed. One-sided finite endpoints are open:
`(-inf, b)` excludes `b`, and `(a, inf)` excludes `a`.

```python
import math

from holocron.models import CensoredResponse, fit_orm

censored = CensoredResponse.from_intervals(
    (1, 1, 2, 2, 3, 3, -math.inf, 1, 2),
    (1, 1, 2, 2, 3, 3, 2, math.inf, 3),
)
turnbull = censored.turnbull()
fit = fit_orm(censored, tuple((float(index),) for index in range(9)))
```

Conversion rounds noninteger finite endpoints to an exact decimal grid, moves
open one-sided endpoints by one grid unit, finds Turnbull maximal intersections,
computes the self-consistent nonparametric MLE, and consolidates intersections
without estimable probability. Right censoring at the highest exact value
creates a distinct tail category. `TurnbullResult.first` and `last` map each
observation to its consecutive estimable intersections.

## Clustered random intercepts

`fit_random_intercept_orm` integrates one standard-normal cluster effect by
adaptive Gauss–Hermite quadrature. It refits on an increasing odd-node grid and
fails unless consecutive marginal log likelihoods stabilize. Its result records
the entire quadrature history, posterior cluster modes, the observed marginal
covariance, and a boundary-aware variance-component test.

Passing `mix_re` uses
`sigma1 * (1 - mix_re) + sigma2 * mix_re` as the observation-specific random-
effect loading. `sigma1` is positive, `sigma2` is signed, and `mix_re` must vary
within at least one cluster. The model likelihood-ratio comparison uses a null
model with the same cluster and quadrature structure.

## Numerical envelope and boundaries

For exact outcomes, the threshold block of the observed information is
tridiagonal; Newton updates use a bordered-tridiagonal solve and a dense Schur
complement over slopes. General interval censoring falls back to a dense solve
because an interval can couple nonadjacent thresholds. Returned covariance is
dense and therefore grows quadratically: with `K` response levels and `p`
features it stores `(K - 1 + p)^2` float64 values. Inputs are capped at 1,024
parameters. The test gate includes a 64-level fit; this is a correctness bound,
not a large-scale performance claim.

Six `orm` fixtures pass the pinned R oracle under named field-aware policies:
three exact-response, one interval-censored, one random-intercept, and one
dual-scale `mix_re` case. The locked Phase 4 simulations, quadrature checks,
sparsity measurements, and failure corpus also pass on the accepted platform
matrix. One-sided censoring keeps the documented open-endpoint semantics under
an explicit pinned-R parity exception. Ron Mexico independently approved the
complete Phase 4 private experimental scope, including that exception, on
2026-09-18; the exit gate is closed.

Weights, offsets, penalties, partial proportional odds, arbitrary character or
factor censoring endpoints, missing-row reinsertion, y-dependent effects,
multiple or crossed random effects, random slopes, and correlated random
effects are unsupported. Conditional predictions from a random-effects fit use
random effect zero; marginal predictive probabilities are not yet exposed.
