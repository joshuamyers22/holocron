# Phase 3 regularization and covariance acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The third Phase 3 deliverable is complete within the experimental envelope.
`fit_penalized_ols` and `fit_penalized_lrm` implement explicit diagonal
quadratic slope penalties while retaining coefficient names and design
identity. Penalized OLS exposes the `simple` and `sandwich` penalty-variance
contracts; penalized binary `lrm` uses inverse penalized information. Both
report the applied penalty and effective degrees of freedom.

`robust_covariance` implements the uncorrected Huber cluster sandwich for the
accepted unpenalized OLS, binomial `Glm`, and binary `lrm` results.
`bootstrap_covariance` refits iid row resamples and returns sample covariance,
replicate count, seed, and the bootstrap coefficient mean. It accepts either a
NumPy seed or a bounded explicit resample schedule. Failed resamples raise
instead of being silently omitted.

## Acceptance evidence

- Three vertical OLS, binomial `Glm`, and binary `lrm` cases pass 42 exact and
  126 numeric comparisons against the pinned R 8.2-0 oracle. The largest
  absolute difference is `1.0989673171479808e-08`, within the named field-aware
  profiles.
- The R paths directly invoke penalized `rms::ols`, penalized binary `rms::lrm`,
  and `rms::robcov`. Bootstrap covariance is independently reconstructed in R
  from the exact declared schedules used by Python, avoiding an invalid claim
  that R and NumPy seeds produce the same samples.
- Unit tests independently verify the penalized normal equations, both OLS
  variance choices, finite penalized separation handling, the clustered
  sandwich equation, declared-schedule sample covariance, seeded
  reproducibility, design identity, and fail-closed invalid inputs.
- The installed-artifact smoke path exercises penalization and both alternative
  covariance APIs. The accepted platform matrix runs the direct differential
  suite on macOS arm64 and Ubuntu x86_64.

## Deliberate boundaries

The capabilities remain `experimental`. Only diagonal slope penalties are
accepted; arbitrary dense or categorical penalty matrices and automatic
`pentrace` remain deferred. Penalized `Glm`, weights, offsets, robust covariance
of penalized fits, Efron OLS covariance, finite-sample corrections, cluster or
group-stratified bootstrap, failed-replicate skipping, stored replicate
coefficients, and bootstrap confidence intervals are absent.

Simulation reports and the numerical edge-case corpus are now accepted in the
[simulation/edge record](PHASE_3_SIMULATION_EDGES.md). The complete getting-
started workflow, specialist review, the Phase 3 exit gate, consequential use,
and external distribution remain open.
