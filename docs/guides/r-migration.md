# Migrating from R `rms`

Holocron follows Regression Modeling Strategies principles, but its API is not a
line-by-line translation of R syntax. Migration should begin with the statistical
contract, not mechanical renaming.

| R concept | Current Python concept | Important difference |
| --- | --- | --- |
| `asis(x)` | `Formula.parse("~ x")` | Numeric one-dimensional input only. |
| `pol(x, degree)` | `Formula.parse("~ pol(x, degree)")` | Explicit raw degree 2–10; no ambient default. |
| `lsp(x, knots)` | `Formula.parse("~ lsp(x, [knots...])")` | Strictly increasing explicit knots only. |
| `rcs(x, knots)` | `Formula.parse("~ rcs(x, [knots...])")` | Explicit knots only; no automatic placement. |
| `Design(...)` | `DesignSpec.from_formula(...)` | Additive numeric terms only; immutable generated-column metadata. |
| `ols(y ~ x)` | `fit_ols(y, design.rows, feature_names=design.column_names)` | Formula-driven fitting is not yet a single API call. |
| `predict(fit, newdata)` | `fit.predict(features)` | Numeric columns must use the fitted order; no adjustment-value semantics. |
| `datadist(...)` | `DataDistribution.from_data(...)` | Immutable explicit metadata replaces `options(datadist=...)`; categorical levels must be declared. |

## Migration checklist

1. Record the pinned R package version and the original model specification.
2. Parse only the supported allowlisted syntax and make learned parameters such
   as knots explicit.
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
