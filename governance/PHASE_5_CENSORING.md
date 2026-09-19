# Phase 5 survival-censoring acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 5 deliverable: right/left/interval censoring where defined
- Disposition: complete within the selected-model envelope

## Accepted contract

`SurvivalResponse` represents positive-time exact, left-, right-, and
interval-censored observations as explicit lower and upper bounds. It rejects
empty, mismatched, nonpositive, reversed, unbounded, and all-right-censored
responses that contain no finite event bound.

`fit_psm` accepts either its established `(times, events, features)` contract or
`(SurvivalResponse, features)`. Weibull and exponential AFT likelihoods now use
the appropriate density, CDF, survivor, or interval-probability contribution
for each observation. The owned score and observed-information calculations
cover location coefficients and Weibull log-scale parameters, including scale
strata, weights, and offsets.

Cox proportional hazards and the selected Kaplan–Meier estimator retain their
right/counting-process censoring contracts. They do not silently reinterpret
left- or interval-censored observations.

## Parity evidence

Two independently implemented cases cover a mixed exact/left/right/interval
Weibull response and an exact/left/right exponential response. Together they
add 70 exact and 120 field-aware numeric comparisons against the pinned R
`rms::psm` 8.2-0 oracle. The maximum observed absolute differences are about
`2.3e-12` for Weibull and `8.1e-10` for exponential. All fourteen survival
cases now pass 579 exact and 1,019 numeric comparisons.

## Boundaries

Parametric censoring coverage remains limited to Weibull and exponential AFT
models. Censored-response residuals are not yet exposed; the existing
parametric residual API remains a right-censored contract. Interval-censored
nonparametric Turnbull curves, competing risks, additional parametric
distributions, time-dependent validation, Phase 5 simulations, specialist
review, and the Phase 5 exit gate were open at this record's acceptance. The
subsequent validation and simulation records close those technical gaps;
the subsequent Phase 5 completion record closes the scoped review and exit
gate. No capability advances beyond `experimental`.

The subsequent fixed-horizon validation record closes the declared validation
gap; see `governance/PHASE_5_SURVIVAL_VALIDATION.md`.
The simulation evidence is recorded in `governance/PHASE_5_SIMULATIONS.md`.
