# Phase 2 formula AST and core transformations acceptance record

- Acceptance date: 2026-09-17
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The second Phase 2 deliverable is complete within the experimental envelope.
`holocron.formula.Formula` is an immutable, typed additive AST with variable,
identity, raw-polynomial, linear-spline, and explicit-knot restricted-cubic-
spline nodes. Its parser accepts only the documented grammar, supports quoted
adversarial column names, and performs no Python or R evaluation.

`holocron.design.DesignSpec` compiles that AST into stable generated-column
identities, nonlinear flags, and term slices. It snapshots named finite numeric
iterables and deterministically reconstructs the same design for new data.
Formula and design metadata use canonical JSON and SHA-256 fingerprints.

Resource limits are part of the contract: 4,096 formula characters, 256
characters per name, 64 additive terms, 256 generated columns, polynomial
degree 2 through 10, and at most 32 explicit knots per spline term.

## Acceptance evidence

- Four versioned cases produced by the pinned R `rms` 8.2-0 oracle cover
  identity terms with adversarial names, raw polynomials, linear splines, and an
  additive identity/restricted-cubic-spline design.
- Independent Python evaluation passes 84 exact metadata checks and 80 numeric
  checks under `formula-design-v1`; maximum observed absolute error is
  `5.33e-15`.
- Unit tests cover every AST node, canonical expression and JSON round trips,
  reconstruction on new data, caller-input copying, generated-column metadata,
  malformed documents, missing/mismatched/non-finite data, overflow, and parser
  injection/resource-limit failures.
- `schemas/formula.schema.json` formalizes the portable AST. Repository checks
  validate it along with cross-document case/output links.
- The R oracle accepts structured terms and never evaluates the formula string.

## Deliberate boundaries

The accepted v1 grammar was additive and numeric. Categorical/ordered encoding
and restricted interactions are now accepted separately in the
[third-deliverable record](PHASE_2_CATEGORICAL_INTERACTIONS.md). Offsets,
strata, matrices, custom transformations, automatic knot selection, model-level
missing-data handling, and dataframe adapters remain later Phase 2 work.
Polynomial terms are raw powers, matching `rms::pol`; orthogonal
polynomials are not substituted. An intercept is formula metadata and is not a
column in `DesignMatrix`. The versioned JSON forms support deterministic
reconstruction now, but their cross-version stability policy remains part of the
later stable design/result schema deliverable.

The capability remains `experimental`. This record does not promote the full R
`Design` or `DesignAssign` contracts, approve arbitrary formula syntax, or
authorize external distribution.
