# Gallery: adjusted effects and inference

## Goal

Fit one adjusted OLS model, predict an effect over a declared covariate grid,
and communicate the coefficient contrast and formula-term tests without
reconstructing statistics inside a renderer.

## Workflow

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.graphics import (
    anova_plot_spec,
    contrast_plot_spec,
    effect_plot_spec,
    render_svg,
)
from holocron.models import anova, contrast, fit_ols, predict, summarize
from holocron.reporting import model_summary_table, render_latex

x = tuple(float(index) for index in range(16))
z = tuple(float((index % 4) - 1) for index in range(16))
y = tuple(
    2.0 + 0.45 * x_value - 0.3 * z_value + 0.08 * ((index % 3) - 1)
    for index, (x_value, z_value) in enumerate(zip(x, z, strict=True))
)

design_spec = DesignSpec.from_formula("y ~ x + z")
design = design_spec.transform({"x": x, "z": z})
fitted_model = fit_ols(y, design)

effect_grid = (1.0, 4.0, 7.0, 10.0, 13.0)
future_design = design_spec.transform(
    {"x": effect_grid, "z": (0.0,) * len(effect_grid)}
)
prediction_result = predict(fitted_model, future_design)
effect_spec = effect_plot_spec(
    prediction_result,
    effect_grid,
    predictor_label="Exposure",
    response_label="Expected outcome",
)
effect_svg = render_svg(effect_spec)

contrast_result = contrast(
    fitted_model,
    {"asis(x)": 1.0},
    name="One-unit exposure difference",
)
contrast_spec = contrast_plot_spec((contrast_result,))
contrast_svg = render_svg(contrast_spec)

anova_result = anova(fitted_model, design_spec)
anova_spec = anova_plot_spec(anova_result)
anova_svg = render_svg(anova_spec)

summary_table = model_summary_table(summarize(fitted_model))
summary_latex = render_latex(summary_table)

assert effect_spec.layers[1].y == prediction_result.values
assert contrast_spec.layers[0].estimates == (contrast_result.estimate,)
assert tuple(test.term for test in anova_result.tests) == ("x", "z")
assert all('role="img"' in value for value in (effect_svg, contrast_svg, anova_svg))
assert isinstance(summary_table.rows[1].values[1], float)
assert "\\begin{table}" in summary_latex
```

## Interpretation

The effect curve is conditional on `z=0`; it is not a marginal population
effect. Its band is a mean-response confidence interval from the fitted model.
The named contrast tests the declared one-unit coefficient combination, while
the ANOVA panel shows joint Wald tests in formula-term order. The coefficient
table retains the same raw estimates and likelihood statistics before LaTeX
formatting.

## Boundaries

This synthetic example does not justify a causal interpretation, the selected
adjustment set, linear functional form, or multiple-testing policy. It does not
provide simultaneous bands, marginal standardization, or R graphics/LaTeX
parity. Check residual behavior, data support, and the estimand before using the
same workflow on an applied analysis.
