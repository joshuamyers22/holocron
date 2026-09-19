# Diagnostics and selection

Holocron provides bounded, typed diagnostics for current OLS and binary-
logistic results. These are owned Python contracts: they do not claim parity
with R `vif`, `which.influence`, `pentrace`, or `fastbw`.

## Inspect influence, collinearity, and uncertainty

`influence_diagnostics` requires the original response and realized analysis
design. For OLS it reports exact case-deletion coefficient changes; for binary
logistic models the changes are one-step approximations. Leverage, Cook
distance, and DFBETA flags use thresholds stored on the result.

`variance_inflation_factors` derives slope VIFs from the fitted coefficient-
covariance correlation matrix. `robustness_diagnostics` presents the accepted
cluster-sandwich estimate next to model-based standard errors and their ratio.

```python
# holocron: execute
from holocron.models import (
    backward_select,
    fit_ols,
    influence_diagnostics,
    robustness_diagnostics,
    trace_penalty,
    variance_inflation_factors,
)

x = tuple(float(index - 10) for index in range(20))
z = tuple(float((index * 7) % 11 - 5) for index in range(20))
features = tuple(zip(x, z, strict=True))
response = tuple(
    2.0 + 1.5 * value + 0.1 * ((index % 5) - 2) for index, value in enumerate(x)
)
fit = fit_ols(response, features, feature_names=("x", "z"))

influence = influence_diagnostics(fit, response, features)
vifs = variance_inflation_factors(fit)
robustness = robustness_diagnostics(
    fit,
    response,
    features,
    clusters=tuple(index // 2 for index in range(20)),
)

assert len(influence.observations) == 20
assert tuple(value.coefficient_name for value in vifs) == ("x", "z")
assert robustness.covariance.cluster_count == 10

trace = trace_penalty(
    fit,
    response,
    features,
    (0.0, 0.1, 1.0, 10.0),
    criterion="bic",
)
selection = backward_select(
    fit,
    response,
    features,
    {"signal": ("x",), "noise": ("z",)},
)

assert trace.selected_point in trace.points
assert selection.selected_terms == ("signal",)
assert selection.final_model.coefficient_names == ("Intercept", "x")
```

Flags identify observations worth investigating; they do not prescribe row
deletion. A robust standard error changes an uncertainty estimate, not the
model, estimand, or adequacy of the design.

## Trace a declared penalty grid

`trace_penalty` accepts 1–1,000 strictly increasing, non-negative scalar
penalties. It reuses the supplied unpenalized fit at zero and freshly fits every
positive point with `fit_penalized_ols` or `fit_penalized_lrm`. Each point
retains coefficients, constant-free deviance, effective degrees of freedom,
AIC, and BIC. The result chooses the minimum requested criterion and breaks an
exact tie toward the smaller penalty.

The function does not choose a grid, optimize between points, accept a dense
penalty matrix, or reproduce R `pentrace`. Effective degrees of freedom follow
the accepted penalized-fit contract and need not decrease monotonically for
penalized OLS.

## Run declared-group backward selection

`backward_select` requires a mapping from term labels to coefficient names that
partitions every slope exactly once. At each step it computes joint Wald tests,
removes the eligible term with the largest p-value above the declared level,
and freshly refits the reduced model. Protected terms are never removed and at
least one term remains.

Holocron does not infer marginality or hierarchy from coefficient names. Group
spline or factor columns explicitly and protect required main effects. The
reported p-values are selection inputs, not valid post-selection inference.
For honest performance assessment, repeat the complete selection procedure
inside each resample and reserve an independent final assessment when the
application requires one.

## Boundaries

Ordinal and survival diagnostics, exact binary case-deletion refits, influence
for penalized fits, generalized VIF variants, adaptive penalty search, automatic
hierarchy discovery, penalized selection, and R method parity remain outside
this contract. Inputs must reproduce the fitted response and realized design;
identity mismatches and unsupported models fail explicitly.
