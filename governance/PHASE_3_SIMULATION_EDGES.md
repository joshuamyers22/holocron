# Phase 3 simulation and numerical-edge acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Evaluated implementation: `822cccc2e1dcb8eb337dda0c324fca3ea9ee6800`

## Accepted contract

The fourth Phase 3 deliverable is complete within the experimental envelope.
The locked `phase-3-core-estimators-v1` plan defines seven seeded studies, 2,620
outer replications, their data-generating parameters, and metric-specific
acceptance intervals. The runner reads those thresholds, records aggregate
metrics and failed replication IDs, hashes canonical replication detail, and
emits a schema-valid environment- and revision-bound report.

The separate `phase-3-core-numerical-edges-v1` corpus declares 16 data-driven
cases. It covers rank loss, exhausted residual DF, near conditioning limits,
invalid binary response, complete separation, iteration exhaustion, penalized
separation recovery, rms-compatible penalized-OLS DF behavior, covariance input
identity, valid clustered covariance, failed bootstrap refits, and deterministic
bootstrap schedules. Outcomes are exact exception classes or named invariants.

## Acceptance evidence

- All seven simulations passed with no failed outer replication. OLS slope bias
  was `0.0008502`, RMSE `0.11482`, coverage `0.950`, and null type-I error
  `0.052`.
- Binary Glm and lrm produced maximum mean-coefficient disagreement
  `2.69e-08`, slope coverage `0.930`, null type-I error `0.0375`, calibration-
  intercept magnitude `0.01472`, calibration-slope error `0.05567`, mean Brier
  score `0.22287`, and mean AUC `0.68034`.
- Cluster-robust coverage was `0.9175`, compared with naive coverage `0.7125`;
  the robust mean-SE to empirical-SD ratio was `0.94214`. Bootstrap variance
  ratio was `1.06751` with centering bias `0.0009995`.
- Under correlated predictors, penalized-to-ordinary coefficient MSE ratio was
  `0.06412` and prediction MSE ratio was `0.69786`.
- All 16 numerical edge cases passed across nine categories. The corpus exposed
  and closed a binomial Glm separation path that previously reached non-finite
  IRLS arithmetic before emitting the structured separation error.
- The clean source-bound reports have SHA-256
  `2813e77607ede633185b0a69eb6744605a942a53b31bbe6ed56a67cda60de62b`
  (simulation) and
  `65cc9d00e5a8412a28c83753cfd9f383cb08d4b0b43a2ece5b65e0225ffe44dc`
  (edges). CI regenerates and retains both reports and repeats the studies on
  the accepted macOS arm64 and Ubuntu x86_64 matrix.

## Deliberate boundaries

The studies use synthetic, correctly specified data-generating processes and
are sized as deterministic engineering gates, not definitive methodological
evaluations. They do not establish external validity, robustness to missingness
or misspecification, multiplicity control, subgroup performance, clinical
utility, or support beyond the accepted estimator and covariance envelope.

The committed report is a clean macOS arm64 result. Platform CI artifacts are
required runtime evidence but are not promoted to immutable historical
cross-platform calibration records by this acceptance. The getting-started
workflow is now accepted separately in the
[workflow record](PHASE_3_GETTING_STARTED.md). Independent statistical review,
the Phase 3 exit gate, consequential use, and external distribution remain open.
