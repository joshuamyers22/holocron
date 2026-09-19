# Nomogram geometry and SVG rendering

Holocron nomograms separate statistical geometry from rendering. The builder
converts a supported additive fitted model, its exact `DesignSpec`, and explicit
`DataDistribution` metadata into immutable `NomogramGeometry`. The SVG renderer
then consumes only that geometry.

## Build an additive nomogram

The current envelope supports full-rank OLS and binary-logistic models fitted
from a `DesignMatrix`. Continuous axes use the metadata display range;
discrete, ordered, and categorical axes retain their declared values. Every
other predictor stays at its explicit adjustment while one axis is evaluated.

```python
# holocron: execute
from holocron.design import DataDistribution, DesignSpec
from holocron.graphics import NomogramGeometry, build_nomogram, render_nomogram_svg
from holocron.models import fit_ols

x = tuple(float(index) for index in range(8))
group = tuple("A" if index % 2 == 0 else "B" for index in range(8))
y = tuple(
    1.0 + value + (1.0 if level == "B" else 0.0)
    for value, level in zip(x, group, strict=True)
)

spec = DesignSpec.from_formula('y ~ x + catg(group, ["A", "B"])')
distribution = DataDistribution.from_data(
    {"x": x, "group": group},
    levels={"group": ("A", "B")},
    labels={"x": "Dose", "group": "Treatment group"},
    units={"x": "mg"},
)
model = fit_ols(y, spec.transform({"x": x, "group": group}))
nomogram = build_nomogram(model, spec, distribution)
restored = NomogramGeometry.from_json(nomogram.to_json())
svg = render_nomogram_svg(restored)

assert restored == nomogram
assert nomogram.axes[0].label == "Dose"
assert 'role="img"' in svg
assert "Total points" in svg
```

The largest predictor effect spans the requested points maximum, 100 by
default. All other axes share that scale. Each tick retains its original value,
display label, model linear predictor with other variables adjusted, and points
contribution. Geometry also retains the design and distribution fingerprints.

For total points `p`, the exact mapping is:

```text
linear predictor = minimum linear predictor + p × linear-predictor units per point
```

OLS exposes that value directly. Binary logistic geometry applies the logistic
response transformation. Outcome axes store both quantities and validate the
identity during construction and deserialization.

## Rendering and accessibility

`render_nomogram_svg` produces bounded deterministic inline SVG with a shared
points axis, one row per predictor, total points, and the response axis. It
includes linked SVG `title` and `desc` elements, semantic groups for every
scale, the geometry fingerprint, and safely escaped labels. The caller owns any
filesystem write or surrounding HTML.

## Boundaries

Interactions fail explicitly. A single unconditional axis would misrepresent
an effect whose points depend on another predictor; conditional interaction
axes require a later contract. Current geometry also excludes ordinal and
survival models, confidence intervals, user-specified response transforms,
multiple response axes, variable omission, and manual tick overrides.

The Python geometry and renderer are experimental and do not claim parity with
R `nomogram` or `plot.nomogram`. Semantic SVG tests are not pixel-level visual
regression or browser/assistive-technology certification.
