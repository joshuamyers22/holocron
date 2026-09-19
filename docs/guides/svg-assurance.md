# SVG accessibility and visual assurance

Holocron's supported SVG renderers produce deterministic, self-contained
documents for plot specifications and nomograms. The development gate combines
a structural accessibility audit with exact golden SVG comparisons:

```sh
make svg-check
```

The audit verifies properties Holocron can own from serialized SVG: one
nonempty title and description, valid `aria-labelledby` references, image and
role-description semantics, non-focusable roots, labelled visible groups,
unique semantic plot-layer identities, schema/fingerprint metadata, bounded
dimensions, explicit text color, and minimum contrast against the renderer's
white background. It also rejects scripts, foreign content, resource links,
event handlers, document types, and entity declarations.

Plot colors use at least 3:1 contrast against white for essential graphical
marks. Text uses at least 4.5:1 contrast, except large text where the threshold
is 3:1. Line-like semantic roles also have stable dash patterns so comparison,
reference, and diagnostic series do not rely only on color. Interval bands and
bars retain a contrasting outline when their translucent fill is used.

## Golden renderer coverage

The committed fixtures in `tests/snapshots/svg/` are ordinary SVG files that
can be opened and reviewed directly. The corpus covers:

| Fixture | Renderer contract exercised |
|---|---|
| `plot-numeric.svg` | lines, step lines, points, bands, references, text annotations, probability scale, captions, and legends |
| `plot-transformed.svg` | logit and logarithmic numeric axes |
| `plot-categorical-horizontal.svg` | horizontal bars and categorical intervals |
| `plot-categorical-vertical.svg` | vertical bars and categorical intervals |
| `nomogram.svg` | predictor, points, total-points, and outcome scales |

Every quality-gate run renders these cases again, audits the generated SVGs,
rejects missing or unexpected fixture files, and requires exact serialized
output. A renderer change therefore produces a human-reviewable SVG diff rather
than an opaque binary or platform-dependent screenshot.

After intentionally changing renderer output, inspect the old and new files in
a browser or SVG viewer, then refresh the corpus explicitly:

```sh
uv run --frozen python -m tools.check_svg_snapshots --update
make svg-check
```

Snapshot updates are review decisions, not an automatic fix for a failed gate.

## Boundaries

These checks establish deterministic document semantics and canonical visual
output for Holocron's dependency-free renderer. They do not test browser layout
engines, fonts, zoom behavior, keyboard interaction in a surrounding page,
screen-reader announcements, forced-colors modes, or rasterized pixels. They
are not WCAG certification, assistive-technology certification, publication-
quality review, or R graphics parity. Consumers embedding SVG in HTML remain
responsible for page-level accessibility and applied interpretation.
