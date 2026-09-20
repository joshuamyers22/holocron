# Multiple-imputation pooling

Holocron's Phase 8 adapter pools completed-data results. It does not generate
imputations or replace an imputation package.

## Pool compatible model fits

Fit the same realized design separately in every completed dataset, then pass
the homogeneous results together:

```python
from holocron.models import fit_ols
from holocron.validation import pool_imputation_models

features = ((0.0,), (1.0,), (2.0,), (3.0,), (4.0,))
fit_one = fit_ols((1.0, 1.8, 3.1, 4.0, 5.2), features)
fit_two = fit_ols((0.9, 2.0, 2.9, 4.2, 5.0), features)

pooled = pool_imputation_models((fit_one, fit_two))
print(pooled.coefficients)
print(pooled.standard_errors)
print(pooled.fraction_missing_information)
```

The result uses Rubin's within- and between-imputation covariance rules and
Barnard--Rubin small-sample degrees of freedom. The same path supports
`BinaryLogisticResult`. Coefficient names, family, sample shape, intercept
choice, and design fingerprint must agree exactly.

## Pool validation and calibration

Apply each existing workflow within each completed dataset first:

```python
from holocron.validation import (
    pool_imputation_calibration,
    pool_imputation_validation,
)

# corrected_validations contains OptimismCorrectedValidationResult objects.
pooled_validation = pool_imputation_validation(corrected_validations)

# corrected_calibrations contains OptimismCorrectedCalibrationResult objects.
pooled_calibration = pool_imputation_calibration(
    corrected_calibrations,
    grid_points=100,
)
```

Validation metrics are averaged over imputations for which that metric is
defined. Contributor counts are retained. Calibration components are linearly
interpolated or extrapolated to one common grid before pointwise averaging.
Incomplete resample executions fail closed unless `allow_partial=True` is
passed explicitly; that opt-in never changes their retained partial status.

## Pool explicit likelihood-ratio tests

The LR path deliberately requires explicit tables so a Wald statistic cannot be
mistaken for a likelihood-ratio statistic:

```python
from holocron.validation import (
    LikelihoodRatioAnova,
    LikelihoodRatioTest,
    imputation_information_table,
    pool_imputation_likelihood_ratio,
)

per_imputation = (
    LikelihoodRatioAnova((LikelihoodRatioTest("age", ("age",), 8.0, 1),)),
    LikelihoodRatioAnova((LikelihoodRatioTest("age", ("age",), 10.0, 1),)),
)
stacked = LikelihoodRatioAnova((LikelihoodRatioTest("age", ("age",), 15.0, 1),))

pooled_anova = pool_imputation_likelihood_ratio(
    per_imputation,
    stacked=stacked,
)
information = imputation_information_table(pooled_anova)
```

The result reports the Chan--Meng adjusted chi-square, p-value, missing-
information fraction, denominator degrees of freedom, and chi-square discount.
The table is renderer-neutral and can be passed to Holocron's reporting APIs.

## Boundaries

- Supply at least two and at most 1,000 completed-data results.
- Model pooling is limited to unpenalized OLS and binary logistic fits with
  their stored classical covariance.
- Do not treat pooled-coefficient prediction as a pooled confidence interval;
  prediction uncertainty is not implemented.
- Imputation model selection, diagnostics, nested imputation within resampling,
  transformed estimands, and missing-not-at-random sensitivity analyses remain
  caller responsibilities.
- These APIs are mapped Python replacements for `processMI` and `prmiInfo`, not
  `fit.mult.impute` or R numerical-parity claims.

Every persisted pooled result supports strict `to_json`/`from_json` and ships
with a versioned schema. See the [compatibility inventory](../compatibility.md)
and the Phase 8 governance decision for the exact disposition.
