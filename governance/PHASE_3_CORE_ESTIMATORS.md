# Phase 3 core-estimator acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The first Phase 3 deliverable is complete within the experimental envelope.
`holocron.models` exposes owned `fit_ols`, `fit_glm`, and `fit_lrm` entry points.
OLS remains the classical full-rank QR estimator accepted in Phase 1.
`fit_glm` supports Gaussian/identity and binomial/logit only; its Gaussian path
returns `OlsResult`, while its binary path returns `BinaryLogisticResult`.
`fit_lrm` implements the unpenalized binary subset of `rms::lrm` and returns the
same owned binary result type.

The binary result carries coefficients, covariance, training linear predictors
and probabilities, null and residual deviance, iteration count, rank,
dimensions, intercept policy, and design identity. It supports linear-predictor
and probability prediction, plus strict canonical JSON under
`holocron-binary-logistic-result/v1`.

ADR-007 fixes the backend policy: Holocron owns estimator control flow and
results while using NumPy's float64 factorization and solve kernels. Binomial
`Glm` matches R `glm.fit` initialization, deviance stopping, and working-
information covariance. Binary `lrm` uses step-halved Newton iteration and the
converged information matrix. These are separate numerical contracts.

## Acceptance evidence

- Six existing OLS cases, three direct `rms::Glm` cases, and four direct binary
  `rms::lrm` cases pass 287 exact and 1,095 numeric comparisons against the
  pinned R 8.2-0 oracle. The largest absolute difference is
  `6.048139766789973e-11`, within the approved field-aware profiles.
- The three new `Glm` fixtures cover Gaussian/identity, linear binomial/logit,
  and explicit-knot spline binomial/logit behavior. All four former `lrm`
  baselines are now independently implemented Python parity cases.
- Tests cover both dispatch paths, direct coefficient/covariance parity, result
  schema and canonical round trips, design-identity prediction, malformed
  persistence, invalid or single-class outcomes, rank deficiency, iteration
  exhaustion, separation, and unsupported links.
- The rebuilt network-isolated oracle retains the same pinned R, `rms`, Hmisc,
  repository, platform, and source-manifest identities. Its image identity was
  refreshed solely to add the versioned `Glm` protocol operation.
- The public schema is included in wheel and source distributions; installation
  smoke tests exercise a serialized binary fit outside the checkout.

## Deliberate boundaries

Both capabilities remain `experimental`. `Glm` does not yet support other
families or links, weights, offsets, quasi-likelihood, custom dispersion,
penalties, alias handling, or formula-level fitting. Binary `lrm` does not yet
support ordinal outcomes, weights, offsets, or its broader method surface.
Diagonal binary-lrm penalties are accepted through the separate
`fit_penalized_lrm` API; `lrm.fit` remains deferred.

The broader covariance, likelihood, residual, prediction, coefficient-summary,
ANOVA, and contrast operations are now accepted in the separate
[result-operations record](PHASE_3_RESULT_OPERATIONS.md). The diagonal-penalty
and alternative-covariance surface is accepted in the
[regularization/covariance record](PHASE_3_REGULARIZATION_COVARIANCE.md).
Simulation and numerical edge-case evidence, specialist review, the Phase 3
exit gate, capability promotion beyond experimental, consequential use, and
external distribution all remain open.
