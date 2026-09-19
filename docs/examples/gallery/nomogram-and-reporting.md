# Gallery: additive nomogram and coefficient reporting

## Goal

Create a points-based nomogram and a coefficient table from the same
identity-bound additive model, preserving the source geometry and raw numeric
results before rendering.

## Workflow

```python
# holocron: execute
from holocron.design import DataDistribution, DesignSpec
from holocron.graphics import build_nomogram, render_nomogram_svg
from holocron.models import fit_ols, summarize
from holocron.reporting import model_summary_table, render_latex

dose = tuple(float(index) for index in range(12))
group = tuple("A" if index % 2 == 0 else "B" for index in range(12))
y = tuple(
    1.0
    + 0.35 * value
    + 0.025 * value * value
    + (0.7 if level == "B" else 0.0)
    + 0.08 * ((index % 3) - 1)
    for index, (value, level) in enumerate(zip(dose, group, strict=True))
)

design_spec = DesignSpec.from_formula('y ~ pol(dose, 2) + catg(group, ["A", "B"])')
distribution = DataDistribution.from_data(
    {"dose": dose, "group": group},
    levels={"group": ("A", "B")},
    labels={"dose": "Dose", "group": "Treatment group"},
    units={"dose": "mg"},
)
design = design_spec.transform({"dose": dose, "group": group})
fitted_model = fit_ols(y, design)

geometry = build_nomogram(fitted_model, design_spec, distribution)
nomogram_svg = render_nomogram_svg(geometry)
summary_table = model_summary_table(summarize(fitted_model))
summary_latex = render_latex(summary_table)

assert tuple(axis.variable for axis in geometry.axes) == ("dose", "group")
assert geometry.design_fingerprint == design_spec.fingerprint
assert 'role="img"' in nomogram_svg
assert "Total points" in nomogram_svg
assert isinstance(summary_table.rows[1].values[1], float)
assert "Dose" in nomogram_svg
assert "\\begin{table}" in summary_latex
```

## Interpretation

Each predictor axis varies that predictor while holding all others at their
explicit `DataDistribution` adjustment values. Shared points reconstruct the
model linear predictor, and the OLS outcome axis uses the identity response.
The table independently retains coefficient estimates, uncertainty, and model
likelihood statistics as raw values before LaTeX formatting.

## Boundaries

The geometry is valid only for the declared additive model. Interactions fail
because one unconditional axis would hide effect modification. Current
nomograms exclude ordinal/survival models, confidence limits, custom response
transforms, and manual axes. A nomogram aids communication; it does not validate
functional form, calibration, transportability, or decision usefulness. No R
nomogram or `latex.*` parity is claimed.
