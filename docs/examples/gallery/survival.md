# Gallery: survival curves and fixed-horizon validation

## Goal

Compare stratified Kaplan–Meier curves and communicate censoring-adjusted
prediction accuracy and calibration at prespecified horizons.

## Workflow

```python
# holocron: execute
from holocron.graphics import (
    calibration_plot_spec,
    render_svg,
    survival_plot_spec,
    validation_plot_spec,
)
from holocron.models import fit_npsurv, validate_survival_predictions
from holocron.reporting import render_latex, validation_table

times = (1, 2, 3, 4, 5, 6, 2, 3, 4, 5, 6, 7)
events = (1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1)
groups = ("standard",) * 6 + ("intensive",) * 6

km_fit = fit_npsurv(times, events, strata=groups)
curve_result = km_fit.predict_curve((0.0, 2.0, 4.0, 6.0))
survival_spec = survival_plot_spec(curve_result)
survival_svg = render_svg(survival_spec)

validation_times = (1, 2, 3, 4, 5, 6)
validation_events = (1, 0, 1, 0, 1, 1)
predicted_survival = (
    (0.75, 0.50, 0.25),
    (0.80, 0.58, 0.32),
    (0.70, 0.45, 0.20),
    (0.85, 0.65, 0.40),
    (0.90, 0.72, 0.48),
    (0.92, 0.78, 0.55),
)
horizons = (2.5, 4.5, 5.5)
survival_validation = validate_survival_predictions(
    validation_times,
    validation_events,
    predicted_survival,
    horizons,
)
survival_validation_spec = validation_plot_spec(survival_validation)
survival_calibration_spec = calibration_plot_spec(survival_validation)
validation_svg = render_svg(survival_validation_spec)
calibration_svg = render_svg(survival_calibration_spec)
survival_table = validation_table(survival_validation)
survival_latex = render_latex(survival_table)

assert curve_result.strata == ("standard", "intensive")
assert all(layer.interpolation == "step" for layer in survival_spec.layers)
assert survival_validation.integrated_brier_score is not None
assert survival_validation.case_counts == (1, 2, 3)
assert all(
    'role="img"' in value for value in (survival_svg, validation_svg, calibration_svg)
)
assert survival_table.rows[0].values[0] == horizons[0]
assert "Brier score" in survival_latex
```

## Interpretation

The Kaplan–Meier panel is descriptive by group and retains the fitted step
function. The validation panel reports IPCW Brier scores and available
cumulative/dynamic AUC values over time. Grouped calibration compares observed
and mean predicted survival; signed calibration error is observed minus
predicted survival. Integrated summaries cover only the declared horizon
interval.

## Boundaries

The two tasks use separate synthetic data intentionally: a fitted Kaplan–Meier
curve is not a prediction model validation. Censoring-adjusted estimates still
depend on independent-censoring and positivity assumptions. These plots do not
test proportional hazards, parametric adequacy, external validity, or clinical
utility, and they do not claim R graphics parity.
