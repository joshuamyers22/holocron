# Phase 5 time-dependent survival-validation acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 5 deliverable: time-dependent validation primitives
- Disposition: complete within the fixed-horizon right-censored envelope

## Accepted contract

`validate_survival_predictions` accepts positive observed times, binary event
indicators, one predicted survival probability per observation and strictly
increasing evaluation horizon, and optional positive frequency weights. It is
model-independent: predictions may come from a Holocron fit or from an external
model, provided rows and horizons retain their declared alignment.

At every horizon the immutable `SurvivalValidationResult` reports:

- an inverse-Kaplan–Meier-censoring-weighted Brier score;
- cumulative/dynamic AUC and its `Dxy = 2 * AUC - 1` transform, with half
  credit for prediction ties and `None` when cases or controls are absent;
- Kaplan–Meier observed survival, weighted mean predicted survival, and their
  signed marginal calibration difference;
- censoring survival plus unweighted case/control counts; and
- a normalized trapezoidal integrated Brier score when at least two horizons
  are supplied.

Event cases use censoring survival immediately before their observed event;
event-free controls use censoring survival at the evaluation horizon. Censored
observations at or before a horizon contribute to neither status. Inputs fail
closed on non-finite probabilities, invalid dimensions, increasing survival
curves, nonpositive times or weights, unordered horizons, unsupported sizes, or
loss of censoring positivity needed by an evaluable observation.

## Parity evidence

Two independently implemented pinned-R cases cover multiple horizons,
censoring, imperfect discrimination, prediction ties, positive frequency
weights, and tied event/censoring times. They add 20 exact and 52 field-aware
numeric comparisons, with maximum absolute error below `5e-16`. The complete
survival corpus now has sixteen cases passing 599 exact and 1,071 numeric
comparisons.

## Boundaries

These are external/fixed-prediction validation primitives, not model-refitting
validation. They do not implement `validate.cph`, `validate.psm`, bootstrap or
cross-validation optimism correction, smooth `hare`/`smoothkm` calibration,
Cox–Snell plots, censoring-time plots, model dispatch, confidence intervals,
competing-risk metrics, left/interval-censored validation, entry times, or
time-varying covariate paths. Global Harrell concordance from `dxy.cens` is also
distinct from the accepted horizon-specific cumulative/dynamic AUC.

All five Phase 5 deliverables are now implemented within their experimental
envelopes. The subsequent locked Phase 5 simulation package passes, as recorded
in [the simulation acceptance record](PHASE_5_SIMULATIONS.md).
The scoped review and exit gate subsequently close in
[the Phase 5 completion record](PHASE_5_COMPLETION.md); no capability advances
beyond `experimental`.
