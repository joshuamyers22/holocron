# Phase 2 R design-specification migration-guide acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The sixth and final Phase 2 deliverable is complete. The R migration guide maps
the supported `rms` design concepts to explicit Holocron distribution, formula,
design-matrix, serialization, fitting, and prediction contracts. Migration is
defined as preservation and verification of design semantics, not mechanical R
syntax translation or loading an R object.

The guide requires users to freeze R-side versions, rows, types, levels,
references, adjustment metadata, transformation parameters, interactions,
intercept policy, and model-matrix output before translation. It documents exact
field mappings, Python indexing differences, reconstruction identity, the
accepted numerical comparison policy, canonical normalization of R column
semantics, and fail-closed stop conditions.

## Acceptance evidence

- The main migration example executes offline in the strict documentation gate
  and covers explicit distribution metadata, RCS and categorical compilation,
  matrix inspection, response extraction, matrix-aware OLS fitting, new-data
  reconstruction, fingerprint retention, and prediction.
- The concept map covers `datadist`, ambient options, every supported main
  effect, restricted interactions, intercepts, `Design`, the narrow
  `DesignAssign` replacement, interaction lookup, OLS, and prediction.
- The matrix-verification procedure distinguishes exact metadata from the
  accepted `1e-12` absolute/relative float64 transformation tolerance and points
  to the 14 pinned-R design/RCS cases and exhaustive property suite.
- The guide links the authoritative compatibility inventory, limitations,
  numerical envelope, design/data/serialization ADRs, and related task guides.
- Stop conditions explicitly prevent migration claims for automatic parameters,
  general R evaluation, implicit missing-data handling, unsupported design
  constructs, incomplete R helpers, inference operations, or unimplemented model
  families.

## Deliberate boundaries

The guide does not automate R inspection, parse `.rds` files, translate arbitrary
formulas, or certify a user's analysis. It covers the current private
experimental envelope and does not promote a capability, approve external
distribution, or close the Phase 2 exit gate. Exit-gate review remains a separate
project-plan action requiring the complete Tier A design evidence to be assessed
together.
