# Survival models

Holocron's five experimental Phase 5 slices provide independent
equivalents for `cph`, `psm`, and `npsurv`. Cox and Kaplan–Meier fitting accept
positive follow-up times with an explicit 0/1 event indicator; parametric AFT
fitting additionally accepts explicit left/right/interval bounds. Model fitting
uses caller-supplied numeric feature rows; it does not evaluate R formulas or
silently discard missing observations.

The implemented envelope is exercised by a locked seven-scenario,
1,280-replication simulation gate spanning Cox ties/strata/offsets,
right- and mixed-censored Weibull AFT recovery, Kaplan–Meier coverage, and
censoring-adjusted validation. The technical thresholds pass, but independent
numerical/statistical reviewer Ron Mexico approved the scoped evidence on
2026-09-18, closing the Phase 5 private-development exit gate. The APIs remain
experimental.

## Cox proportional hazards

`fit_cph` supports Efron and Breslow handling of tied event times. Returned
linear predictors are centered at the training feature means, matching the
registered `rms::cph` contract. Survival predictions combine those predictors
with the fitted stratum-specific baseline cumulative hazard. Optional entry
times use the counting-process interval `(entry, time]`; weights must be finite
and positive, and offsets are additive on the log-hazard scale.

```python
# holocron: execute
from holocron.models import CoxResult, fit_cph

time = (8, 7, 6, 5, 4, 3, 2, 1)
event = (0, 1, 1, 0, 1, 1, 1, 1)
x = ((0.2,), (-1.2,), (1.3,), (-0.4,), (0.8,), (-0.8,), (1.8,), (0.1,))

cox = fit_cph(time, event, x, method="efron", feature_names=("x",))
cox_curve = cox.predict_curve(((-1.0,), (1.0,)), (0.0, 2.0, 4.0, 6.0))
cox_median = cox.predict_quantile(((-1.0,), (1.0,)))
cox_restricted_mean = cox.predict_mean(((-1.0,), (1.0,)), restricted_time=6.0)
assert CoxResult.from_json(cox.to_json()) == cox
assert all(row[3] <= row[2] <= row[1] <= row[0] for row in cox_curve.survival)
assert len(cox_median) == len(cox_restricted_mean) == 2
```

The Cox coefficient is a log hazard ratio per feature unit. A positive value
means larger hazard and therefore lower predicted survival, conditional on the
proportional-hazards assumption. This implementation does not test that
assumption for the caller.

`predict_quantile` accepts event-time CDF probabilities, so `0.5` requests the
median. Cox and Kaplan–Meier quantiles return `None` when follow-up never reaches
the requested probability. `predict_mean` requires `restricted_time` for these
finite-support curves; Cox follows the pinned `Mean.cph` event-grid integration
contract. Use `interpolation="linear"` only when polygon interpolation is part
of the declared estimand; the default is the observed step-function contract.
Kaplan–Meier step quantiles follow `quantile.survfit`'s midpoint convention when
the fitted curve lands exactly on the requested survival threshold.

For a stratified fit, prediction must identify the stratum for every feature
row. Baseline hazard increments, cumulative hazard, and baseline survival share
the aligned `baseline_strata` and `baseline_times` coordinates.

```python
# holocron: execute
from holocron.models import fit_cph, survival_residuals

time = (8, 7, 6, 5, 4, 3, 2, 1)
event = (0, 1, 1, 0, 1, 1, 1, 1)
x = ((0.2,), (-1.2,), (1.3,), (-0.4,), (0.8,), (-0.8,), (1.8,), (0.1,))
entry = (0, 1, 0, 2, 0, 1, 0, 0)
strata = ("A", "A", "A", "A", "B", "B", "B", "B")
weights = (1, 2, 1, 1, 1, 2, 1, 1)
offsets = (0, 0.1, -0.1, 0, 0.05, -0.05, 0, 0)

stratified_cox = fit_cph(
    time,
    event,
    x,
    entry_times=entry,
    strata=strata,
    weights=weights,
    offsets=offsets,
)
cox_curve = stratified_cox.predict_survival(
    ((0.0,), (0.0,)), (2.0, 4.0), strata=("A", "B")
)
cox_residual = survival_residuals(
    stratified_cox, time, event, entry_times=entry, strata=strata
)
assert len(cox_curve) == 2
assert len(cox_residual.values) == len(time)
```

## Parametric accelerated failure time

`fit_psm` supports Weibull and exponential distributions. Coefficients describe
the location of log survival time: a positive feature coefficient shifts the
time distribution later. Weibull scale is estimated; exponential scale is
fixed at one under the `survreg`/`psm` parameterization.
Positive weights and log-time offsets are supported. Weibull scale strata
estimate a separate positive scale for each declared level; exponential models
have fixed scale one and therefore reject multiple scale strata.

Right-censored inputs retain the compact `(times, events, features)` call.
`SurvivalResponse` supplies explicit positive-time bounds for exact, left-,
right-, and interval-censored likelihood contributions:

```python
# holocron: execute
from math import inf

from holocron.models import SurvivalResponse, fit_psm

response = SurvivalResponse.from_intervals(
    (12, 8, 12, 7, 10, -inf, 7, -inf, 5, 8, 12, 7),
    (12, 10, inf, 7, inf, 7, 9, 5, 5, inf, 14, 7),
)
features = tuple(
    (value,) for value in (-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, -1.8, -0.8, 0.2)
)
censored_weibull = fit_psm(response, features, feature_names=("x",))
assert set(response.censoring_types) == {"exact", "left", "right", "interval"}
assert censored_weibull.log_likelihood[1] > censored_weibull.log_likelihood[0]
```

