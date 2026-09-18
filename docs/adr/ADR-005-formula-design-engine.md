# ADR-005: Owned formula and design engine

- Status: accepted
- Date: 2026-09-17
- Owner: joshuamyers22

## Context

The design system must retain predictor identity, transformations, interactions,
generated-column order, and learned parameters for later prediction. Delegating
that contract to evaluated Python expressions or an opaque third-party formula
object would weaken serialization, security, and compatibility guarantees.

## Decision

Holocron will own an immutable, typed formula AST and resulting design metadata.
Only registered terms and transformations may appear in the AST; neither Python
`eval` nor arbitrary callbacks are part of the formula contract. Parsing, term
resolution, metadata learning, matrix construction, and numerical estimation
remain separate stages.

Third-party parsers may be evaluated later as syntax front ends, but they must
lower into the owned AST and pass the same validation and parity cases. Learned
metadata—including distribution summaries, factor levels, knots, encodings, and
generated-column identities—must be stored with the fitted design. Post-fit
operations may not depend on mutable process-wide configuration.

`DataDistribution` was the first design-domain object under this decision.
`Formula` and `DesignSpec` now implement explicit numeric and factor terms plus
hierarchical two-way restricted interactions with fixed resource limits and
reconstructible generated-column metadata.

## Consequences and verification

The initial AST vocabulary and resource limits are accepted in the
[formula-design record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_2_FORMULA_DESIGN.md).
Unsupported expressions fail with a typed error. Categorical nodes and
restricted interactions extend the same owned representation with explicit
level, reference, unseen-value, hierarchy, and nonlinear-product rules, as
accepted in the
[categorical/interactions record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_2_CATEGORICAL_INTERACTIONS.md).
