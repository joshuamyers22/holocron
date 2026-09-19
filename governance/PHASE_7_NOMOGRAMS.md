# Phase 7 nomogram acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 7 deliverable: nomogram geometry and rendering
- Disposition: complete within the declared additive OLS/logit envelope

## Accepted contract

`build_nomogram` converts an identity-bound full-rank OLS or binary-logistic
result, its exact `DesignSpec`, and explicit `DataDistribution` into immutable
backend-neutral `NomogramGeometry`. Model/design fingerprints and coefficient
names must agree. Continuous grids use declared display ranges; discrete,
ordered, and categorical grids use declared values. Other predictors remain at
their explicit adjustment values.

Predictor effects are measured on the model linear-predictor scale. The largest
axis spans the configured maximum points, every other axis shares that scale,
and maximum total points equals the sum of axis maxima. Geometry preserves the
minimum linear predictor and exact linear-predictor units per point. OLS outcome
ticks use the identity response; binary-logistic ticks use the logistic
response. Constructors and readers verify these identities.

Interactions fail explicitly because one unconditional predictor axis would
not preserve a conditional effect. The builder also rejects missing metadata,
wrong design identity, coefficient mismatch, nonvarying models, and invalid
tick/resource settings.

Geometry uses strict canonical non-executable
`holocron-nomogram-geometry/v1` JSON with stable SHA-256 identity. The schema
ships in wheel and source distributions. The dependency-free renderer consumes
only geometry and emits bounded deterministic inline SVG with linked title and
description, semantic scale groups, safe XML text, and source identity.

## Evidence

Focused tests prove prediction reconstruction over the Cartesian product of a
nonlinear numeric axis and categorical axis, exercise binary probability
outcomes, verify strict/schema-valid round trips and identity rejection, and
cover interaction/design mismatch failures. SVG tests cover deterministic
output, accessibility metadata, text escaping, total-points rendering, and
dimension bounds. Public API, CI, executable documentation, strict typing,
lint, and installed wheel/sdist smoke paths include the new contract.

## Boundaries and next step

No R `nomogram` or `plot.nomogram` compatibility status changes in this slice.
Ordinal/survival geometry, confidence limits, custom response transforms,
multiple outcomes, manual axis overrides, and conditional interaction axes
remain unsupported. SVG semantics are not pixel-baseline visual regression or
browser accessibility certification.

The next Phase 7 deliverable is structured tables and LaTeX output. Galleries,
broader accessibility evidence, visual regression, and the Phase 7 exit gate
remain open.
