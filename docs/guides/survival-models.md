# Survival models

Holocron's first experimental Phase 5 slice provides independent equivalents
for `cph`, `psm`, and `npsurv`. All APIs accept positive follow-up times and an
explicit 0/1 event indicator. Model fitting uses caller-supplied numeric feature
rows; it does not evaluate R formulas or silently discard missing observations.

## Cox proportional hazards

`fit_cph` supports Efron and Breslow handling of tied event times. Returned
linear predictors are centered at the training feature means, matching the
registered `rms::cph` contract. Survival predictions combine those predictors
with the fitted baseline cumulative hazard.

```python
# holocron: execute
from holocron.models import CoxResult, fit_cph

time = (8, 7, 6, 5, 4, 3, 2, 1)
event = (0, 1, 1, 0, 1, 1, 1, 1)
x = ((0.2,), (-1.2,), (1.3,), (-0.4,), (0.8,), (-0.8,), (1.8,), (0.1,))

cox = fit_cph(time, event, x, method="efron", feature_names=("x",))
cox_survival = cox.predict_survival(((-1.0,), (1.0,)), (2.0, 4.0, 6.0))
assert CoxResult.from_json(cox.to_json()) == cox
assert all(row[2] <= row[1] <= row[0] for row in cox_survival)
```

The Cox coefficient is a log hazard ratio per feature unit. A positive value
means larger hazard and therefore lower predicted survival, conditional on the
proportional-hazards assumption. This implementation does not test that
assumption for the caller.

## Parametric accelerated failure time

`fit_psm` supports Weibull and exponential distributions. Coefficients describe
the location of log survival time: a positive feature coefficient shifts the
time distribution later. Weibull scale is estimated; exponential scale is
fixed at one under the `survreg`/`psm` parameterization.

```python
# holocron: execute
from holocron.models import ParametricSurvivalResult, fit_psm

time = (8, 7, 6, 5, 4, 3, 2, 1)
event = (0, 1, 1, 0, 1, 1, 1, 1)
x = ((0.2,), (-1.2,), (1.3,), (-0.4,), (0.8,), (-0.8,), (1.8,), (0.1,))

weibull = fit_psm(time, event, x, distribution="weibull", feature_names=("x",))
weibull_survival = weibull.predict_survival(((-1.0,), (1.0,)), (2.0, 4.0, 6.0))
assert ParametricSurvivalResult.from_json(weibull.to_json()) == weibull
assert weibull.scale > 0.0
assert all(row[2] < row[1] < row[0] for row in weibull_survival)
```

## Kaplan–Meier

`fit_npsurv` returns one row per observed time, including censor-only times.
`standard_error` is the standard error of log survival from Greenwood's sum;
the lower and upper bounds use the corresponding log-scale interval.

```python
# holocron: execute
from holocron.models import NonparametricSurvivalResult, fit_npsurv

time = (8, 7, 6, 5, 4, 3, 2, 1)
event = (0, 1, 1, 0, 1, 1, 1, 1)

curve = fit_npsurv(time, event)
assert curve.predict((0.0, 2.0, 5.0))[0] == 1.0
assert NonparametricSurvivalResult.from_json(curve.to_json()) == curve
```

## Supported boundary

The current slice is right-censoring only. Cox strata, entry times, weights,
offsets, residuals, and robust covariance are deferred. Parametric left- and
interval-censoring and distributions beyond Weibull/exponential are deferred.
Kaplan–Meier grouping, entry times, weights, and alternate estimators are also
deferred. Formula-level survival fitting and dataframe missing-row behavior are
not inferred from the input.

The six registered survival cases cover linear and restricted-cubic-spline
designs, both Cox tie methods, both parametric distributions, tied events,
censoring, covariance, log likelihood, and survival curves. They are narrow
parity evidence, not evidence of model validity, proportional hazards, correct
distribution choice, transportability, or fitness for consequential use.
