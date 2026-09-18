# Phase 3 result-operations acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The second Phase 3 deliverable is complete within the experimental envelope.
`holocron.models` exposes typed `covariance`, `likelihood`, `residuals`,
`predict`, `summarize`, `anova`, and `contrast` operations for the accepted OLS,
Gaussian/identity `Glm`, binomial/logit `Glm`, and binary unpenalized `lrm`
results.

The operations are field-aware. Covariance selection and contrasts use stable
coefficient names. Predictions retain fitted-design identity when passed a
`DesignMatrix`. ANOVA derives its coefficient blocks from a matching
`DesignSpec` or requires explicit, non-overlapping named groups. Binary
residuals require the original response because it is intentionally absent from
the persisted fit. Each unsupported model/operation combination fails closed.

The inference contract uses Student t reference distributions for OLS and
binomial `Glm`, normal reference distributions for binary `lrm`, F term tests
for OLS, and chi-square Wald term tests for binary models. OLS supports mean and
individual prediction intervals; binary models support mean intervals on the
linear and probability scales.

## Acceptance evidence

- Three vertical post-estimation cases exercise OLS, binomial `Glm`, and binary
  `lrm` through the pinned R 8.2-0 oracle. They pass 93 exact and 231 numeric
  comparisons under `postfit-inference-v1`; the largest absolute difference is
  `7.73070496506989e-12`.
- The R cases call public `vcov`, `logLik`, `residuals`, `predict`, `anova`, and
  `contrast` behavior and normalize the results into the versioned oracle
  output schema. Independent Python tests use the public Holocron API and the
  shared field-aware comparator.
- Unit tests cover response- and linear-scale prediction, OLS mean and
  individual uncertainty, all supported residual types, coefficient inference,
  likelihood metadata, single and multi-column term tests, named contrasts,
  design-identity checks, and fail-closed invalid inputs.
- Wheel and source-distribution smoke tests invoke the installed post-estimation
  API outside the checkout. The cross-platform CI matrix runs the direct
  estimator and post-estimation suites on both accepted numerical platforms.

## Deliberate boundaries

The new compatibility entries remain `experimental`. `summarize` is explicitly
coefficient-level and does not claim parity with adjusted-effect
`summary.rms`. ANOVA is a declared-term joint Wald interface, not the complete
`anova.rms` partitioning surface. Contrasts are single linear coefficient
combinations; simultaneous, nonlinear, grid-based, and expression-driven
contrasts remain absent. Derived operation records are runtime values and do
not add a persistence format.

Penalties and alternative covariance are now accepted separately in the
[regularization/covariance record](PHASE_3_REGULARIZATION_COVARIANCE.md).
Simulation and numerical edge-case evidence is now accepted in the
[simulation/edge record](PHASE_3_SIMULATION_EDGES.md). The complete getting-
started workflow is now accepted in the
[workflow record](PHASE_3_GETTING_STARTED.md). Specialist review, the Phase 3
exit gate, capability promotion beyond experimental, consequential use, and
external distribution remain open.
