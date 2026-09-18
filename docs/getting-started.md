# Getting started

This workflow exercises the complete accepted Phase 3 path on a small synthetic
dataset. It keeps predictor policy, formula transformations, model fitting,
inference, prediction, covariance sensitivity checks, penalization, and safe
reconstruction explicit. Holocron never learns an analysis strategy from the
data or from global state.

!!! warning "Experimental workflow"
    This is an executable API guide, not a defensible analysis protocol. Do not
    use Holocron for consequential decisions. You still own the estimand,
    predictor selection, missing-data policy, validation design, multiplicity,
    external validity, and action threshold.

## 1. Declare the analysis data and policy

The example has one continuous predictor, one explicitly leveled group, a
continuous response, a binary response, and caller-declared clusters. Values
are synthetic and complete because model-level missing-data handling is not yet
supported.

`DataDistribution` records adjustment, display, labels, units, and level order.
`DesignSpec` owns the safe formula and every generated column. Fixed spline
knots and factor levels make training and future transformations identical.

## 2. Fit, inspect, and predict

The following is one executable program. CI runs it offline exactly as shown.

```python
# holocron: execute
import numpy as np

from holocron.design import DataDistribution, DesignMatrix, DesignSpec
from holocron.models import (
    BinaryLogisticResult,
    OlsResult,
    anova,
    bootstrap_covariance,
    contrast,
    fit_lrm,
    fit_ols,
    fit_penalized_lrm,
    fit_penalized_ols,
    likelihood,
    predict,
    residuals,
    robust_covariance,
    summarize,
)

# Synthetic analysis rows. Row order is shared by every declared column.
age = tuple(float(value) for value in range(30, 78, 2))
group = tuple("treated" if index % 4 in (1, 2) else "control" for index in range(24))
noise = (-0.30, 0.15, -0.10, 0.25, -0.20, 0.10) * 4
score = tuple(
    1.5 + 0.06 * value + (0.45 if arm == "treated" else 0.0) + error
    for value, arm, error in zip(age, group, noise, strict=True)
)
event = (0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1, 0, 1)
clusters = tuple(f"household-{index // 2}" for index in range(24))

distribution = DataDistribution.from_data(
    {"age": age, "group": group},
    levels={"group": ("control", "treated")},
    labels={"age": "Age", "group": "Study group"},
    units={"age": "years"},
)
specification = DesignSpec.from_formula(
    'score ~ rcs(age, [30, 44, 60, 76]) + catg(group, ["control", "treated"])'
)
design = specification.transform({"age": age, "group": group})
fit = fit_ols(score, design)

# Named post-fit records avoid positional reconstruction.
fit_likelihood = likelihood(fit)
coefficient_summary = summarize(fit)
term_tests = anova(fit, specification)
group_contrast = contrast(
    fit,
    {'catg(group,level="treated")': 1.0},
    name="treated minus control coefficient",
)
standardized_residuals = residuals(fit, kind="standardized")

# Future rows pass through the original immutable transformation contract.
future = specification.transform({"age": (40.0, 65.0), "group": ("control", "treated")})
future_means = predict(fit, future, interval="mean")

# Sensitivity estimators require the original analysis rows explicitly.
cluster_covariance = robust_covariance(fit, score, design, clusters=clusters)
bootstrap_estimate = bootstrap_covariance(
    fit, score, design, replicates=40, seed=20260918
)
penalized_fit = fit_penalized_ols(score, design, penalty=2.0)

# Supported persistence is strict JSON, never pickle.
restored_distribution = DataDistribution.from_json(distribution.to_json())
restored_specification = DesignSpec.from_json(specification.to_json())
restored_design = DesignMatrix.from_json(design.to_json())
restored_fit = OlsResult.from_json(fit.to_json())

assert distribution.adjustments == {"age": 53.0, "group": "control"}
assert design.shape == (24, 4)
assert fit.design_fingerprint == specification.fingerprint
assert fit_likelihood.parameter_count == fit.rank + 1
assert len(coefficient_summary.coefficients) == 5
assert tuple(test.term for test in term_tests.tests) == (
    "rcs(age, [30.0, 44.0, 60.0, 76.0])",
    'catg(group, ["control", "treated"])',
)
assert group_contrast.estimate > 0.0
assert len(standardized_residuals.values) == len(score)
assert future_means.lower is not None and future_means.upper is not None
assert cluster_covariance.cluster_count == 12
assert bootstrap_estimate.replicate_count == 40
assert penalized_fit.penalty_weights == (2.0, 2.0, 2.0, 2.0)
assert restored_distribution == distribution
assert restored_specification == specification
assert restored_design == design
assert restored_fit == fit
assert np.allclose(restored_fit.predict(future), future_means.values)

# Binary modeling uses a response-specific formula and the same predictor policy.
binary_specification = DesignSpec.from_formula(
    'event ~ age + catg(group, ["control", "treated"])'
)
binary_design = binary_specification.transform({"age": age, "group": group})
binary_fit = fit_lrm(event, binary_design)
binary_summary = summarize(binary_fit)
binary_future = binary_specification.transform(
    {"age": (40.0, 65.0), "group": ("control", "treated")}
)
binary_probabilities = predict(binary_fit, binary_future, scale="response")
binary_residuals = residuals(binary_fit, kind="deviance", response=event)
penalized_binary = fit_penalized_lrm(event, binary_design, penalty=1.0)
restored_binary = BinaryLogisticResult.from_json(binary_fit.to_json())

assert binary_fit.design_fingerprint == binary_specification.fingerprint
assert binary_summary.model_type == "lrm-binary"
assert all(0.0 < value < 1.0 for value in binary_probabilities.values)
assert len(binary_residuals.values) == len(event)
assert penalized_binary.penalty_weights == (1.0, 1.0)
assert restored_binary == binary_fit
```

