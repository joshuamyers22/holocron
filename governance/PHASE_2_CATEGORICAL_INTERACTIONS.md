# Phase 2 categorical, ordered, and restricted-interaction acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The third Phase 2 deliverable is complete within the experimental envelope.
`CategoricalTerm` records two or more explicit string or numeric levels and uses
the first as the reference. `OrderedTerm` records three or more strictly
increasing numeric levels and implements the `rms::scored` linear-score plus
nonlinear-indicator expansion. Both store the fixed `unknown_level="error"`
policy and reject missing, non-finite, mixed-type, or undeclared values.

`RestrictedInteractionTerm` is a first-class AST node matching the `rms` `%ia%`
rule: it creates two-way component products in deterministic order and omits a
product when both component columns are nonlinear. Both exact components must
also appear as main effects. Nested, self, reversed-duplicate, unrestricted,
matrix, and three-way interactions fail explicitly.

Generated columns retain all source variables and, for interactions, both
component-column identities. `DesignSpec.interactions_containing` exposes
zero-based interaction-term ownership. Formula and design serialization advance
to `holocron-formula/v2` and `holocron-design-spec/v2` for this expanded AST.

## Acceptance evidence

- Four new versioned cases produced by the pinned R `rms` 8.2-0 oracle cover
  unordered reference coding, scored ordering, linear-by-categorical products,
  and polynomial-by-spline products with doubly nonlinear terms removed.
- Independent Python evaluation passes 131 exact metadata checks and 126
  numeric checks under `formula-design-v1`; the maximum observed absolute
  difference is `1.07e-14`.
- Unit tests cover reference coding, nonlinear flags, canonical parser/JSON
  round trips, prediction reconstruction, interaction ownership, component
  order, and failures for unknown levels, missing values, invalid ordering,
  absent main effects, nesting, self-interactions, and reversed duplicates.
- The formula, oracle-case, and oracle-output schemas now formalize the new
  nodes. The structured oracle continues to evaluate no formula source.
- Compatibility entries for `catg`, `scored`, `%ia%`, and
  `interactions.containing` are linked to distinct parity cases and remain
  explicitly experimental.

## Deliberate boundaries

Level inference is not part of the formula contract; callers must make order
and reference choice explicit. Missing values fail closed because model-level
row-exclusion or imputation policy is not yet defined. Only the fixed unseen-
level error policy is accepted.

Interactions are hierarchical, two-way, and restricted. This record does not
claim unrestricted products, nested or higher-order interactions, matrices,
strata, offsets, automatic parameter selection, complete R `DesignAssign`
behavior, stable cross-version serialization, or estimator support for these
columns. The capability remains `experimental` and external distribution
remains blocked.
