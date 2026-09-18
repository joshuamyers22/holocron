# Phase 5 survival-estimator acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 5 deliverable: `cph`, `psm`, and `npsurv` equivalents
- Disposition: complete within the declared experimental envelope

## Implemented contract

`fit_cph` independently implements the Cox partial likelihood for right-
censored outcomes with Efron or Breslow tie handling, step-halved Newton
optimization, observed-information covariance, mean-centered linear predictors,
an owned baseline cumulative hazard, and survival prediction.

`fit_psm` independently implements Weibull and exponential accelerated-failure-
time likelihoods for right-censored outcomes. It estimates the location
coefficients and, for Weibull models, the log-scale nuisance parameter jointly;
the returned covariance accounts for that nuisance parameter. Results expose
log-time predictors and survival prediction.

`fit_npsurv` independently implements an unstratified Kaplan–Meier product-limit
curve with risk, event, and censor counts at every observed time and log-scale
Greenwood confidence intervals. All three immutable result types use strict,
bounded, canonical JSON and ship with versioned schemas.

## Parity evidence

All six registered survival cases are now Python-parity cases rather than
future oracle baselines:

- Efron linear and Breslow restricted-cubic-spline Cox fits;
- Weibull linear and exponential restricted-cubic-spline parametric fits; and
- two Kaplan–Meier curves spanning tied events and delayed censoring.

Together they pass 190 exact and 446 numeric comparisons against committed
outputs from the pinned R `rms` 8.2-0 oracle. The comparisons cover designs,
coefficient and covariance names, estimates, covariance, centered or AFT linear
predictors, null and fitted log likelihoods, Weibull scale, risk-set counts,
survival uncertainty, and predicted survival curves. Maximum observed errors
are approximately `3.1e-12` for Cox, `5.2e-10` for parametric survival, and
machine precision for Kaplan–Meier.

## Boundaries and remaining Phase 5 work

This deliverable accepts positive-time right-censored outcomes and caller-
supplied finite, full-rank feature matrices. Cox strata, entry times, weights,
offsets, residuals, robust covariance, and formula-level fitting are not yet
supported. Parametric distributions other than Weibull and exponential, plus
left/interval censoring, weights, offsets, and residuals, remain deferred.
Kaplan–Meier strata, entry times, weights, and alternate estimators remain
deferred.

The deliverable does not close Phase 5 or promote any capability beyond
`experimental`. The remaining Phase 5 deliverables, survival simulations, and
independent numerical review are still required by the phase exit gate.
