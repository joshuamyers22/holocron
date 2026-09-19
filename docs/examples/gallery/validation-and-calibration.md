# Gallery: validation and calibration

## Goal

Use one exact materialized resample plan to estimate optimism in performance
and calibration, while keeping execution coverage visible beside the corrected
results.

## Workflow

```python
# holocron: execute
from holocron.graphics import (
    calibration_plot_spec,
    render_svg,
    validation_plot_spec,
)
from holocron.models import fit_ols
from holocron.reporting import (
    render_latex,
    resample_report_table,
    validation_table,
)
from holocron.validation import (
    ResamplePlan,
    calibrate_model,
    optimism_correct_calibration,
    optimism_correct_validation,
    report_resample_execution,
    validate_model,
)

x = tuple(float(index) for index in range(18))
features = tuple((value,) for value in x)
y = tuple(
    1.5 + 0.4 * value + 0.12 * ((index % 4) - 1.5) for index, value in enumerate(x)
)
fitted_model = fit_ols(y, features, feature_names=("x",))
plan = ResamplePlan.k_fold(len(y), folds=3, repeats=2, seed=23)

validation = validate_model(fitted_model, y, features, plan)
calibration = calibrate_model(
    fitted_model,
    y,
    features,
    plan,
    prediction_grid=(2.0, 4.0, 6.0, 8.0),
)
corrected_validation = optimism_correct_validation(validation)
corrected_calibration = optimism_correct_calibration(calibration)

validation_spec = validation_plot_spec(corrected_validation)
calibration_spec = calibration_plot_spec(corrected_calibration)
validation_svg = render_svg(validation_spec)
calibration_svg = render_svg(calibration_spec)

validation_table_spec = validation_table(corrected_validation)
validation_latex = render_latex(validation_table_spec)
resample_report = report_resample_execution(
    corrected_validation.resamples,
    metric_contributors={
        metric.name: metric.contributing_resamples
        for metric in corrected_validation.metrics
    },
)
resample_table = resample_report_table(resample_report)
resample_latex = render_latex(resample_table)

assert corrected_validation.status == "complete"
assert corrected_calibration.status == "complete"
assert corrected_validation.successful_resamples == 6
assert validation_spec.legend_order == ("apparent", "corrected")
assert calibration_spec.legend_order == ("apparent", "corrected", "ideal")
assert resample_report.failure_rate == 0.0
assert all('role="img"' in value for value in (validation_svg, calibration_svg))
assert "Corrected" in validation_latex
assert "Planned coverage" in resample_latex
```

## Interpretation

Each split refits the model and retains separate training and assessment
indices. Corrected performance is the apparent value minus mean training-minus-
assessment optimism. The calibration plot applies the same correction
pointwise. The coverage table is part of the interpretation: it shows how many
planned and successful resamples contributed to each metric.

## Boundaries

The convenience workflow validates an already-realized numeric design. Any
learned transformation, imputation, knot selection, or term selection must be
repeated inside a lower-level resample callback. A complete run does not prove
transportability, and corrected estimates are not an external validation.
Current model-specific correction supports OLS and binary-logistic families;
smooth calibration and R `validate`/`calibrate` parity remain deferred.