## 3. Read the results by contract

The fitted objects retain coefficient names, covariance, fitted values,
dimensions, convergence information, and the originating design fingerprint.
Derived operations return typed records:

- `summarize` is coefficient-level inference, not adjusted-effect
  `summary.rms`;
- `anova` tests the coefficient block owned by each declared formula term;
- `contrast` evaluates the exact named linear combination supplied by the
  caller;
- `predict` returns estimates and uncertainty for a design produced by the
  matching specification;
- `robust_covariance` is the accepted uncorrected cluster sandwich; and
- `bootstrap_covariance` is seeded iid row resampling and fails if any requested
  refit fails.

The ordinary and penalized fits answer different questions. A penalty is a
declared modeling choice, not an automatic repair for every unstable analysis.
The binary example uses `fit_lrm`; use `fit_glm(..., family="binomial")` only
when its separately documented Glm numerical contract is the intended one.

## 4. Preserve enough to reproduce

Persist the distribution metadata, design specification, and fitted result
together. Their canonical JSON documents are strict, bounded, and
fingerprinted. A fingerprint detects mismatched content; it is not a digital
signature. Keep caller-owned data identifiers, retained-row identity,
environment, source revision, and analysis decisions in the surrounding
evidence record. Do not serialize sensitive raw rows merely to make a model
self-contained.

## 5. Know where to stop

This workflow does not provide automatic knot or level selection, missing-data
handling, weights or offsets, resampled transformation learning, internal
validation, calibration correction, model selection, bootstrap confidence
intervals, or external validation. It also does not make the group coefficient
causal. Stop rather than silently substitute another method when any of those
features is required.

Continue with the [data-distribution guide](guides/data-distributions.md),
[formula/design guide](guides/formulas-and-designs.md),
[generalized-model guide](guides/generalized-models.md),
[post-estimation guide](guides/post-estimation.md),
[regularization/covariance guide](guides/regularization-and-covariance.md),
[serialization guide](guides/serialization.md), and
[interpretation boundaries](interpretation-and-limitations.md).
