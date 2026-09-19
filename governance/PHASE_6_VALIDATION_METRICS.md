# Phase 6 probability and survival metric acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 6 deliverable: broader probability and survival validation metrics
- Disposition: complete within the declared model-independent binary and
  right-censored fixed-horizon envelopes

## Accepted contract

`validate_probabilities` evaluates row-aligned binary outcomes and predicted
probabilities with positive frequency weights. It reports discrimination,
Brier and log scores, likelihood-quality indices, logistic recalibration,
parametric absolute calibration errors, Spiegelhalter's statistic,
calibration-in-the-large, prediction-ranked calibration groups, and declared-
threshold classification metrics. Probabilities are strictly inside `(0, 1)`;
separated recalibration is explicitly undefined.

`validate_survival_predictions` retains its right-censored fixed-horizon IPCW
Brier, cumulative/dynamic AUC/Dxy, marginal calibration, and integrated Brier
contract and adds:

- prediction-ranked groups with within-group Kaplan--Meier observed survival;
- declared-risk-threshold sensitivity, specificity, predictive values, and
  accuracy using IPCW event-case and event-free-control contributions;
- integrated AUC when AUC exists at every supplied horizon; and
- integrated absolute marginal calibration error.

Inputs, group counts, threshold counts, and prediction-matrix size are bounded.
Thresholds and horizons must be strictly increasing. Tied predictions remain
together in grouped summaries, and weights have frequency-weight semantics.

## Evidence

The `probability-validation-overall` case executes pinned
`rms::val.prob(p=..., y=..., pl=FALSE)` and passes 4 exact and 21 numeric
comparisons, with maximum absolute error `8.881784197001252e-16` and maximum
relative error `2.3601170876489558e-15`. Existing fixed-horizon survival oracle
cases continue to cover the overlapping `val.surv` quantities. Owned Python
tests cover declared values, ties, undefined discrimination and recalibration,
integrated summaries, malformed inputs, and equivalence of integer frequency
weights to replicated rows for binary and survival metrics.

## Boundaries and next step

These functions score supplied predictions. They do not establish that those
predictions are out of sample, refit a model, rebuild preprocessing, aggregate
resamples, or correct optimism. Grouped calibration is descriptive; LOWESS,
`hare`, `smoothkm`, named-group `val.probg`, Cox--Snell plots, model dispatch,
and plotting are deferred. Survival metrics cover right censoring only;
left/interval censoring, entry times, competing risks, and time-varying
covariates are outside this contract.

Optimism-corrected performance and calibration are recorded separately in
`PHASE_6_OPTIMISM_CORRECTION.md`. Phase 6 and its exit gate remain open.
