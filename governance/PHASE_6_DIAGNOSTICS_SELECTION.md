# Phase 6 diagnostics-and-selection acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 6 deliverable: influence, robustness, VIF, penalty tracing, and supported selection helpers
- Disposition: complete within the declared OLS/binary envelope

## Accepted contract

`influence_diagnostics` accepts current unpenalized OLS and binary-logistic
results with their original response and realized design. It returns bounded,
typed observation records containing leverage, standardized residual, Cook
distance, coefficient change, DFBETAs, and a declared heuristic flag. OLS
coefficient changes use the exact case-deletion identity; binary-logistic
changes are one-step approximations at the fitted model.

`variance_inflation_factors` reports covariance-correlation VIFs for every
non-intercept coefficient. `robustness_diagnostics` wraps the already accepted
uncorrected cluster-sandwich covariance and pairs model-based and robust
standard errors with their ratio.

`trace_penalty` refits a caller-declared grid of 1–1,000 strictly increasing,
non-negative scalar penalties for OLS or binary `lrm`. Each point reports the
coefficients, fitted effective degrees of freedom, constant-free deviance, AIC,
and BIC. Selection minimizes the requested information criterion with a lower-
penalty tie break. It is not an adaptive optimizer.

`backward_select` accepts OLS or binary-logistic fits and a caller-declared
partition of all slope coefficients into at most 256 terms. It evaluates joint
Wald tests, removes the largest eligible p-value above the significance level,
and freshly refits after every removal. Protected terms and a minimum retained
term count constrain the path. The helper never infers hierarchy.

## Evidence

Focused tests verify the OLS case-deletion coefficient identity, leverage-trace
identities for OLS and binary logistic models, finite binary influence, the
two-predictor VIF definition, exact reuse of accepted robust covariance,
bounded OLS and binary-lrm penalty paths, information-criterion selection,
fresh-refit removal of a declared noise term, protected terms, and fail-closed
invalid grids, partitions, responses, and model families. The executable guide
and installed-artifact smoke path cover all five public operations.

No compatibility-manifest status advances with this deliverable. R `vif`,
`which.influence`, `pentrace`, and `fastbw` remain deferred because no pinned
cross-language cases or method-specific parity evidence were added. The public
functions are explicitly owned Python contracts.

## Boundaries and next step

Influence flags are heuristics and do not authorize deletion. Binary influence
is not an exact deleted-case refit. VIF does not diagnose all forms of
misspecification. Robust covariance does not repair a wrong model. Penalized
OLS effective degrees of freedom follow the accepted variance contract and are
not promised to be monotone. Backward selection does not provide valid post-
selection inference and must itself be repeated inside validation when it is
part of the learned procedure.

Ordinal, survival, and penalized-fit influence; exact binary case deletion;
dense or adaptive penalty search; hierarchy inference; and penalized selection
remain deferred. Failure-rate and partial-resample reporting is the final Phase
6 deliverable. Phase 6 and its exit gate remain open.
