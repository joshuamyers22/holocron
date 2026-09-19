# Backend-neutral plot specifications

Holocron plot specifications are immutable source-data documents. They describe
what a statistical plot means—axes, estimates, intervals, observations,
references, annotations, legend order, provenance, and accessible alternative
text—without importing a plotting backend or choosing colors, fonts, dimensions,
or output formats.

## Build a numeric specification

Use numeric line, point, and band layers for effects, calibration, validation,
survival curves, and diagnostics. Axis scales enforce their data domain:
probability values stay in `[0, 1]`, logit values stay inside `(0, 1)`, and log
values must be positive.

```python
# holocron: execute
from holocron.graphics import (
    AxisSpec,
    BandLayer,
    LineLayer,
    PlotMetadata,
    PlotSpec,
    ReferenceLine,
)

prediction = (0.1, 0.5, 0.9)
specification = PlotSpec(
    plot_id="calibration-example",
    kind="calibration",
    title="Calibration",
    alt_text=(
        "Observed probability plotted against predicted probability with an "
        "estimate line and interval band."
    ),
    x_axis=AxisSpec("Predicted probability", scale="probability"),
    y_axis=AxisSpec("Observed probability", scale="probability"),
    layers=(
        BandLayer(
            "interval",
            prediction,
            (0.04, 0.39, 0.78),
            (0.20, 0.61, 0.97),
            label="Interval",
        ),
        LineLayer(
            "estimate",
            prediction,
            (0.12, 0.48, 0.88),
            label="Estimate",
        ),
    ),
    annotations=(ReferenceLine("y", 0.5, "Half observed"),),
    metadata=(PlotMetadata("model_family", "binary-logistic"),),
    legend_order=("estimate", "interval"),
)
restored = PlotSpec.from_json(specification.to_json())

assert restored == specification
assert restored.fingerprint == specification.fingerprint
```

Line layers support linear or step interpolation; step is suitable for
Kaplan–Meier-style source data. Point layers retain observed or diagnostic
coordinates. Band layers require aligned lower and upper values and reject
crossed intervals. Reference lines and text annotations use data coordinates.

## Encode categorical summaries

`BarLayer` represents categorical values such as term statistics.
`IntervalLayer` represents named estimates with lower and upper endpoints, such
as contrasts. Their declared orientation must agree with exactly one categorical
axis. Categories are explicit ordered strings rather than backend tick positions.

Semantic roles—estimate, interval, observed, reference, comparison, and
diagnostic—let future renderers select accessible styling. They are not color or
line-width directives. A renderer must preserve the source values and meaning;
styling cannot change statistical content.

## Serialization and accessibility

`PlotSpec` writes strict canonical `holocron-plot-spec/v1` JSON and exposes its
SHA-256 fingerprint. Readers reject unknown fields, duplicate keys, non-finite
coordinates, inconsistent dimensions, wrong scale domains, excessive resource
counts, and unsupported versions. The packaged JSON Schema describes the local
shape; constructors enforce cross-field rules.

Every plot requires non-empty alternative text. The text should convey the
plot's purpose, main comparison or trend, uncertainty when present, and any
important exception. A renderer may supplement it with backend-specific
accessibility metadata but must not discard it.

## Adapt results and render SVG

Typed adapters convert supported result contracts into the same `PlotSpec`
documents. Effect adapters require the predictor grid because a
`PredictionResult` deliberately contains predictions, not the source covariate.

```python
# holocron: execute
from holocron.graphics import effect_plot_spec, render_svg
from holocron.models import PredictionResult

result = PredictionResult(
    scale="response",
    interval="mean",
    confidence_level=0.95,
    values=(1.0, 1.5, 2.2),
    standard_errors=(0.1, 0.1, 0.2),
    lower=(0.8, 1.3, 1.8),
    upper=(1.2, 1.7, 2.6),
)
effect = effect_plot_spec(
    result,
    (0.0, 1.0, 2.0),
    predictor_label="Dose",
    response_label="Expected response",
)
svg = render_svg(effect, width=800, height=520)

assert effect.kind == "effect"
assert 'role="img"' in svg
assert effect.alt_text in svg
```

The public adapter set covers effects, named contrasts, ANOVA term tests,
probability and survival validation, raw and optimism-corrected calibration,
survival curves, and current influence, robust-uncertainty, penalty-trace, and
VIF diagnostics. Adapters preserve result values and add only plot semantics;
they do not recompute statistical estimates.

`render_svg` is an owned dependency-free inline SVG backend. It renders every
v1 layer, scale, orientation, annotation, and legend contract with a fixed
semantic palette. Output includes an SVG `title`, `desc`, `role="img"`, layer
groups, and the source fingerprint; XML escaping prevents labels from becoming
markup. Width and height are bounded to 320–4096 pixels. The returned string can
be saved by the caller, but Holocron does not perform filesystem writes.

## Boundaries

The SVG renderer is deterministic and semantically tested, but it is not a
browser accessibility certification or pixel-level visual-regression claim.
There is no bitmap, HTML, interactive, custom-theme, or automatic output-file
contract. Adapter coverage is limited to the explicit result types above and
does not claim parity with R graphics methods. The `nomogram` kind remains a
reserved `PlotSpec` identity because nomograms use their own stricter
multi-axis `NomogramGeometry`; see the [nomogram guide](nomograms.md).
