# Phase 7 plot-specification acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 7 deliverable: backend-neutral plot specifications
- Disposition: complete within the declared source-data envelope

## Accepted contract

The new `holocron.graphics` namespace provides immutable `PlotSpec` documents
with semantic plot kind, title, required alternative text, numeric or
categorical axes, ordered layers, annotations, bounded string metadata, legend
visibility, and explicit legend ordering.

Numeric line, point, and interval-band layers cover continuous and step source
data. Categorical bar and estimate/interval layers cover term and contrast
summaries in either orientation. Semantic layer roles identify estimates,
intervals, observations, references, comparisons, and diagnostics without
encoding a renderer's colors, dimensions, fonts, or object types. Reference
lines and numeric text annotations are explicit data-coordinate records.

Axis and layer constructors reject non-finite values, inconsistent lengths,
crossed intervals, duplicate identifiers/categories, invalid scale domains,
categorical-orientation mismatches, and unsupported combinations. Each layer is
bounded to 100,000 points; a plot is bounded to 256 layers, 256 annotations, 128
metadata entries, and one million total layer points.

`PlotSpec` uses strict, canonical, non-executable
`holocron-plot-spec/v1` JSON with deterministic SHA-256 identity. Its schema and
serialization-manifest entry ship in wheel and source distributions. Readers
reject unknown fields, duplicate keys, malformed collections, non-finite JSON,
and unsupported versions.

## Evidence

Focused tests cover numeric line/point/band documents, vertical bars, horizontal
categorical intervals, probability/log/categorical scale semantics, reference
and text annotations, semantic metadata, legend ordering, required alternative
text, canonical/schema-valid round trips, stable fingerprints, malformed and
duplicate JSON, crossed intervals, mismatched coordinates, duplicate layer
identity, non-finite values, and orientation errors. Public-namespace tests and
generated API documentation lock the surface. Executable documentation and the
installed-artifact smoke path reconstruct a plot specification without a
rendering dependency. CI repeats the focused specification suite on the
accepted Ubuntu and macOS platform matrix.

## Boundaries and next step

No renderer, theme, palette, layout engine, graphics dependency, or output-file
contract is introduced. This slice does not transform fitted results into plot
data, test pixels, or claim parity with any R graphics method. `nomogram` is a
reserved semantic kind only; nomogram geometry remains deferred.

The next Phase 7 deliverable is effect, contrast, ANOVA, validation,
calibration, survival, and diagnostic renderers. Phase 7 and its exit gate
remain open.
