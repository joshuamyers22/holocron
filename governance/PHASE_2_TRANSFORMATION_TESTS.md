# Phase 2 transformation differential/property-test acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The fifth Phase 2 deliverable is complete for the supported design envelope.
Every allowlisted main-effect transformation and every ordered pair of
restricted-interaction component kinds is exercised against a reference that is
independent of the vectorized production path. Deterministic generative tests
cover the full discrete parameter ranges declared by the public AST; continuous
input space is sampled reproducibly and includes knots, both tails, negative and
fractional values, and every declared factor level.

The suite checks observable design values together with column count and order,
nonlinear flags, term slices, intercept policy, canonical parser and JSON
reconstruction, and specification identity. It also establishes row-permutation
and batching equivariance and fail-closed handling of non-finite, boolean,
wrong-type, and undeclared values.

## Acceptance evidence

- Four hundred eighty-four deterministic generated configurations run from seed
  `20260918`: 64 trials for each of six main-effect kinds, all 36 ordered
  interaction-kind pairs, and 64 additional RCS tail trials.
- The main-effect trials exhaust polynomial degrees 2–10, linear-spline knot
  counts 1–32, restricted-cubic-spline knot counts 3–32, categorical level
  counts 2–64, and scored-ordered level counts 3–64.
- The independent scalar implementation uses Python scalar arithmetic and
  explicit indicator/product loops rather than the production NumPy block
  builders. Restricted interactions are assembled independently in left-major
  order while omitting every doubly nonlinear product.
- Fourteen frozen cases from the pinned R `rms` 8.2-0 oracle cover standalone
  RCS and complete designs. They pass 363 exact metadata comparisons and 382
  numeric comparisons under the accepted field-aware policies. Maximum absolute
  difference is `1.42e-13`; maximum relative difference is `7.76e-16`.
- Twenty-six generated invalid-value combinations verify fail-closed behavior,
  in addition to the parser, schema, resource-boundary, and interaction failures
  in the existing unit suite.
- The ordinary repository gate runs the generative suite on every supported
  Python/NumPy CI platform without Docker or network access.

## Deliberate boundaries

“Exhaustive” applies to the finite transformation-kind combinations and declared
degree/knot/level cardinalities, not every representable float or dataset.
Random-looking inputs are produced by a fixed local seed and are reproducible;
they are not statistical simulation evidence. Frozen R cases remain the
cross-language differential authority, while the scalar reference supplies
breadth between those reviewed cases.

The suite does not qualify automatic knot or level selection, missing-data
handling, offsets, strata, matrices, unrestricted or higher-order interactions,
or dataframe adapters. It does not promote experimental capabilities to
implemented status or remove the independent statistical-review gate.
