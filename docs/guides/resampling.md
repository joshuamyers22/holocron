# Exact resample plans

Phase 6 begins with a model-independent resampling contract. A `ResamplePlan`
contains every analysis and assessment row index needed to replay bootstrap,
repeated K-fold, or caller-declared resampling. Seeds generate plans; serialized
indices—not later RNG behavior—define their exact identity.

## Generate and persist a plan

```python
# holocron: execute
from holocron.validation import ResamplePlan

plan = ResamplePlan.k_fold(
    12,
    folds=3,
    repeats=2,
    seed=71,
    plan_id="development-validation",
    row_ids=tuple(f"subject-{index + 1}" for index in range(12)),
)
restored = ResamplePlan.from_json(plan.to_json())

assert restored == plan
assert restored.fingerprint == plan.fingerprint
assert len(plan.splits) == 6
```

Bootstrap plans store one full-size iid analysis resample per replicate and use
the original rows, in original order, as the assessment sample. Repeated K-fold
plans partition every row into assessment exactly once per repeat. `exact()`
preserves caller-supplied order and multiplicity, allowing an externally
audited grouped, stratified, or temporal schedule to be represented without
Holocron silently regenerating it.

Every plan stores unique row identifiers in its fingerprint. Constructors use
positional string identifiers by default; pass stable source identifiers when
reordering must be detectable. Supplying the current identifiers to
`take_rows(..., row_ids=...)` rejects order or identity drift before selection.

## Refit the whole procedure

`run_resample_plan` invokes a caller-owned procedure once per exact split. The
procedure receives indices, not a pre-fitted model. Learn transformations,
select terms, fit, and assess inside that callback.

```python
# holocron: execute
from holocron.models import fit_ols
from holocron.validation import ResamplePlan, run_resample_plan, take_rows

x = tuple(float(value) for value in range(12))
y = tuple(1.5 + 0.7 * value for value in x)
features = tuple((value,) for value in x)
plan = ResamplePlan.k_fold(12, folds=3, repeats=2, seed=71)


def refit(split):
    analysis_x = take_rows(features, split.analysis_indices, plan=plan)
    analysis_y = take_rows(y, split.analysis_indices, plan=plan)
    assessment_x = take_rows(features, split.assessment_indices, plan=plan)
    fitted = fit_ols(analysis_y, analysis_x, feature_names=("x",))
    return fitted.predict(assessment_x)


execution = run_resample_plan(plan, refit)
assert execution.status == "complete"
assert execution.plan_fingerprint == plan.fingerprint
assert execution.failure_rate == 0.0
```

The default failure policy stops on the first failed whole-procedure refit.
`failure_policy="record"` instead returns bounded failure records and a
`partial` or `failed` status; it never labels incomplete execution `complete`.
Callers must declare an acceptable failure policy before evaluation rather than
discarding failed resamples after inspecting results.

## Report failures and partial coverage

`report_resample_execution` turns retained outcomes into a typed, auditable
summary. It preserves exact successful and failed split IDs, groups equal
exception-type/message pairs, reports each reason as a fraction of all planned
resamples, and optionally records per-metric contributor coverage.

```python
# holocron: execute
from holocron.validation import (
    ResamplePlan,
    report_resample_execution,
    run_resample_plan,
)

plan = ResamplePlan.exact(
    4,
    (
        ((0, 1, 2), (3,)),
        ((0, 1, 3), (2,)),
        ((0, 2, 3), (1,)),
    ),
)


def sometimes_fails(split):
    if split.split_id == "exact-2":
        raise ValueError("single-class assessment")
    return split.split_id


execution = run_resample_plan(plan, sometimes_fails, failure_policy="record")
strict_report = report_resample_execution(
    execution,
    metric_contributors={"brier_score": 2, "dxy": 1},
)
partial_report = report_resample_execution(execution, allow_partial=True)

assert strict_report.status == "partial"
assert strict_report.failure_rate == 1.0 / 3.0
assert not strict_report.aggregation_permitted
assert partial_report.aggregation_permitted
assert strict_report.failure_reasons[0].exception_type == "ValueError"
assert strict_report.metric_coverage[0].metric_name == "brier_score"
```

Reporting and permission are separate. The default `complete-only` policy marks
a partial run ineligible for downstream aggregation. `allow_partial=True`
records a deliberate opt-in but leaves the status `partial`, preserves the
failure rate, and never permits aggregation when every resample failed.
`metric_contributors` counts defined metric pairs among successful resamples;
the report separately exposes planned coverage and coverage among successes so
undefined metrics cannot be mistaken for refit failures.

## Validate a supported fixed design

`validate_model` applies the exact plan to an existing OLS or binary-logistic
model family. It fits a fresh model on every analysis sample and measures it on
both that analysis sample and its assessment sample. OLS reports R-squared,
mean squared error, and linear calibration intercept/slope. Binary logistic
reports Somers' Dxy, Brier score, and logistic calibration intercept/slope.

```python
# holocron: execute
from holocron.models import fit_ols
from holocron.validation import (
    ResamplePlan,
    calibrate_model,
    optimism_correct_calibration,
    optimism_correct_validation,
    validate_model,
)

x = tuple(float(value) for value in range(20))
y = tuple(1.0 + 0.5 * value + 0.1 * ((value % 3) - 1.0) for value in x)
features = tuple((value,) for value in x)
fitted = fit_ols(y, features, feature_names=("x",))
plan = ResamplePlan.k_fold(20, folds=4, seed=71)

validation = validate_model(fitted, y, features, plan)
calibration = calibrate_model(fitted, y, features, plan, grid_points=20)
corrected_validation = optimism_correct_validation(validation)
corrected_calibration = optimism_correct_calibration(calibration)

assert validation.status == "complete"
assert calibration.status == "complete"
assert len(validation.resamples.successes) == 4
assert len(calibration.apparent_curve) == 20
assert corrected_validation.metric("mean_squared_error").corrected is not None
assert len(corrected_calibration.corrected_curve) == 20
```

The apparent estimate and every successful training/assessment pair remain
separate in the source result. `optimism_correct_validation` summarizes each
metric as `apparent - mean(training - assessment)`. A metric that is undefined
on either side of a split omits that pair only for that metric and reports its
own contributing-resample count. `calibrate_model` uses a family-specific
parametric relationship: observed response on prediction for OLS and observed
event on predicted log odds for binary logistic regression.

`optimism_correct_calibration` evaluates every retained training and assessment
relationship on the original declared grid and applies the same correction
pointwise. A corrected probability-scale curve is not clipped to `[0, 1]`;
values outside that range expose the correction rather than silently changing
it. Both correction functions reject partial executions by default. Passing
`allow_partial=True` is an explicit decision to aggregate successful pairs,
and the result still exposes `status`, `failure_rate`, and the retained source
execution.

The supplied matrix is an already-realized design. If transformations,
imputation, term selection, or other preprocessing were learned from data, use
`run_resample_plan` and repeat those steps inside its callback. Passing a
full-data-derived design to `validate_model` does not make those steps
fold-local.

## Boundaries

The engine is sequential. The model-specific convenience and optimism-
correction layers are limited to unpenalized OLS and binary-logistic results on
fixed numeric designs. They do not yet implement ordinal or survival refits,
smooth calibration, parallel or distributed execution, stratified/grouped/
time-series generators, or serialization of arbitrary callback results. Exact
custom plans can carry externally constructed schedules, but callers remain
responsible for proving their sampling semantics and for keeping every learned
step inside the callback. A partial-report opt-in does not establish that
failures are random or harmless and does not repair selection bias from omitted
resamples.
