# Interpretation and limitations

Holocron currently proves narrow engineering claims: predictor-distribution
summaries, allowlisted numeric/factor/restricted-interaction formula designs,
and selected estimator and post-estimation outputs from well-conditioned full-
rank OLS, Gaussian/binomial `Glm`, and binary `lrm`, including selected diagonal
penalties and alternative covariance estimates, match a pinned R `rms` oracle
under field-aware tolerances.
Seven locked synthetic simulation scenarios additionally pass predeclared
recovery, coverage, calibration, discrimination, type-I-error, robust-
covariance, bootstrap, and penalization thresholds, and 16 numerical edge cases
pass their declared exception or result-invariant contracts.
That is not evidence of package-wide equivalence, model validity, or fitness for
a consequential decision.

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
- ordinal, Cox, parametric-survival, and nonparametric-survival Python
  estimators;
- adjusted-effect `summary.rms`, complete `anova.rms` partitioning, nonlinear or
  simultaneous contrasts, calibration, validation, and resampling;
- off-diagonal penalties, `pentrace`, weighted or offset fits, bootstrap
  confidence intervals, resampled transformation learning, and aliased fits;
- GLM families/links outside Gaussian/identity and binomial/logit, ordinal
  `lrm`, plotting, nomograms, and a dataframe adapter contract.

Some unsupported families already have committed R oracle outputs. Those files
freeze future comparison targets and do not imply a Python implementation.

## Decision boundary

Callers own the estimand, target population, action policy, time horizon, utility,
data provenance, leakage controls, and external validation. Holocron reports
numeric results; it does not authorize clinical, regulatory, financial, or
automated action. Review the [compatibility inventory](compatibility.md) and the
[numerical-envelope ADR](adr/ADR-009-supported-numerical-envelope.md) before
making even an experimental parity statement.