An exact observation has equal finite bounds, left censoring uses `-inf` as the
lower bound, right censoring uses `inf` as the upper bound, and a finite ordered
pair declares an interval. Empty, nonpositive, reversed, fully unbounded, and
all-right-censored responses fail closed.

```python
# holocron: execute
from holocron.models import ParametricSurvivalResult, fit_psm

time = (8, 7, 6, 5, 4, 3, 2, 1)
event = (0, 1, 1, 0, 1, 1, 1, 1)
x = ((0.2,), (-1.2,), (1.3,), (-0.4,), (0.8,), (-0.8,), (1.8,), (0.1,))

weibull = fit_psm(time, event, x, distribution="weibull", feature_names=("x",))
weibull_curve = weibull.predict_curve(((-1.0,), (1.0,)), (2.0, 4.0, 6.0))
weibull_quantiles = weibull.predict_quantile(((-1.0,), (1.0,)), (0.25, 0.5, 0.75))
weibull_means = weibull.predict_mean(((-1.0,), (1.0,)))
assert ParametricSurvivalResult.from_json(weibull.to_json()) == weibull
assert weibull.scale is not None and weibull.scale > 0.0
assert all(row[2] < row[1] < row[0] for row in weibull_curve.survival)
assert all(row[0] < row[1] < row[2] for row in weibull_quantiles)
assert all(value > 0.0 for value in weibull_means)
```

`predict_hazard` uses the same explicit stratum and offset contract as
`predict_survival`. For right-censored fits, parametric residuals support
`response`, `normalized`, `martingale`, and `deviance`; Cox residuals support
`martingale` and `deviance`.

## Kaplan–Meier

`fit_npsurv` returns one row per observed time within each stratum, including
censor-only times. Entry times and positive frequency weights modify the risk,
event, and censor counts explicitly.
`standard_error` is the standard error of log survival from Greenwood's sum;
the lower and upper bounds use the corresponding log-scale interval.

```python
# holocron: execute
from holocron.models import NonparametricSurvivalResult, fit_npsurv

time = (8, 7, 6, 5, 4, 3, 2, 1)
event = (0, 1, 1, 0, 1, 1, 1, 1)

curve = fit_npsurv(time, event)
assert curve.predict((0.0, 2.0, 5.0))[0] == 1.0
km_curve = curve.predict_curve((0.0, 2.0, 5.0))
km_median = curve.predict_quantile()
km_restricted_mean = curve.predict_mean(restricted_time=5.0)
assert km_curve.survival[0][0] == 1.0
assert len(km_median) == len(km_restricted_mean) == 1
assert NonparametricSurvivalResult.from_json(curve.to_json()) == curve
```

## Fixed-horizon validation

`validate_survival_predictions` evaluates a row-aligned survival-probability
matrix against right-censored outcomes. It estimates censoring with
Kaplan–Meier, uses inverse censoring weights for Brier scores and event cases in
cumulative/dynamic AUC, and reports signed marginal calibration as observed
minus mean predicted survival.

```python
# holocron: execute
from holocron.models import validate_survival_predictions

validation = validate_survival_predictions(
    (1, 2, 3, 4, 5, 6),
    (1, 0, 1, 0, 1, 1),
    (
        (0.75, 0.50, 0.25),
        (0.80, 0.58, 0.32),
        (0.70, 0.45, 0.20),
        (0.85, 0.65, 0.40),
        (0.90, 0.72, 0.48),
        (0.92, 0.78, 0.55),
    ),
    (2.5, 4.5, 5.5),
)
assert validation.integrated_brier_score is not None
assert validation.integrated_auc is not None
assert validation.integrated_absolute_calibration_error is not None
assert validation.case_counts == (1, 2, 3)
assert all(value >= 0.0 for value in validation.brier_scores)
assert len(validation.calibration_groups) == 3
assert len(validation.threshold_metrics) == 3
```

An AUC and Dxy value is `None` when a horizon lacks either an observed event
case or an event-free control. All integrated metrics are `None` for a single
horizon; otherwise they are normalized trapezoidal integrals over the supplied
horizon interval. Integrated AUC is also `None` when AUC is undefined at any
horizon. Calibration groups are ranked by predicted survival without splitting
prediction ties and use within-group Kaplan--Meier observed survival. Threshold
metrics classify predicted event risk and apply censoring adjustment to
evaluable cases and controls. Positive weights have frequency-weight semantics.

## Supported boundary

Cox score, Schoenfeld, influence, and robust covariance operations are
deferred. Parametric distributions beyond Weibull/exponential and residuals for
left-/interval-censored responses are deferred. Kaplan–Meier alternate
estimators, interval-censored nonparametric curves, competing risks, and robust
variance are also deferred.
Formula-level survival fitting and dataframe missing-row behavior are not
inferred from the input.

Full `validate.cph`/`validate.psm` resampling, optimism correction, smooth
`hare`/`smoothkm` calibration, Cox–Snell plots, left/interval-censored
validation, entry times, competing-risk metrics, and time-varying covariate
paths remain deferred.

The sixteen registered survival cases additionally cover censoring
likelihoods, counting-process entry, strata, weights, offsets, baseline
hazard/survival, hazard prediction, and supported residuals, curves, means, and
quantiles, plus fixed-horizon accuracy, discrimination, and marginal
calibration. The later grouped-calibration, threshold, and integrated-summary
extensions are owned Python contracts rather than additional `val.surv` parity
claims. These are narrow evidence, not evidence of model validity,
proportional hazards, correct distribution choice, transportability, or
fitness for consequential use.
