# Simulation and numerical-edge evidence

Holocron's fixed R oracle cases answer a compatibility question: does a Python
operation reproduce the pinned `rms` result for a declared input? The Phase 3
simulation plan asks a different question: across repeated samples from known
data-generating processes, do the current estimators exhibit the predeclared
bias, uncertainty, calibration, discrimination, and type-I-error behavior?

Both forms of evidence are required. Neither establishes suitability for a new
population or consequential use.

## Locked simulation plan

The versioned plan contains seven deterministic scenarios and 2,620 outer
replications. Every scenario has a fixed NumPy seed, sample size, parameters,
and acceptance interval. Thresholds live in the plan—not in runner code—so a
failed study cannot be made green by silently changing its comparator.

| Scenario | Replications | Primary checks |
|---|---:|---|
| Gaussian OLS recovery | 500 | coefficient bias, slope RMSE, 95% interval coverage |
| Gaussian OLS null | 500 | two-sided slope type-I error |
| Binary logit recovery | 400 | Glm/lrm bias, RMSE, coverage, agreement, calibration, Brier score, AUC |
| Binary logit null | 400 | Glm and lrm type-I error |
| Clustered OLS covariance | 400 | robust and naive coverage, coverage gain, SE calibration |
| OLS bootstrap variance | 120 | bootstrap-to-empirical variance ratio and centering; 60 inner resamples |
| Penalized OLS collinearity | 300 | coefficient and prediction MSE ratios, effective DF |

The committed report passed every threshold with no failed outer replication.
Selected diagnostics include OLS slope coverage `0.950`, binary Glm/lrm slope
coverage `0.930`, binary null type-I error `0.0375`, clustered robust coverage
`0.9175` versus naive coverage `0.7125`, and a bootstrap-to-empirical variance
ratio of `1.0675`.

The report retains aggregate values, failed replication identifiers, and a
SHA-256 digest of canonical per-replication diagnostics. It deliberately does
not commit thousands of generated samples. The fixed scenario seed reproduces
the stream when detailed diagnosis is needed.

## Numerical edge corpus

The data-driven corpus contains 16 cases across rank, residual degrees of
freedom, conditioning, response validation, separation, convergence, penalty,
robust-covariance, and bootstrap behavior. Each case declares either an exact
exception class or explicit result invariants. Current success invariants cover
finite results, symmetric positive-semidefinite covariance, stable prediction,
effective-DF accounting, penalty behavior, and deterministic resampling.

One compatibility edge is intentionally surprising. `rms::lm.pfit` defines its
penalized OLS effective-DF diagonal using the ratio of penalized to unpenalized
variance. On a nearly deterministic duplicated-column design, effective DF can
therefore exceed the sample size and residual DF can be negative. Holocron
preserves and tests that observed contract; callers must not reinterpret the
field as the ordinary trace-of-hat-matrix quantity.

Complete separation now raises `SeparationError` consistently from both
binomial `Glm` and binary `lrm`, including when IRLS first reaches a non-finite
intermediate state. Singular or single-class declared bootstrap resamples raise
`NumericalError`; failed replicates are never silently discarded.

## Phase 5 survival simulations

The separate `phase-5-survival-models-v1` plan runs seven deterministic
scenarios totaling 1,280 replications. It covers continuous and tied Cox
recovery, stratified Cox with offsets, right-censored and mixed-censored
Weibull AFT recovery, Kaplan–Meier recovery and interval coverage, and IPCW
validation metrics against complete latent-event-time targets. Every threshold
passes with no failed replication. Ron Mexico independently approved the
scoped numerical/statistical evidence on 2026-09-18, closing the Phase 5
private-development exit gate.

Run it with:

```sh
make phase-5-evidence
```

The report is written under `.work/phase-5-evidence/`, binds the plan hash,
revision, environment, aggregate metrics, failed IDs, and replication-detail
digests, and validates against its JSON Schema. CI uses
`make phase-5-evidence-clean`, retains the clean report, and repeats the same
plan on macOS 15 and Ubuntu 24.04.

## Reproduce the Phase 3 evidence

From the frozen development environment, run:

```sh
make phase-3-evidence
```

This validates the plan and corpus, executes both suites, validates the two
reports against their JSON Schemas, and writes fresh artifacts under
`.work/phase-3-evidence/`. The clean-checkout acceptance form is:

```sh
make phase-3-evidence-clean
```

CI runs that clean form and retains both reports. Its macOS arm64 and Ubuntu
x86_64 matrix also executes the same thresholds and retains platform-specific
reports. The immutable acceptance artifacts are the
[simulation report](https://github.com/joshuamyers22/holocron/blob/main/governance/evidence/phase-3/simulation-report.json)
and [numerical-edge report](https://github.com/joshuamyers22/holocron/blob/main/governance/evidence/phase-3/numerical-edge-report.json).

## Interpretation boundary

These are deliberately small synthetic studies for the current Phase 3 core.
They do not assess model misspecification, missing data, nonlinear effect
selection, external validity, subgroup performance, calibration correction, or
an end-user analysis process. Phase 3 does not assess ordinal or survival
estimators; the Phase 5 suite covers only the declared synthetic survival
regimes and does not remove those broader limits.
Passing them supports the stated experimental engineering contract only.
