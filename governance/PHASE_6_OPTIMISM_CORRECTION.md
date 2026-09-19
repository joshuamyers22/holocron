# Phase 6 optimism-correction acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 6 deliverable: optimism-corrected performance and calibration
- Disposition: complete within the declared fixed-design OLS/binary envelope

## Accepted contract

`optimism_correct_validation` consumes a `ModelValidationResult` and computes,
for every model-family metric:

```text
optimism = mean(training - assessment)
corrected = apparent - optimism
```

The mean is paired by successful split. When a metric such as R-squared or Dxy
is undefined on either side, that split is omitted only for that metric and the
result reports the exact contributing-resample count. Apparent, mean training,
mean assessment, optimism, and corrected values remain separate.

`optimism_correct_calibration` evaluates each retained training and assessment
recalibration relationship on the source result's declared prediction grid. It
then applies the same identity pointwise, retaining apparent, mean training,
mean assessment, optimism, and corrected curves. Corrected probability-scale
values are not clipped.

Both result types retain the exact source `ResampleExecution`, including its
plan fingerprint, successes, failures, status, and failure rate. A failed
execution cannot be aggregated. A partial execution fails closed by default;
`allow_partial=True` is required to aggregate its successful pairs and does not
change the reported partial status.

## Evidence

Focused tests cover OLS and binary-logistic metric sets, the exact correction
identity, pairwise omission of undefined metrics, pointwise response- and
probability-scale calibration correction, plan-fingerprint retention, and
complete, partial, and failed execution behavior. Executable documentation and
artifact installation smoke tests exercise the public correction functions.

## Boundaries and next step

Correction is only as honest as the retained refits. The fixed-design
convenience APIs do not relearn formula transformations, knots, factor levels,
imputation, or selection. Callers with learned preprocessing must run the whole
procedure through `run_resample_plan` and construct an equivalent retained-pair
contract before correction. This slice does not add smooth calibration,
ordinal or survival refits, confidence intervals, standard errors, pooling
across heterogeneous plans, or R `validate.*`/`calibrate.*` method parity.

That next diagnostics-and-selection deliverable is now accepted in
`PHASE_6_DIAGNOSTICS_SELECTION.md`. Failure-rate and partial-resample reporting
is next. Phase 6 and its exit gate remain open.
