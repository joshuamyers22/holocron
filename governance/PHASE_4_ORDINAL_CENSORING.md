# Phase 4 ordinal-regression and censoring implementation record

- Implementation date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 4 exit gate: open

## Implemented contract

The Phase 4 functional deliverables are implemented behind explicit typed APIs.
`fit_orm` owns cumulative-link maximum likelihood for logistic, probit, log-log,
complementary log-log, and Cauchy families. `fit_ordinal_lrm` exposes the
multi-intercept proportional-odds subset. `OrdinalResult` carries every
threshold and slope, dense observed covariance, training probabilities,
deviance, design identity, strict canonical JSON, probability/mean/quantile/
exceedance predictions, likelihood-ratio and joint Wald tests, and numerical
diagnostics.

`CensoredResponse` supports exact, left-, right-, interval-, and mixed-censored
numeric outcomes. Its conversion implements rounded exact-grid endpoints, open
finite endpoints for one-sided censoring, Turnbull maximal intersections,
self-consistency, Kuhn–Tucker support consolidation, observation mappings, and
distinct right-tail support.

`fit_random_intercept_orm` implements one Gaussian cluster intercept with
adaptive Gauss–Hermite quadrature, declared convergence escalation, posterior
cluster modes, numerical marginal observed information, a clustered null model,
and boundary-aware variance-component mixtures. `mix_re` implements the signed
dual-scale loading `sigma1 * (1 - mix_re) + sigma2 * mix_re` and requires
within-cluster variation.

## Current evidence

- Six frozen `rms::orm` cases pass named field-aware policies: three exact
  response fits, one interval-censored fit, one random-intercept fit, and one
  dual-scale `mix_re` fit.
- Deterministic tests cover all five links, multi-intercept `lrm`, design
  identity, prediction operations, tests and diagnostics, strict schema round
  trips, left/right/interval/mixed censoring, exact-grid tail creation,
  Turnbull mappings, random-intercept and dual-scale fits, quadrature history,
  clustered-null likelihood, covariance, boundary mixtures, and structured
  failures.
- A 64-level/256-observation case exercises the many-intercept path. Exact
  outcomes use a bordered-tridiagonal Newton solve; general censoring falls back
  to dense information when nonadjacent thresholds are coupled.
- Wheel and source-distribution smoke tests import the public ordinal API, fit
  and reconstruct an ordinal model, execute Turnbull conversion, and verify the
  packaged ordinal-result schema.
- The locked Phase 4 evidence package passes 232 operating-characteristic
  replications, both declared quadrature-stability checks, 16/32/64-level
  sparsity and conditioning checks, and nine failure/stability cases. CI runs
  it on Ubuntu 24.04 x86_64 and macOS 15 arm64 and retains schema-valid reports.

## Limits and gate status

The returned covariance is dense and consumes `8 * (K - 1 + p)^2` bytes before
container overhead. The public parameter cap is 1,024. There is no claim for
larger response supports, and arbitrary censoring may require dense Newton
work. Random-effects prediction is conditional at random effect zero; marginal
prediction, multiple/crossed effects, random slopes, correlated effects,
y-dependent effects, weights, offsets, penalties, and partial proportional odds
are unsupported and fail or remain absent rather than being approximated.

The technical exit evidence is complete and passing; see
`PHASE_4_EXIT_EVIDENCE.md`. One-sided censoring retains documented exact-grid
semantics under an explicit pinned-R parity exception. Scoped independent
statistical approval is the only remaining Phase 4 exit criterion. Capability
promotion and external use remain separate gates.
