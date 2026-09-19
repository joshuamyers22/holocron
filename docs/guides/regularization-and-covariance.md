# Penalties and alternative covariance

Holocron supports explicit diagonal quadratic penalties for OLS and binary
`lrm`, plus cluster-sandwich and iid bootstrap covariance for every currently
supported OLS, binomial `Glm`, and binary `lrm` fit.

## Penalized fits

Pass either one non-negative penalty for every slope or a mapping keyed by the
generated coefficient names. The intercept is never penalized.

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.models import fit_penalized_lrm, fit_penalized_ols

x = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0) * 2
event = (0, 0, 0, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1)
specification = DesignSpec.from_formula("event ~ x")
design = specification.transform({"x": x})

logistic = fit_penalized_lrm(event, design, penalty={"asis(x)": 1.5})
assert logistic.penalty_weights == (1.5,)
assert logistic.design_fingerprint == specification.fingerprint

y = tuple(3.0 + 0.8 * value + (-1) ** index * 0.1 for index, value in enumerate(x))
linear = fit_penalized_ols(y, design, penalty=2.0, variance="sandwich")
assert linear.model_type == "ols"
assert linear.predict_response(design) == linear.fitted_values
```

`fit_penalized_ols` implements the `rms::ols` simple and sandwich penalty-
variance choices. `fit_penalized_lrm` uses the inverse penalized information,
matching binary `rms::lrm`. Both results report the applied slope weights and
effective degrees of freedom. A positive penalty can produce a finite binary
fit for data that are separated under unpenalized maximum likelihood.

`trace_penalty` evaluates an explicit, bounded scalar grid for an existing OLS
or binary `lrm` fit. It returns every refit's coefficients, deviance, effective
degrees of freedom, AIC, and BIC, then selects the minimum requested criterion
with the smaller penalty breaking a tie. This is an owned Python contract, not
R `pentrace` parity or an adaptive search.

```python
# holocron: execute
from holocron.models import fit_ols, trace_penalty

x = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0)
y = (0.8, 1.5, 2.1, 3.0, 3.7, 4.6, 5.1, 6.2)
features = tuple((value,) for value in x)
fit = fit_ols(y, features, feature_names=("x",))
trace = trace_penalty(fit, y, features, (0.0, 0.5, 2.0))

assert trace.selected_point.penalty in {0.0, 0.5, 2.0}
assert len(trace.points) == 3
```

## Cluster-sandwich covariance

`robust_covariance` requires the original response and analysis design because
the persisted fit does not retain every score input. Omitting `clusters` treats
each observation as its own cluster.

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.models import fit_ols, robust_covariance

x = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0)
y = (0.8, 1.5, 2.1, 3.0, 3.7, 4.6, 5.1, 6.2)
specification = DesignSpec.from_formula("y ~ x")
design = specification.transform({"x": x})
fit = fit_ols(y, design)
clusters = ("a", "a", "b", "b", "c", "c", "d", "d")
estimate = robust_covariance(fit, y, design, clusters=clusters)

assert estimate.method == "robust"
assert estimate.cluster_count == 4
```

This is the uncorrected Huber cluster sandwich used by the supported
`rms::robcov` path. It does not apply HC1-style small-sample corrections.

## Bootstrap covariance

The default bootstrap uses NumPy's seeded generator and resamples analysis rows
with replacement. A declared schedule makes every row selection reviewable and
allows the same schedule to be replayed in another implementation.

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.models import bootstrap_covariance, fit_ols

x = (-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0)
y = (0.8, 1.5, 2.1, 3.0, 3.7, 4.6, 5.1, 6.2)
specification = DesignSpec.from_formula("y ~ x")
design = specification.transform({"x": x})
fit = fit_ols(y, design)
estimate = bootstrap_covariance(fit, y, design, replicates=20, seed=90210)

assert estimate.method == "bootstrap"
assert estimate.replicate_count == 20
assert estimate.seed == 90210
```

Every requested replicate must fit successfully. Holocron raises a structured
numerical error instead of silently discarding a separated, singular, or
single-class bootstrap sample.

## Boundaries

Only diagonal slope penalties are supported. Arbitrary dense or categorical
penalty matrices, adaptive penalty search and R `pentrace` parity, penalized
`Glm`, weights, offsets,
penalized post-estimation inference, Efron OLS robust covariance, finite-sample
corrections, cluster bootstrap, stratified/grouped resampling, failed-replicate
skipping, bootstrap coefficient persistence, and bootstrap confidence intervals
remain outside this contract.
