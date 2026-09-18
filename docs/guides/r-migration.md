# Migrating from R `rms`

Holocron follows Regression Modeling Strategies principles, but its API is not a
line-by-line translation of R syntax. Migration should begin with the statistical
contract, not mechanical renaming.

| R concept | Current Python concept | Important difference |
| --- | --- | --- |
| `rcs(x, knots)` | `RestrictedCubicSplineSpec(knots).transform(x)` | Explicit knots only; no formula metadata or automatic placement. |
| `ols(y ~ x)` | `fit_ols(y, features, feature_names=...)` | Caller constructs the design; no formulas or `datadist`. |
| `predict(fit, newdata)` | `fit.predict(features)` | Numeric columns must use the fitted order; no adjustment-value semantics. |
| `datadist(...)` | `DataDistribution.from_data(...)` | Immutable explicit metadata replaces `options(datadist=...)`; categorical levels must be declared. |

## Migration checklist

1. Record the pinned R package version and the original model specification.
2. Make knots and every generated design column explicit.
3. Preserve row order and document the analysis sample outside Holocron.
4. Compare only a capability marked evidence-backed on the
   [compatibility page](../compatibility.md).
5. Check known differences and the numerical envelope before interpreting a
   comparison.
6. Retain the R analysis until the complete workflow—not merely coefficients—has
   been independently qualified.

Binary logistic, ordinal, Cox, parametric survival, Kaplan–Meier, validation,
calibration, contrasts, and nomograms have frozen baselines or planned entries,
but no supported Python migration path yet. Holocron fails closed rather than
substituting another method.
