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

- All three frozen exact-response `rms::orm` cases pass the field-aware
  `ordinal-model-v1` policy for logistic, probit, and complementary log-log
  models, including a restricted-cubic-spline design.
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

## Limits and gate status

The returned covariance is dense and consumes `8 * (K - 1 + p)^2` bytes before
container overhead. The public parameter cap is 1,024. There is no claim for
larger response supports, and arbitrary censoring may require dense Newton
work. Random-effects prediction is conditional at random effect zero; marginal
prediction, multiple/crossed effects, random slopes, correlated effects,
y-dependent effects, weights, offsets, penalties, and partial proportional odds
are unsupported and fail or remain absent rather than being approximated.

This record completes the implementation deliverable, not the Phase 4 exit
gate. Censored and clustered oracle cases, operating-characteristic simulation,
quadrature and sparsity benchmarks on both accepted platforms, tolerance
calibration, and scoped independent statistical approval remain required before
Phase 4 can close or those capabilities can advance beyond experimental.
