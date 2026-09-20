# Phase 8 multiple-imputation adapter decision

**Decision date:** 2026-09-19  
**Scope:** second Phase 8 deliverable  
**Decision:** complete within a bounded Python-native replacement envelope

## Accepted contracts

The public `holocron.validation.process_multiple_imputation` dispatcher accepts
one homogeneous, materialized collection and selects exactly one of four owned
operations:

- `pool_imputation_models` applies Rubin's rules to two through 1,000 compatible
  `OlsResult` or `BinaryLogisticResult` objects. It reports pooled coefficients,
  within-, between-, and total covariance, standard errors, relative variance
  increase, fraction of missing information, and Barnard--Rubin small-sample
  degrees of freedom.
- `pool_imputation_validation` averages already optimism-corrected validation
  quantities by named metric and sums their actual contributing resamples.
- `pool_imputation_calibration` linearly interpolates or extrapolates already
  corrected calibration components onto one explicit common grid, averages the
  components, and reconstructs the optimism and corrected-curve identities.
- `pool_imputation_likelihood_ratio` accepts explicit per-imputation and
  stacked likelihood-ratio tables and applies the Chan--Meng adjustment used by
  the pinned `rms` source. It never infers LR tests from Holocron's Wald ANOVA.

`imputation_information_table` is the mapped `prmiInfo` replacement. It returns
a typed `TableSpec` rather than writing formatted console output.

All four persisted result types are immutable and have canonical strict JSON,
stable fingerprints, bounded versioned schemas, public reconstruction, and
wheel/sdist coverage. Pooling rejects heterogeneous families, coefficient or
design identities, malformed LR-table identities, unsupported fit types,
non-finite values, and fewer than two imputations. Validation and calibration
reject partial source executions unless `allow_partial=True` is explicit; the
source statuses and failure rates remain visible either way.

## Statistical boundary

This adapter begins after imputation-specific datasets and fits already exist.
It does not create imputations, choose an imputation model, pool transformed or
nonlinear estimands, or repeat imputation inside validation resamples. Callers
remain responsible for congenial imputation and analysis models, inclusion of
outcomes and auxiliary predictors where appropriate, missing-at-random
assumptions, diagnostics, and sensitivity analysis.

Model pooling currently supports only unpenalized OLS and binary logistic
results with classical covariance. Survival, ordinal, penalized, clustered,
robust, bootstrap, quantile, GLS, and Buckley--James fits are rejected. Pooled
predictions use the pooled coefficient vector; prediction uncertainty and
confidence intervals are not exposed. Calibration pooling preserves the
pinned implementation's common-range linear extrapolation behavior, which can
be unstable when imputation-specific grids have little overlap.

## Compatibility disposition

`processMI`, `prmiInfo`, and `processMI.fit.mult.impute` are now `mapped`. This
is not an R-parity claim: Holocron does not implement `fit.mult.impute`, R S3
objects or dispatch, stacked-data construction, implicit model refitting, or R
printing behavior. No oracle cases or tolerance profile are attached to these
mappings. Deterministic mathematical tests cover Rubin components, the
Chan--Meng formulas, interpolation identities, strict round trips, schemas,
dispatcher boundaries, and artifact installation.

The machine-readable authority is `compatibility/rms-8.2.0.yaml`. This decision
completed only the second Phase 8 deliverable. Full namespace disposition and
retained-profile performance work and migration/deprecation policy were
completed by subsequent decisions. The accountable completion review in
`PHASE_8_COMPLETION.md` subsequently passed the private-development exit gate.
