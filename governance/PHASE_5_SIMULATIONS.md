# Phase 5 survival simulation acceptance record

- Evidence date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Technical simulation evidence: passed
- Independent numerical/statistical reviewer: Ron Mexico
- Review disposition: approved on 2026-09-18
- Phase 5 exit gate: closed

## Reproducible package

The locked `phase-5-survival-models-v1` plan defines seven seeded scenarios and
1,280 outer replications. `make phase-5-evidence` validates the plan, executes
the public survival and validation APIs, checks every declared threshold, and
writes a schema-valid report to
`.work/phase-5-evidence/simulation-report.json`. The
`phase-5-evidence-clean` target additionally requires a clean source tree.

Reports bind the plan SHA-256, source revision and dirty state, runtime and
platform, aggregate metrics, failed replication identifiers, and a SHA-256 of
canonical per-replication diagnostics. CI runs the clean gate and repeats the
same package on Ubuntu 24.04 and macOS 15, retaining platform-specific reports.

## Scenarios and observed evidence

All 1,280 fits or validations completed without a failed replication and every
predeclared threshold passed:

- 120 continuous-time Cox replications gave slope bias `0.00749`, RMSE
  `0.08316`, 95% interval coverage `0.950`, and mean censoring `0.3489`;
- 80 tied-time replications gave Efron and Breslow slope biases `0.01775` and
  `0.03691`, mean coefficient disagreement `0.01916`, and tied-event fraction
  `0.8916`;
- 80 stratified Cox replications with offsets gave slope bias `0.00552`, RMSE
  `0.09228`, coverage `0.9375`, and correct stratum-baseline ordering in every
  replication;
- 500 right-censored Weibull AFT replications gave slope bias `0.00114`, RMSE
  `0.05302`, coverage `0.948`, scale bias `0.00352`, and mean censoring
  `0.2974`;
- 100 mixed exact/left/interval/right-censored Weibull AFT replications gave
  slope bias `0.00224`, RMSE `0.05289`, scale bias `0.00234`, and exercised
  mean left, interval, and right fractions of `0.1221`, `0.5939`, and `0.0909`;
- 250 Kaplan–Meier replications gave survival bias `0.0000561`, RMSE `0.03071`,
  and log-scale interval coverage `0.956`; and
- 150 censoring-adjusted validation replications kept absolute Brier and AUC
  bias at `0.0000603` and `0.000260`, mean absolute marginal-calibration error
  at `0.01440`, and integrated-Brier bias at `0.0000989` relative to complete
  latent-event-time targets.

The approved plan SHA-256 is
`c189df09f207c4c84a2391a2a8e4314b48f70ecaaf57870274e7ebbc0483ff57`.
During sizing, the right-censored PSM scenario was increased from 120 to 500
replications after the smaller pilot exposed the coarse resolution of a
two-sided coverage threshold. Its seed, data-generating process, acceptance
interval, and implementation were not relaxed; the 500-replication design is
the locked acceptance plan.

## Boundaries and gate disposition

These are correctly specified synthetic data-generating processes and fixed
engineering-gate sizes. They do not establish external validity, robustness to
misspecification or missingness, proportional-hazards or AFT adequacy, subgroup
performance, competing-risk behavior, clinical utility, or support outside the
documented experimental envelope.

The technical simulation package is complete and passing. Ron Mexico
independently reviewed the likelihood, observed-information, risk-set,
censoring, prediction, validation, and simulation-threshold evidence and
approved the Phase 5 private experimental scope on 2026-09-18. The Phase 5 exit
gate is closed; no capability advances beyond `experimental`.
