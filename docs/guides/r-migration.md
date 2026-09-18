# Migrating R `rms` design specifications

Holocron follows Regression Modeling Strategies principles, but it does not load
R objects or emulate R evaluation. Migrate the design contract—not the spelling
of one formula. That contract includes variable identity, levels and reference
order, transformation parameters, interaction restrictions, intercept policy,
generated-column order, and the rows used by the model.

This guide covers the current experimental design envelope and classical
full-rank OLS and the supported Gaussian/binomial `Glm` and binary `lrm`
envelopes, including the accepted diagonal-penalty and alternative-covariance
subset. It is not a migration path for an arbitrary `rms` fit.

## End-to-end example

A representative R workflow may rely on inferred factor metadata and an ambient
`datadist` option:

```r
group <- factor(group, levels = c("control", "treated", "other"))
dd <- datadist(age, group)
options(datadist = "dd")
fit <- ols(outcome ~ rcs(age, c(30, 45, 60, 75)) + group,
           x = TRUE, y = TRUE)
```

The Holocron equivalent makes those choices explicit and keeps distribution
metadata separate from the transformation specification:

```python
# holocron: execute
from holocron.design import DataDistribution, DesignSpec
from holocron.models import fit_ols

age = (20, 27, 34, 41, 48, 55, 62, 69, 76, 83, 90, 97)
group = (
    "control",
    "treated",
    "other",
    "control",
    "treated",
    "other",
    "control",
    "treated",
    "other",
    "control",
    "treated",
    "other",
)
outcome = (1.1, 1.6, 1.9, 2.4, 2.8, 3.0, 3.5, 3.9, 4.2, 4.8, 5.0, 5.5)

distribution = DataDistribution.from_data(
    {"age": age, "group": group},
    levels={"group": ("control", "treated", "other")},
    labels={"age": "Age", "group": "Treatment group"},
    units={"age": "years"},
)
specification = DesignSpec.from_formula(
    "outcome ~ rcs(age, [30, 45, 60, 75]) + "
    'catg(group, ["control", "treated", "other"])'
)
design = specification.transform({"age": age, "group": group})
fit = fit_ols(specification.response_values({"outcome": outcome}), design)

assert design.shape == (12, 5)
assert design.term_slices == ((0, 3), (3, 5))
assert design.include_intercept
assert fit.design_fingerprint == specification.fingerprint
assert distribution["group"].adjustment == "control"

future = specification.transform({"age": (50, 70), "group": ("control", "treated")})
predictions = fit.predict(future)
assert len(predictions) == 2
```

The `DataDistribution` object does not implicitly configure `DesignSpec` or the
fit. Keep both artifacts when the original analysis needs distribution summaries
for later effect or display operations.

## Concept map

| R `rms` concept | Holocron contract | Migration rule |
|---|---|---|
| `datadist(...)` | `DataDistribution.from_data(...)` | Pass named iterables and declare categorical/ordered levels, labels, and units. |
| `options(datadist=...)` | No ambient equivalent | Retain and pass explicit metadata; process-global configuration is intentionally absent. |
| `asis(x)` or bare `x` | `x` or `asis(x)` in `Formula` | One finite numeric input column. |
| `pol(x, degree)` | `pol(x, degree)` | Raw powers; declare an integer degree from 2 through 10. |
| `lsp(x, knots)` | `lsp(x, [knots...])` | Declare 1–32 finite, strictly increasing knots. |
| `rcs(x, knots)` | `rcs(x, [knots...])` | Declare 3–32 finite, strictly increasing knots; automatic placement is not migrated. |
| unordered factor | `catg(x, [levels...])` | Declare 2–64 unique levels; the first level is the reference. |
| `scored(x)` | `scored(x, [levels...])` | Declare 3–64 strictly increasing numeric levels. |
| `a %ia% b` | `ia(a, b)` | Include identical `a` and `b` main effects; doubly nonlinear products are omitted. |
| formula intercept | default or leading `0`/`-1` | The policy is metadata; `DesignMatrix` never contains an intercept column. |
| `Design(...)` | `DesignSpec.from_formula(...)` | Compile an immutable, allowlisted AST with stable generated-column identity. |
| `DesignAssign` | `columns` and `term_slices` | Narrow replacement only; slices are zero-based, half-open Python intervals. |
| `interactions.containing` | `DesignSpec.interactions_containing(...)` | Returns zero-based term indices from the immutable specification. |
| stored model matrix | `DesignMatrix` | Contains rows, names, nonlinear flags, term slices, intercept policy, and specification fingerprint. |
| `ols(...)` | `fit_ols(response, design)` | Pass the `DesignMatrix` to retain design identity and intercept policy. |
| `Glm(..., family=gaussian())` | `fit_glm(response, design, family="gaussian")` | Identity link only; returns `OlsResult`. |
| `Glm(..., family=binomial())` | `fit_glm(response, design, family="binomial")` | Logit link and binary response only. |
| binary `lrm(...)` | `fit_lrm(response, design)` | Unpenalized full-rank binary response only. |
| penalized `ols(...)` | `fit_penalized_ols(response, design, penalty=...)` | Diagonal, non-negative slope weights only; the intercept is unpenalized. |
| penalized binary `lrm(...)` | `fit_penalized_lrm(response, design, penalty=...)` | Diagonal, non-negative slope weights only. |
| `robcov(fit, cluster=...)` | `robust_covariance(fit, response, design, clusters=...)` | Uncorrected Huber cluster sandwich; omitted clusters make rows independent clusters. |
| `bootcov(fit, B=...)` | `bootstrap_covariance(fit, response, design, replicates=..., seed=...)` | Iid row resampling only; pass `resample_indices` for cross-language replay. |
| `predict(fit, newdata=...)` | `fit.predict(specification.transform(data))` | Transform with the original specification; unseen or missing values fail closed. |
| `vcov(fit)` | `covariance(fit)` | Full named covariance or a named principal submatrix. |
| `logLik(fit)` | `likelihood(fit)` | Includes maximized/null likelihood, AIC, and the overall LR test. |
| `residuals(fit, type=...)` | `residuals(fit, kind=..., response=...)` | Binary residuals require the original response explicitly. |
| interval `predict(...)` | `predict(fit, design, ...)` | Mean uncertainty for every supported model; individual intervals for OLS only. |
| coefficient table | `summarize(fit)` | Coefficient-level Wald inference only; this is not adjusted-effect `summary.rms`. |
| `anova(fit)` | `anova(fit, specification)` | Joint Wald tests for declared formula-term blocks only. |
| `contrast(fit, ...)` | `contrast(fit, weights)` | One explicit linear coefficient contrast; no R expression evaluation. |

