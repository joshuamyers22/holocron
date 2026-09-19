# Phase 6 model-validation acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 6 deliverable: model-specific `validate` and `calibrate` behavior
- Disposition: complete within the declared fixed-design OLS/binary envelope

## Accepted contract

`validate_model` accepts a current unpenalized OLS, binomial `Glm`, or binary
`lrm` result together with its development response, realized numeric design,
and an exact `ResamplePlan`. It:

- checks observation, feature, optional design-fingerprint, and optional row
  identity against the fitted result and plan;
- reconstructs the estimator family, intercept choice, feature names, and
  supported iterative controls for a fresh fit inside every analysis sample;
- evaluates that fit separately on the analysis and assessment rows;
- reports OLS R-squared, mean squared error, and linear calibration intercept
  and slope, or binary Somers' Dxy, Brier score, and logistic calibration
  intercept and slope; and
- retains every pair under the plan fingerprint and preserves the resampling
  engine's raise-or-record and complete/partial/failed semantics.

`calibrate_model` performs the same fresh model refits and retains family-
specific parametric recalibration intercepts and slopes for each analysis and
assessment sample. Its apparent curve is evaluated on an explicit or bounded
generated grid. OLS uses the response scale; binary logistic regression uses
the probability scale with recalibration performed on predicted log odds.

Neither result averages the retained pairs or labels a quantity optimism-
corrected. This prevents a later aggregation policy from being silently baked
into the model-specific refit contract.

## Evidence

Focused tests cover both supported families, apparent identity calibration,
family-specific indices and curves, exact plan binding, retained split pairs,
row-identity rejection, malformed grids, unsupported ordinal dispatch, fresh
fit failures caused by a rank-deficient analysis sample, and both strict and
recorded failure policies. Public API and generated documentation checks cover
the exported immutable result types and functions.

## Boundaries and next step

The feature matrix is a fixed realized design. This API does not claim that a
formula transformation, knot or level choice, imputation, selection step, or
other preprocessing learned outside the function was rebuilt per split. Such
procedures must use `run_resample_plan` and perform every learned step inside
its callback.

Penalized, ordinal, random-effects, Cox, and parametric-survival results are not
accepted by this slice. Smooth/nonparametric calibration,
R `validate.*`/`calibrate.*` compatibility, and serialized model-validation
results also remain deferred. Compatibility-manifest entries therefore do not
advance on this owned Python contract alone. The separate aggregation contract
is recorded in `PHASE_6_OPTIMISM_CORRECTION.md`.

The broader probability and survival validation-metric layer is recorded
separately in `PHASE_6_VALIDATION_METRICS.md`; optimism correction is recorded
in `PHASE_6_OPTIMISM_CORRECTION.md`. Phase 6 and its exit gate remain open.
