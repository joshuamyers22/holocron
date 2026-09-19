# Phase 5 richer survival-prediction acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 5 deliverable: survival, hazard, mean, quantile, and curve prediction APIs
- Disposition: complete within the declared experimental envelope

## Accepted contract

`CoxResult` now returns typed survival curves, event-time quantiles, and exact
event-grid restricted means for explicit feature rows, strata, and offsets.
Quantile inputs use conventional CDF probabilities and map them to the pinned
`rms::Quantile.cph` survival-threshold convention. Unreached quantiles are
explicit `None` values. A finite restriction time is mandatory for Cox means;
step and polygon-style linear interpolation are named choices.

`ParametricSurvivalResult` now returns typed curves plus analytic Weibull or
exponential event-time quantiles and means. The operations preserve the
existing scale-stratum and offset contracts. `NonparametricSurvivalResult`
returns typed Kaplan–Meier curves, event-time quantiles, and conventional
restricted step-function means by stratum. Exact-threshold Kaplan–Meier
quantiles preserve the pinned `quantile.survfit` plateau-midpoint convention.

`SurvivalCurveResult` preserves the common time grid, one survival row and
stratum per prediction subject, and model linear predictors where defined.
Its constructor rejects inconsistent coordinates, non-finite values, and
invalid probabilities.

## Parity evidence

Three new independently implemented cases exercise Cox, Weibull, and
Kaplan–Meier curves, multiple event-time quantiles, and mean predictions. They add 77 exact and 178
field-aware numeric comparisons. Together with the first two Phase 5 slices,
all twelve survival cases pass 509 exact and 899 numeric comparisons against
the pinned R `rms` 8.2-0 oracle.

The Cox case records an important observed contract: `Mean.cph` integrates its
stored event-time grid from time zero and does not extend the last included
event interval to an arbitrary restriction point. Holocron reproduces that
behavior for `CoxResult.predict_mean`; Kaplan–Meier restricted means retain the
ordinary full step-function integral through the requested horizon.

## Boundaries

Cox mean prediction is restricted rather than an extrapolated overall mean.
Confidence intervals, curve standard errors, individual time-dependent paths,
and simultaneous prediction bands remain deferred. Parametric prediction is
limited to the currently supported Weibull and exponential families. Broader
censoring and fixed-horizon validation subsequently close in
`governance/PHASE_5_CENSORING.md` and
`governance/PHASE_5_SURVIVAL_VALIDATION.md`. The subsequent locked simulations
pass as recorded in `governance/PHASE_5_SIMULATIONS.md`; the scoped review and
exit gate close in `governance/PHASE_5_COMPLETION.md`. No capability advances
beyond `experimental`.
