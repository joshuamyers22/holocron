# Extended model replacements

Holocron provides bounded Python-native replacements for four Phase 8 `rms`
exports. They are deliberately mapped capabilities, not drop-in R parity.

## Fixed-covariance GLS

```python
from holocron.models import fit_gls

fit = fit_gls(
    response=(1.0, 2.1, 2.8, 4.2),
    features=((0.0,), (1.0,), (2.0,), (3.0,)),
    observation_covariance=(
        (1.0, 0.2, 0.0, 0.0),
        (0.2, 1.0, 0.2, 0.0),
        (0.0, 0.2, 1.0, 0.2),
        (0.0, 0.0, 0.2, 1.0),
    ),
    method="reml",
)
```

The covariance is treated as known up to one residual scale. Holocron does not
estimate `corFloorExp`, grouped correlation, or variance structures.

## Single-quantile regression

```python
from holocron.models import fit_quantile_regression

median = fit_quantile_regression(
    response=(1.0, 2.0, 2.5, 5.0, 8.0),
    features=((0.0,), (1.0,), (2.0,), (3.0,), (4.0,)),
    quantile=0.5,
)
```

The estimator fits one optional-weight quantile using deterministic ADMM. The
reported covariance is a bounded kernel-density approximation. Multiple
quantiles, algorithm selection, and bootstrap inference are not supported.

## Right-censored Buckley–James AFT

```python
from holocron.models import fit_buckley_james

fit = fit_buckley_james(
    times=(1.1, 1.7, 2.4, 3.0, 4.8, 5.5),
    events=(1, 1, 1, 1, 1, 0),
    features=((-2.0,), (-1.0,), (0.0,), (1.0,), (2.0,), (3.0,)),
    link="log",
)
```

Both observed events and right-censored rows are required. The fit uses
Kaplan–Meier residual-tail imputation and raises `ConvergenceError` instead of
returning an unconverged or cycle-averaged estimate. Its covariance is an
event-only working OLS approximation, not bootstrap inference.

## Parametric AFT to proportional hazards

```python
from holocron.models import fit_psm, to_proportional_hazards

aft = fit_psm(times, events, features, distribution="weibull")
ph = to_proportional_hazards(aft)
survival = ph.predict_survival(new_features, times=(1.0, 2.0, 5.0))
```

The conversion preserves survival predictions for a one-scale Weibull or
exponential model. `conditional_covariance` conditions on the fitted AFT scale;
it is not the joint delta-method covariance. Scale-stratified fits are rejected.

Each result supports canonical `to_json`, strict `from_json`, a stable
`fingerprint`, and a packaged versioned JSON schema. See the
[compatibility inventory](../compatibility.md) and the Phase 8 governance
decision for all helper replacements and unsupported boundaries.
