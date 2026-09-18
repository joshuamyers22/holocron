# Phase 5 risk-set and survival-quantity acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 5 deliverable: ties, strata, entry times, weights, offsets, baseline
  survival/hazard, and residuals
- Disposition: complete within the declared experimental envelope

## Accepted contract

`fit_cph` supports Efron and Breslow ties, counting-process entry times,
stratum-specific risk sets, positive case weights, and additive offsets. Its
result owns per-stratum baseline hazard increments, cumulative hazard, and
survival, predicts cumulative hazard or survival for explicit strata and
offsets, and returns martingale or deviance residuals in training-row order.

`fit_psm` supports positive case weights and additive offsets for Weibull and
exponential AFT fits. Weibull fits may estimate one scale per declared stratum;
the fixed-scale exponential distribution rejects multiple scale strata. Results
predict survival and hazard and expose response, normalized, martingale, and
deviance residuals.

`fit_npsurv` supports counting-process entry, strata, and positive frequency
weights. It reports weighted risk, event, and censor counts and a separate
Kaplan–Meier curve with log-scale Greenwood intervals for each stratum.

The three survival result documents advance to explicit v2 schemas. Writers
emit v2; strict readers continue to accept the shipped v1 documents and perform
a tested one-step in-memory migration. Both schema generations remain packaged.

## Parity evidence

Three vertical cases add a weighted, stratified counting-process Cox fit; a
weighted, offset Weibull fit with stratum-specific scales; and weighted,
stratified counting-process Kaplan–Meier curves. They contribute 242 exact and
275 field-aware numeric comparisons. Together with the first survival slice,
all nine survival cases pass 432 exact and 721 numeric comparisons against the
pinned R 8.2-0 environment.

The scale-stratified AFT oracle uses `survival::survreg`, the likelihood engine
wrapped by `rms::psm`, because the pinned `rms::psm` wrapper fails while forming
the scale-stratified design. Coefficients, covariance, stratum scales,
likelihood, hazard/survival predictions, and four residual kinds are compared
under the named `parametric-survival-risk-set-v2` policy. This is an explicit
oracle implementation detail, not a runtime dependency.

## Boundaries

Inputs remain caller-supplied finite full-rank designs with explicit row
alignment; formula evaluation and implicit missing-row deletion are unsupported.
Cox score, Schoenfeld, influence, and robust residual/covariance surfaces remain
deferred. Parametric fitting remains right-censoring only and limited to
Weibull/exponential distributions. Kaplan–Meier alternate estimators and robust
variance are unsupported; non-integer weights use the declared frequency-weight
Greenwood calculation. Mean/quantile prediction, broader censoring, and
time-dependent validation are later Phase 5 deliverables.

This record completes the second Phase 5 deliverable. It does not close Phase 5
or promote these capabilities beyond `experimental`.
