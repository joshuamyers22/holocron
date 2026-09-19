# Probability and survival validation metrics

The standalone validation functions evaluate predictions that already exist.
They do not fit a model, choose a resampling plan, or establish that the
predictions are out of sample. Use them on a genuinely held-out assessment set
or inside a correctly scoped resampling procedure.

## Binary probabilities

`validate_probabilities` accepts binary outcomes, probabilities strictly
inside `(0, 1)`, optional positive frequency weights, a requested number of
prediction-ranked groups, and ordered classification thresholds.

```python
# holocron: execute
from holocron.validation import validate_probabilities

binary = validate_probabilities(
    (0, 1, 0, 1, 0, 1, 1, 0),
    (0.10, 0.70, 0.40, 0.60, 0.55, 0.80, 0.35, 0.45),
    calibration_groups=4,
    thresholds=(0.4, 0.5, 0.6),
)

assert binary.auc == 0.8125
assert binary.dxy == 0.625
assert binary.brier_score > 0.0
assert binary.log_loss > 0.0
assert len(binary.calibration_groups) == 4
assert len(binary.threshold_metrics) == 3
```

The result includes AUC/Somers' Dxy, Brier and scaled Brier scores, log and
null-log scores, Nagelkerke R-squared, discrimination/unreliability/quality
indices, likelihood-ratio statistics, logistic recalibration intercept and
slope, parametric calibration-error summaries, Spiegelhalter's statistic,
prevalence, mean prediction, and calibration-in-the-large. Calibration groups
have weighted equal-frequency targets and never split tied predictions.

Complete or quasi-complete separation can make the logistic recalibration
relationship non-finite. In that case its intercept, slope, unreliability, and
derived parametric calibration errors are `None`; discrimination, scoring,
grouped, and threshold results remain available. Endpoint probabilities are
rejected because the contract includes log loss and predicted log odds.

## Right-censored survival predictions

`validate_survival_predictions` accepts one survival-probability column per
strictly increasing horizon. Predictions must be row aligned and non-increasing
across horizons.

```python
# holocron: execute
from holocron.validation import validate_survival_predictions

survival = validate_survival_predictions(
    (1, 2, 3, 4, 5, 6),
    (1, 0, 1, 0, 1, 1),
    (
        (0.75, 0.50, 0.25),
        (0.80, 0.58, 0.32),
        (0.70, 0.45, 0.20),
        (0.85, 0.65, 0.40),
        (0.90, 0.72, 0.48),
        (0.92, 0.78, 0.55),
    ),
    (2.5, 4.5, 5.5),
    calibration_groups=3,
    risk_thresholds=(0.25, 0.50),
)

assert survival.integrated_brier_score is not None
assert survival.integrated_auc is not None
assert survival.integrated_absolute_calibration_error is not None
assert len(survival.calibration_groups) == 3
assert len(survival.threshold_metrics) == 6
```

Brier scores and threshold tables use inverse Kaplan--Meier censoring weights.
AUC is cumulative/dynamic and Dxy is `2 * AUC - 1`. Each grouped calibration
record compares mean predicted survival with within-group Kaplan--Meier
survival. Integrated results are normalized trapezoidal summaries over the
declared horizon range; they are `None` for a single horizon, and integrated
AUC is also `None` if any component AUC is undefined.

## Boundaries

Both functions use positive weights with frequency-weight semantics. Grouped
summaries are descriptive and are not LOWESS, `hare`, or `smoothkm` calibration
curves. Named-group `val.probg`, Cox--Snell plots, left- and interval-censored
survival validation, competing-risk metrics, and model dispatch remain
deferred. These standalone functions do not refit or correct optimism; the
separate fixed-design OLS/binary workflow is documented in
[Exact resample plans](resampling.md).
