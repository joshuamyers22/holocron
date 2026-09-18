# ADR-007: Numerical backends and owned estimator solvers

- Status: accepted
- Date: 2026-09-18
- Owner: joshuamyers22

## Context

Estimator behavior includes convergence rules, rank policy, covariance
construction, and failure classification; selecting a library solely because it
can produce coefficients would not preserve that contract. Conversely, owning
every factorization would duplicate mature numerical kernels and expand the
maintenance burden. The project plan requires this decision before estimator
work proceeds.

## Decision

Holocron owns estimator control flow and public result types while using NumPy's
float64 array, factorization, and linear-solve kernels. A third-party fit object
is never the public contract. Solvers use factorizations or linear solves rather
than explicitly forming matrix inverses.

The accepted initial algorithms are:

| Estimator | Numerical path |
|---|---|
| `ols` | Full-rank QR least squares; classical covariance from triangular solves |
| Gaussian/identity `Glm` | The accepted OLS path, returned as `OlsResult` |
| Binomial/logit `Glm` | Owned IRLS matching `stats::glm.fit` initialization, relative-deviance stopping, and final working-information covariance |
| Binary `lrm` | Owned step-halved Newton iteration to a finite unpenalized maximum, with covariance from the converged observed information |

Inputs are bounded, finite, float64 matrices with an explicit intercept policy.
Rank deficiency fails before iteration. Binary response degeneracy, iteration
exhaustion, singular information, and complete or quasi-complete separation are
distinct public failures. Controls are bounded; no estimator silently changes
family, link, penalty, alias policy, or solver.

The initial `Glm` envelope is Gaussian/identity and binomial/logit only. Other
families, links, weights, offsets, penalties, sparse solvers, and non-default
dispersion rules remain unsupported. SciPy or Statsmodels may be introduced
later only behind owned contracts, after dependency review and method-specific
parity, simulation, failure, and platform evidence. Their result objects will
not become Holocron's public API.

## Consequences and verification

This keeps the runtime dependency graph at NumPy and makes the observable
algorithm explicit. It also makes Holocron responsible for convergence and
separation behavior, which requires adversarial tests and later simulation and
specialist review.

The Phase 3 core-estimator suite checks direct pinned-R parity for six OLS, three
`Glm`, and four binary `lrm` cases; schema-valid result round trips; exact design
identity during prediction; Gaussian dispatch; step exhaustion; rank
deficiency; degenerate response; separation; unsupported links; and clean
artifact installation. ADR-009 remains the authority for the accepted
cross-platform numerical envelope. This decision does not promote any estimator
beyond `experimental` or approve production use.
