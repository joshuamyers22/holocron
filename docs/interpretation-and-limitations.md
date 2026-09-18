# Interpretation and limitations

Holocron currently proves a narrow engineering claim: for explicit-knot spline
design and well-conditioned full-rank OLS fixtures, its selected outputs match a
pinned R `rms` oracle under accepted field-aware tolerances on two platforms.
That is not evidence of package-wide equivalence, model validity, or fitness for
a consequential decision.

## Supported numerical envelope

The accepted float64 evidence environment is CPython 3.12.14 with NumPy 2.5.3
on macOS 15 arm64/Accelerate and Ubuntu 24.04 x86_64/OpenBLAS. Other platforms
may install and work, but do not inherit the parity claim. Exact fields remain
exact; approximate comparison is restricted to allowlisted numerical paths.

## Not yet supported

- automatic knots, formulas, `datadist`, labels, units, and missing-data policy;
- binary logistic, ordinal, Cox, parametric survival, and nonparametric survival
  Python estimators;
- inference tables, ANOVA, contrasts, calibration, validation, and resampling;
- robust covariance, clustered errors, penalization, and aliased fits;
- plotting, nomograms, serialization, and a dataframe adapter contract.

Some unsupported families already have committed R oracle outputs. Those files
freeze future comparison targets and do not imply a Python implementation.

## Decision boundary

Callers own the estimand, target population, action policy, time horizon, utility,
data provenance, leakage controls, and external validation. Holocron reports
numeric results; it does not authorize clinical, regulatory, financial, or
automated action. Review the [compatibility inventory](compatibility.md) and the
[numerical-envelope ADR](adr/ADR-009-supported-numerical-envelope.md) before
making even an experimental parity statement.
