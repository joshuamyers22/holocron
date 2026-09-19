# Phase 7 adapters and renderer acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 7 deliverable: model-to-plot adapters and owned SVG renderer
- Disposition: complete within the declared result and SVG envelope

## Accepted contract

`holocron.graphics` provides typed adapters for effect predictions, named
contrasts, ANOVA term tests, probability and survival validation, apparent and
optimism-corrected calibration, survival curves, and current influence,
robustness, penalty-trace, and VIF diagnostic results. Every adapter produces a
backend-neutral `PlotSpec`; it does not recompute estimates. Required context
absent from a result contract—most notably an effect predictor grid—is an
explicit argument and is length/domain checked.

The dependency-free `render_svg` backend consumes only `PlotSpec`. It supports
linear, probability, log, logit, and categorical axes; line and step paths;
points, bands, vertical/horizontal bars and intervals; reference lines, text,
captions, and legends. A fixed role-based palette separates statistical meaning
from caller styling. Dimensions are bounded to 320–4096 pixels.

SVG output is deterministic, script-free, and contains no external resources
or event handlers. It carries `role="img"`, linked `title` and `desc` elements,
semantic layer groups, and the source specification fingerprint. XML generation
escapes caller text.

## Evidence

Focused tests cover all seven requested adapter families, explicit-context
failure, grouped probability and right-censored survival calibration,
multi-curve step survival output, influence highlighting, VIF output, numeric
bands, categorical intervals and bars, log scales, reference annotations,
determinism, text escaping, accessibility metadata, and dimension limits. The
public namespace, executable documentation, CI platform matrix, strict typing,
lint, and wheel/sdist installed-artifact smoke paths include the new surface.

## Boundaries and next step

Semantic checks are not browser/assistive-technology certification, and no
pixel-baseline visual-regression evidence is claimed yet. The renderer returns
inline SVG only; it does not write files or provide bitmap, HTML, interactive,
or custom-theme output. Adapter support does not imply parity with R plotting
methods, and unsupported result types fail explicitly.

The next Phase 7 deliverable is nomogram geometry and rendering. Structured
tables/LaTeX, task-oriented galleries, broader accessibility testing, visual
regression, and the Phase 7 exit gate remain open.
