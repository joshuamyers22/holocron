# Interpretation and limitations

Holocron currently proves narrow engineering claims: predictor-distribution
summaries, allowlisted numeric/factor/restricted-interaction formula designs,
and selected estimator and post-estimation outputs from well-conditioned full-
rank OLS, Gaussian/binomial `Glm`, binary `lrm`, and exact-response ordinal
models, including selected diagonal
penalties and alternative covariance estimates, match a pinned R `rms` oracle
under field-aware tolerances.
Seven locked synthetic simulation scenarios additionally pass predeclared
recovery, coverage, calibration, discrimination, type-I-error, robust-
covariance, bootstrap, and penalization thresholds, and 16 numerical edge cases
pass their declared exception or result-invariant contracts.
Seven separate Phase 5 scenarios totaling 1,280 replications pass their Cox,
parametric-survival, Kaplan–Meier, censoring, and fixed-horizon-validation
thresholds without a failed replication.
That is not evidence of package-wide equivalence, model validity, or fitness for
a consequential decision.

The common resampling engine preserves exact analysis/assessment indices and
can prove that its callback is invoked once per split. It cannot inspect a
callback to prove that every learned preprocessing, selection, fit, and score
was actually repeated. Callers must keep those steps inside the procedure;
the model-specific convenience APIs freshly refit OLS or binary-logistic models
but treat their supplied numeric feature matrix as fixed. They therefore do not
prove that formula transformations or other externally learned preprocessing
were learned inside each split. Their per-split results may be summarized by
the owned optimism-correction layer, but that correction covers only the work
actually repeated inside each refit. It cannot repair leakage from a full-data-
derived design or other preprocessing supplied from outside the callback.

Optimism-corrected metrics use apparent minus the mean paired training-
assessment gap. Undefined pairs are omitted metric by metric and accompanied by
an effective contributor count. Parametric calibration curves use the same
identity pointwise and are not clipped after correction. Partial resample
executions are rejected by default; explicitly allowing them preserves the
partial status and failure rate but does not prove that failures are ignorable.

Influence flags use declared heuristics, not universal decision rules. OLS
coefficient changes are exact case-deletion identities; binary-logistic changes
are one-step approximations at the fitted model. VIFs are descriptive values
derived from the slope-coefficient covariance correlation matrix. Robustness
comparisons change estimated uncertainty, not model specification or validity.

Penalty tracing evaluates only the caller's finite, strictly increasing scalar
grid. Its AIC/BIC values use constant-free deviance and the fitted model's
effective degrees of freedom; those degrees of freedom need not be monotone for
the accepted penalized OLS variance contract. Backward selection uses joint
Wald p-values, fully refits after every removal, never infers hierarchy, and
does not make post-selection confidence intervals or p-values valid. Treat it
as exploratory unless the complete selection procedure is repeated during
validation and independently assessed.

The standalone binary-probability metrics describe supplied predictions; they
do not refit a model, prove out-of-sample evaluation, or correct optimism.
Probabilities must be strictly inside `(0, 1)` because log scores and logistic
recalibration are part of the contract. A separated recalibration fit is
reported as undefined rather than replaced by a finite approximation. Grouped
calibration is a descriptive weighted equal-frequency summary, not a smooth
calibration estimator.

Survival validation is limited to right-censored outcomes and fixed horizons.
Its grouped observed survival uses Kaplan--Meier estimates, and threshold
classification uses the same inverse-censoring-weighted case/control contract
as the horizon metrics. Integrated AUC is undefined if AUC is undefined at any
horizon. These metrics do not validate left/interval-censored outcomes,
time-varying covariates, competing risks, or the prediction model itself.

The simulations use correctly specified synthetic data and fixed engineering-
gate sizes. They are internal validity checks, not evidence for transportability,
real-world calibration, subgroup performance, robustness to missingness or
model misspecification, or an end-user decision process. See the
[simulation evidence guide](guides/simulation-and-edge-evidence.md) for the
design and observed metrics.

## Supported numerical envelope

The accepted float64 evidence environment is CPython 3.12.14 with NumPy 2.5.3
on macOS 15 arm64/Accelerate and Ubuntu 24.04 x86_64/OpenBLAS. Other platforms
may install and work, but do not inherit the parity claim. Exact fields remain
exact; approximate comparison is restricted to allowlisted numerical paths.

## Not yet supported

- automatic knots or factor levels, unrestricted or higher-order interactions,
  dataframe/date-time adapters, and model-level missing-data policy;
- Cox score/Schoenfeld/influence residuals, robust covariance, and formula-level
  fitting; parametric distributions beyond Weibull/exponential and parametric
  residuals for left/interval censoring; Kaplan–Meier alternate estimators,
  interval-censored nonparametric curves, competing risks, and robust variance;
- adjusted-effect `summary.rms`, complete `anova.rms` partitioning, nonlinear or
  simultaneous contrasts, smooth calibration, ordinal/survival model-specific
  validation, LOWESS/`hare` smooth calibration, named-group `val.probg`, and
  R `validate.*`/`calibrate.*` method parity;
- off-diagonal penalties, automatic/adaptive penalty search or R `pentrace`
  parity, weighted or offset fits, bootstrap
  confidence intervals, resampled transformation learning, and aliased fits;
- GLM families/links outside Gaussian/identity and binomial/logit, ordinal
  weights/offsets/partial proportional odds, marginal random-effects
  prediction, plotting, nomograms, and a dataframe adapter contract.

Some unsupported families already have committed R oracle outputs. Those files
freeze future comparison targets and do not imply a Python implementation.
Exact-response, interval-censored, random-intercept, and dual-scale `mix_re`
ordinal fixtures are parity-qualified. Phase 4 simulations, quadrature,
sparsity, failure-mode, and platform evidence pass. One-sided censoring follows
the documented open-endpoint contract under a pinned-R parity exception. Ron
Mexico independently approved the complete Phase 4 private experimental scope,
including that exception, on 2026-09-18.

Sixteen survival fixtures are parity-qualified for all five implemented Phase 5
deliverables: Efron/Breslow Cox, exact/left/right/interval-censored
Weibull/exponential AFT, Kaplan–Meier, and the supported counting-process,
stratification, weight, offset, baseline-quantity, curve, mean, quantile,
prediction, residual, fixed-horizon IPCW Brier, cumulative/dynamic AUC/Dxy,
marginal-calibration, and integrated-Brier operations. They do not establish
proportional hazards, distributional adequacy, external validity, or support
for the deferred survival features listed above. The Phase 5 simulations add
known-data-generating-process recovery and coverage evidence. Ron Mexico's
scoped independent numerical/statistical approval closes the Phase 5 private-
development exit gate, but does not promote these capabilities beyond
experimental.

## Decision boundary

Callers own the estimand, target population, action policy, time horizon, utility,
data provenance, leakage controls, and external validation. Holocron reports
numeric results; it does not authorize clinical, regulatory, financial, or
automated action. Review the [compatibility inventory](compatibility.md) and the
[numerical-envelope ADR](adr/ADR-009-supported-numerical-envelope.md) before
making even an experimental parity statement.
