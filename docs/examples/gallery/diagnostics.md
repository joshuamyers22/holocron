# Gallery: model diagnostics and robustness

## Goal

Inspect observation influence, compare model-based and clustered robust
uncertainty, check covariance-based collinearity, and review a declared penalty
path without turning any one diagnostic into an automatic decision rule.

## Workflow

```python
# holocron: execute
from holocron.graphics import diagnostic_plot_spec, render_svg
from holocron.models import (
    fit_ols,
    influence_diagnostics,
    robustness_diagnostics,
    trace_penalty,
    variance_inflation_factors,
)
from holocron.reporting import diagnostic_table, render_latex

x = tuple(float(index - 10) for index in range(20))
z = tuple(float((index * 7) % 11 - 5) for index in range(20))
features = tuple(zip(x, z, strict=True))
y = tuple(
    2.0 + 1.2 * x_value - 0.25 * z_value + 0.1 * ((index % 5) - 2)
    for index, (x_value, z_value) in enumerate(features)
)
fitted_model = fit_ols(y, features, feature_names=("x", "z"))

influence = influence_diagnostics(fitted_model, y, features)
robustness = robustness_diagnostics(
    fitted_model,
    y,
    features,
    clusters=tuple(index // 2 for index in range(len(y))),
)
penalty_trace = trace_penalty(
    fitted_model,
    y,
    features,
    (0.0, 0.25, 1.0, 4.0),
    criterion="bic",
)
vifs = variance_inflation_factors(fitted_model)

influence_spec = diagnostic_plot_spec(influence, plot_id="influence")
robustness_spec = diagnostic_plot_spec(robustness, plot_id="robustness")
penalty_spec = diagnostic_plot_spec(penalty_trace, plot_id="penalty")
vif_spec = diagnostic_plot_spec(vifs, plot_id="vif")
influence_svg = render_svg(influence_spec)
robustness_svg = render_svg(robustness_spec)
penalty_svg = render_svg(penalty_spec)
vif_svg = render_svg(vif_spec)

diagnostic_table_spec = diagnostic_table(robustness)
diagnostic_latex = render_latex(diagnostic_table_spec)

assert len(influence.observations) == len(y)
assert robustness_spec.legend_order == ("model-se", "robust-se")
assert penalty_trace.selected_point in penalty_trace.points
assert tuple(value.coefficient_name for value in vifs) == ("x", "z")
assert all(
    'role="img"' in value
    for value in (influence_svg, robustness_svg, penalty_svg, vif_svg)
)
assert "Robust/model ratio" in diagnostic_latex
```

## Interpretation

Cook distance and declared heuristic thresholds identify rows for investigation,
not deletion. Robust-to-model standard-error changes describe sensitivity to
the clustered covariance assumption. VIFs summarize covariance-correlation
inflation for non-intercept coefficients. The penalty trace compares only the
explicit grid and marks the AIC/BIC minimizer within that grid.

## Boundaries

None of these outputs establishes model adequacy or authorizes automated row,
term, or penalty selection. Cluster-robust uncertainty requires scientifically
meaningful clusters and enough independent clusters. VIF thresholds are not
universal. The penalty path is bounded and scalar; it is not cross-validation,
a dense optimizer, or R `pentrace` parity.
