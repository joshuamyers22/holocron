# Phase 7 SVG accessibility and visual-regression acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 7 deliverable: accessibility and visual-regression checks
- Disposition: complete within the declared deterministic-SVG envelope

## Accepted contract

The plot and nomogram SVG renderers now emit non-focusable `role="img"` roots,
renderer-specific role descriptions, direct title/description elements joined
by `aria-labelledby`, labelled visible groups, schema/fingerprint metadata, and
self-contained passive content. The fixed semantic plot palette provides at
least 3:1 contrast against the owned white background. Text meets the owned
4.5:1 normal-text or 3:1 large-text thresholds. Stable dash patterns and
outlined translucent marks provide non-color cues for line-like roles and
essential boundaries.

`tools/svg_assurance.py` audits those serialized properties without adding a
runtime dependency or public package API. It rejects malformed documents,
unbounded input, missing or dangling names, duplicate IDs or layer identities,
unlabelled visible groups, missing semantic layer roles, insufficient text or
graphical contrast, active/foreign elements, event handlers, external resource
references, and document-type/entity declarations.

## Visual-regression evidence

Five committed, human-reviewable SVG fixtures cover every supported plot layer,
linear/probability/log/logit/categorical scales, linear and step interpolation,
both categorical orientations, annotations, legends, and the nomogram
renderer. `tools/check_svg_snapshots.py` reconstructs all fixtures from fixed
typed inputs, runs the accessibility audit, rejects missing or extra golden
files, and compares canonical SVG text exactly. Updating fixtures requires the
explicit `--update` operation and produces ordinary source diffs.

The focused suite covers successful plot/nomogram audits, corpus completeness,
exact regression matching, palette contrast, non-color line cues, and negative
mutations for focus behavior, accessible naming, active content, event
handlers, group labels, and text contrast. `make svg-check` is a dependency of
`make check`; the Phase 7 macOS/Ubuntu matrix includes the new suite.

## Boundaries and next step

This gate is deterministic SVG-document assurance. It is not browser-engine or
font rasterization coverage, assistive-technology testing, forced-colors or
page-level accessibility testing, WCAG certification, publication-quality
review, or R graphics parity. Exact snapshots intentionally cover owned SVG
serialization rather than platform-dependent pixels.

All six Phase 7 deliverables are now implemented within their declared
experimental envelopes. The next project-plan item is the Phase 7 completion
review and exit-gate decision; that review remains open and is not implied by
this deliverable acceptance.