## 1. Freeze the R-side contract

Before translating code, retain enough R-side information to explain the exact
matrix that was fitted:

- R, `rms`, and Hmisc versions;
- the original formula and intercept choice;
- analysis-row selection and row order;
- predictor storage types, factor levels, ordering, and reference levels;
- `datadist` adjustment values, ranges, labels, and units that matter later;
- explicit or resolved polynomial degree, spline knots, and interaction terms;
- generated model-matrix column names and values; and
- any warnings, aliases, offsets, strata, weights, or missing-value actions.

Holocron cannot recover these from an `.rds` file. If the R design depended on
automatic knots, inferred levels, contrasts, or global options, resolve and
record those values in R first. Do not recompute them independently in Python
and call the result the same design.

## 2. Replace `datadist` global state

Construct `DataDistribution` directly from the intended analysis columns. The
object records adjustment values, effect/display/overall ranges, retained
values, labels, units, and missingness counts. Use `with_adjustment` for a
reviewed reference-value change and `with_data` to append same-row-count
variables without mutating the original object.

Important differences from R are deliberate:

- no `options(datadist=...)` lookup occurs;
- categorical and ordered levels must be declared;
- an even number of ordered levels uses the lower middle declared level;
- display probabilities are determined independently per variable when
  missingness counts differ;
- labels and units are metadata and do not convert values; and
- formula transformation parameters are not selected from this object yet.

`DataDistribution` may summarize `None` and NaN as missing for supported numeric
summaries. `DesignSpec.transform` does not perform row exclusion or imputation;
model-design input must already be complete and finite.

## 3. Translate the formula explicitly

Holocron parses only additive registered terms. It never evaluates R or Python
expressions. Backtick a name containing whitespace, operators, parentheses, or
a reserved transformation name; double a literal backtick inside it.

```text
`response ~ value` ~ 0 + `blood pressure` + pol(marker, 3)
                     + lsp(time, [1, 4])
                     + rcs(age, [20, 40, 60, 80])
                     + catg(group, ["control", "treated"])
                     + scored(stage, [1, 2, 4, 8])
```

Categorical ordering is semantic. `catg` emits one indicator for every declared
level after the first. `scored` emits the numeric score followed by indicators
for levels three onward. Prediction values outside the declaration raise
`InputValidationError`; there is no fallback or implicit new-level policy.

For an R restricted interaction such as `pol(x, 3) %ia% rcs(z, knots)`, write:

```text
~ pol(x, 3) + rcs(z, [0, 1, 3, 6])
  + ia(pol(x, 3), rcs(z, [0, 1, 3, 6]))
```

Both exact component terms must appear as main effects. Holocron rejects nested,
self, reversed-duplicate, unrestricted, and three-way interactions instead of
silently changing their meaning.

## 4. Build and inspect the design

The canonical data boundary is a mapping of unique string names to equal-length
Python iterables. Holocron snapshots them and emits float64 rows. It does not yet
consume dataframe metadata, apply an R contrasts option, or choose an analysis
sample.

Inspect these fields before fitting:

- `specification.formula.expression`: canonical round-trippable formula;
- `specification.columns`: source variables, transformation, ownership,
  nonlinear status, and interaction components for each column;
- `design.column_names`: exact generated-column order;
- `design.nonlinear_mask`: column-aligned nonlinear classification;
- `design.term_slices`: zero-based half-open ownership intervals;
- `design.include_intercept`: estimator intercept policy; and
- `design.specification_fingerprint`: identity of the reconstruction contract.

The response is not part of the matrix. For a two-sided formula,
`specification.response_values(data)` validates and snapshots it separately.
Transformation itself needs only predictor columns, which is useful for future
prediction data.

## 5. Verify against the R matrix

Compare designs before comparing fitted coefficients. Use the same rows, order,
knots, levels, references, and intercept policy on both sides.

1. Compare response identity, intercept policy, term order, normalized generated
   identities, nonlinear flags, and term ownership exactly.
2. Compare transformed float64 values under the accepted
   `deterministic-transform-v1` policy: `1e-12` absolute and relative tolerance.
3. Confirm the first categorical level and the scored-level order explicitly.
4. Confirm restricted-interaction columns are left-major and contain no product
   for which both components are nonlinear.
5. Repeat the transformation on held-out rows, including knot boundaries,
   factor references, both spline tails, and adversarial names.

Do not assume literal R and Holocron column labels are equal. The project oracle
normalizes R terms into Holocron's descriptive canonical names before exact
comparison. Establish the positional semantic mapping from the R term/design
metadata first, then compare the normalized identities and values.

The committed parity corpus contains 14 pinned-R RCS/design cases. They cover
every supported main-effect kind, adversarial names, both representative
interaction forms, and exact design metadata. The deterministic property suite
additionally covers every supported degree, knot-count, level-count, and all 36
ordered interaction-kind pairs. These are the project claims; a private ad hoc
comparison does not expand the supported envelope.

## 6. Retain reconstruction and prediction identity

Persist `DesignSpec.to_json()` with its schema version and fingerprint. Recreate
prediction designs with `DesignSpec.from_json(...)`, then call `transform` on the
new predictor mapping. If a realized matrix must be exchanged, its JSON retains
the specification fingerprint and intercept policy.

Passing `DesignMatrix` directly to `fit_ols` carries that fingerprint into the
result. Passing raw numeric rows is still accepted for narrow array workflows,
but loses specification-identity checking. A result fitted with a design matrix
rejects prediction from a matrix compiled under a different specification.

The supported interchange is strict, bounded, non-executable JSON. Pickle,
joblib, R object deserialization, and arbitrary class reconstruction are not
supported. Fingerprints detect identity mismatch but are not signatures.

## Stop conditions

Do not claim a supported migration when the R workflow requires any of the
following:

- automatic knot, level, contrast, or transformation-parameter selection;
- general R formula operators, callbacks, offsets, strata, matrices, `gTrans`,
  unrestricted interactions, or interactions above two variables;
- implicit `na.action`, imputation, row filtering, or dataframe/date-time
  semantics;
- complete R `DesignAssign`, `modelData`, `Newlevels`, `Newlabels`, or `specs`
  behavior;
- aliased OLS columns, weights, offsets, dense penalties, `pentrace`,
  finite-sample robust corrections, cluster/stratified bootstrap, bootstrap
  intervals, adjusted-effect summaries, complete `anova.rms` partitions, or
  nonlinear, simultaneous, grid-based, or expression-driven contrasts; or
- logistic behavior outside the supported binary/logit and diagonal-penalty
  envelope; ordinal behavior outside its declared contract; Cox strata, entry
  times, weights, offsets, or residuals; parametric families other than
  Weibull/exponential or non-right censoring; stratified/weighted/entry-time
  Kaplan–Meier; or validation, calibration, or nomogram execution in Python.

Supported ordinal and first-slice survival paths have Python parity evidence.
Anything outside those explicit envelopes remains a stop condition; Holocron
must raise an explicit error rather than substitute another method.

## Migration checklist

- [ ] Pin and record the R reference environment.
- [ ] Preserve the R analysis rows and their order.
- [ ] Extract exact knots, degrees, levels, references, and intercept policy.
- [ ] Recreate relevant `datadist` metadata explicitly; remove reliance on
      process-global options.
- [ ] Translate only allowlisted formula terms and make every learned parameter
      literal.
- [ ] Inspect names, nonlinear flags, slices, and interaction components.
- [ ] Compare the R and Holocron matrices before fitting.
- [ ] Exercise held-out reconstruction, factor references, knots, and tails.
- [ ] Persist the versioned design specification and fingerprint.
- [ ] Pass `DesignMatrix`, not bare rows, when design identity matters.
- [ ] Review the [compatibility inventory](../compatibility.md),
      [limitations](../interpretation-and-limitations.md), and
      [numerical envelope](../adr/ADR-009-supported-numerical-envelope.md).
- [ ] Retain the R workflow until every required downstream operation has its
      own accepted migration path.

The underlying design decisions are documented in
[ADR-005](../adr/ADR-005-formula-design-engine.md),
[ADR-006](../adr/ADR-006-canonical-data-boundary.md), and
[ADR-008](../adr/ADR-008-model-result-serialization.md).
