# Holocron

Holocron is an independent Python implementation of Frank Harrell's R `rms`
package. It aims to reproduce the integrated Regression Modeling Strategies
workflow—design metadata, estimation, inference, prediction, validation,
calibration, and graphics—with statistical fidelity and a Python-native API.

The project is distributed internally as `holocron-rms` and imported as
`holocron`. No external package has been published.

## Current status

Holocron is experimental and incomplete. Do not use it for consequential
analysis, inference, prediction, or clinical decisions.

Phases 0–6 are complete for private experimental development. The Phase 3
deliverables cover experimental `ols`,
Gaussian/identity and binomial/logit `Glm`, and binary `lrm` estimators plus
their covariance,
likelihood, residual, prediction, coefficient-summary, ANOVA, and linear-
contrast operations, diagonal OLS/lrm quadratic penalties, and robust and
bootstrap covariance, plus locked simulation reports and a numerical edge-case
corpus and a complete executable getting-started workflow. Ron Mexico
independently reviewed and approved the Phase 3 alpha scope on 2026-09-18; the
evidence-backed disposition is recorded in the
[Phase 3 completion record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_3_COMPLETION.md).
Every capability remains experimental pending its separate promotion reviews.
Ron Mexico also independently reviewed and approved the Phase 4 ordinal,
censoring, random-effects, and parity-exception scope on 2026-09-18; its exit
gate is recorded in the
[Phase 4 completion record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_4_COMPLETION.md).
Ron Mexico independently reviewed and approved the Phase 5 survival scope on
2026-09-18; its exit gate is recorded in the
[Phase 5 completion record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_5_COMPLETION.md).
The Phase 1 exit
gate is recorded in the
[completion record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_1_COMPLETION.md);
the evidence-backed Phase 2 disposition is recorded in its
[completion record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_2_COMPLETION.md).
All six Phase 2 deliverables—immutable data-distribution metadata, the
allowlisted formula/core design engine, and explicit factor/restricted-
interaction handling, plus stable design/result schemas and a serialization
policy, exhaustive transformation differential/property tests, and the R
design-specification migration guide—are complete within their experimental
envelopes. The exit gate checks all 18 design-system parity cases, adversarial
names, and exact serialized prediction reconstruction. External distribution
and capability promotion remain blocked by the governance reviews described
there.

The evidence-backed experimental surface implements predictor-distribution
metadata, safe formulas, numeric and factor transformations, restricted
interactions, classical full-rank ordinary least squares, bounded generalized
linear models, binary logistic regression, cumulative-link ordinal regression,
numeric mixed-censoring conversion, and single-cluster random-intercept ordinal
models, plus right-censored Efron/Breslow Cox models, exact/left/right/interval-
censored Weibull/exponential accelerated-failure-time models, Kaplan–Meier
curves, and fixed-horizon censoring-adjusted validation with the declared
risk-set, stratum, weight, offset, baseline-quantity, prediction, residual,
accuracy, discrimination, grouped-calibration, and threshold-classification
operations. Model-independent binary-probability validation covers
discrimination, Brier and log scores, likelihood quality indices, logistic
recalibration, grouped calibration, and declared thresholds. It also
includes the accepted post-estimation
operations, diagonal OLS/lrm penalties, and robust/bootstrap covariance. The
implemented surfaces are checked across 60 independent parity cases against
committed outputs from a Dockerized R oracle. The sixteen survival cases cover
coefficients, covariance, likelihoods, risk sets, baseline quantities,
curves, means, quantiles, predictions, supported residuals, IPCW Brier scores,
cumulative/dynamic discrimination, and marginal calibration.
Interval-censored,
random-intercept, and dual-scale random-effect ORM cases are parity-qualified;
one-sided censoring is covered by an explicit documented parity exception.
Compatibility is claimed
only for capabilities and support envelopes backed by the
[compatibility manifest](https://github.com/joshuamyers22/holocron/blob/main/compatibility/rms-8.2.0.yaml).
The current numerical envelope is CPython 3.12.14 with NumPy 2.5.3 on macOS 15
arm64/Accelerate and Ubuntu 24.04 x86_64/OpenBLAS, as defined by ADR-009.

Transformation breadth is additionally checked by deterministic generative
tests covering every supported degree, knot-count, level-count, and ordered pair
of restricted-interaction component kinds. Seven seeded Phase 3 simulation
scenarios run 2,620 outer replications against predeclared statistical
thresholds, and a data-driven corpus exercises 16 numerical edge cases across
nine failure and stability categories.

The Phase 4 package additionally runs 232 seeded fixed, censored, and clustered
ordinal replications, two quadrature-stability checks, three response-support
sparsity/conditioning cases, and nine failure-mode cases on both accepted
platforms. Its technical evidence and scoped independent statistical review
pass, closing Phase 4 for private experimental development.

All five Phase 5 deliverables are implemented within their experimental
envelope. Cox, Weibull/exponential AFT, and Kaplan–Meier paths now cover declared
ties, strata, entry times where defined, positive weights, offsets where
defined, baseline hazard/survival, hazard/survival prediction, and supported
residuals. Typed survival curves, event-time quantiles, analytic parametric
means, and restricted Cox/Kaplan–Meier means are also supported. Parametric
responses accept explicit exact, left, right, and interval bounds. Fixed-horizon
validation provides censoring-adjusted Brier, AUC/Dxy, marginal calibration,
and integrated Brier metrics. A locked seven-scenario, 1,280-replication
simulation package passes all declared recovery, coverage, censoring, tie,
strata/offset, Kaplan–Meier, and validation thresholds with no failed
replication. Additional distributions, independent numerical/statistical
review for capability promotion, and broader survival functionality remain
deferred. The Phase 5 private-development exit gate is closed.

All six Phase 6 deliverables are implemented within their experimental
envelopes. They provide immutable exact
bootstrap, repeated K-fold, and caller-declared resample plans plus
model-specific fixed-design validation and parametric calibration for OLS and
binary-logistic results. Every split refits a fresh model, retains separate
training and assessment measurements, and preserves explicit
complete/partial/failed outcomes. The broader model-independent metric layer
adds weighted binary probability validation and expands right-censored
survival validation. Model-specific performance metrics and parametric
calibration curves can now be corrected by the mean retained training-minus-
assessment gap, with pairwise contributor counts and fail-closed partial-
execution behavior. OLS and binary-logistic diagnostics now provide influence
measures, covariance-correlation VIFs, robust/model uncertainty comparisons,
bounded explicit penalty traces, and fresh-refit backward selection over
caller-declared term groups. Typed resample reports preserve exact outcome IDs,
failure rates and grouped reasons, per-metric contributor coverage, and an
explicit complete-only or allow-partial aggregation disposition. The accountable
technical completion review passes the Phase 6 private-development exit gate;
it does not claim independent approval or promote any capability beyond
experimental. See the
[Phase 6 completion record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_6_COMPLETION.md).

Phase 7 is underway. Its first four deliverables add immutable backend-neutral plot
specifications for numeric lines, points, interval bands, categorical bars and
estimate intervals, semantic annotations and metadata, explicit axis scales,
legend order, and required alternative text. Plot specifications use strict
versioned JSON. Typed adapters cover effects, contrasts, ANOVA, validation,
calibration, survival, and diagnostics; a dependency-free backend renders the
same specifications as bounded accessible inline SVG. Strict backend-neutral
nomogram geometry and accessible SVG cover additive identity-bound OLS and
binary-logistic models, with interactions rejected explicitly. Immutable typed
tables retain raw result values in strict canonical JSON, and typed adapters
feed a deterministic dependency-free LaTeX renderer that escapes all
caller-controlled text. Task-oriented galleries and broader renderer assurance
remain deferred.

## Library API

Holocron is a typed library and intentionally installs no command-line tools.
Its current public namespaces are `holocron.design`, `holocron.formula`,
`holocron.graphics`, `holocron.models`, `holocron.reporting`,
`holocron.validation`, and `holocron.exceptions`:

```python
from holocron.design import DataDistribution, DesignSpec
from holocron.formula import Formula
from holocron.models import fit_ols

x = (-2.0, -1.0, 0.0, 1.0, 2.0, 3.0)
y = (0.2, 0.8, 1.1, 1.7, 2.5, 3.6)

metadata = DataDistribution.from_data({"x": x}, labels={"x": "Predictor"})
spec = DesignSpec.from_formula(Formula.parse("y ~ rcs(x, [-2, 0, 1.5, 3])"))
design = spec.transform({"x": x})
fit = fit_ols(y, design)
predictions = fit.predict(design)
restored_fit = type(fit).from_json(fit.to_json())
```

`metadata["x"]` retains adjustment, effect, display, and overall ranges without
depending on global state or the original input iterable.

Design specifications, realized matrices, OLS results, binary-logistic results,
ordinal results, all three survival result types, exact resample plans, and plot
specifications, nomogram geometry, and table specifications use strict versioned
data-only JSON. Fitting from a `DesignMatrix`
carries its specification fingerprint into the result and checks that identity
during prediction. The public schemas ship under `holocron/schemas`; arbitrary
pickle interchange is not supported.

Explicit categorical and scored-ordered terms plus hierarchical two-way
restricted interactions are supported by the design compiler. Automatic knot
or level selection, unrestricted or higher-order interactions, missing-data
policies, aliased-fit handling, other GLM families/links, off-diagonal
penalties, automatic or dense penalty searches, weights/offsets, bootstrap confidence intervals,
partial proportional odds, and multi-effect random structures are not supported
outside the explicitly documented paths. Survival families beyond Cox,
Weibull/exponential AFT, and Kaplan–Meier remain unsupported.
Unsupported behavior must fail explicitly
rather than silently substitute a different method. See the
[package architecture](https://github.com/joshuamyers22/holocron/blob/main/docs/architecture/PACKAGE_STRUCTURE.md) for API and
dependency boundaries.

## Reference and oracle

The statistical reference is the local `rms` 8.2-0 snapshot at
`/Users/josh/Downloads/rms-master`, frozen to upstream commit
`a4e4a305a029090e737562fb4d35bdb705db7d63`. The R source is GPL-licensed
reference material and is not copied into Holocron or its distributions.

R and `rms` run only in a pinned, isolated Docker oracle with versioned JSON
input/output. Holocron never calls R at runtime. To rebuild and verify it:

```sh
make oracle-build RMS_SOURCE=/Users/josh/Downloads/rms-master
make oracle-health
make oracle-check
```

See the [oracle documentation](https://github.com/joshuamyers22/holocron/blob/main/reference/README.md)
and [ADR-001](https://github.com/joshuamyers22/holocron/blob/main/docs/adr/ADR-001-independent-oracle.md)
for the provenance boundary
and two-stage oracle/independent-test workflow. External distribution remains
blocked pending qualified license and provenance review.

## Development

The canonical development environment uses CPython 3.12.14 and uv 0.12.7;
package metadata permits Python 3.11 or later. Both tool versions and the full
dependency/build graph are frozen and checked as described in the
[environment contract](https://github.com/joshuamyers22/holocron/blob/main/docs/reproducibility/FROZEN_ENVIRONMENTS.md).

```sh
make setup
make check
make phase-1-e2e
make phase-3-evidence-clean
make phase-5-evidence-clean
make build
make audit
```

`make check` runs formatting, linting, strict type checking, unit and parity
fixture tests, frozen-environment checks, and reference-metadata validation.
It also executes the Phase 1 and Phase 2 evidence gates, the Phase 3 simulation
and numerical-edge suites, the Phase 4 evidence package, and the Phase 5
survival simulations. Their schema-valid reports are written under `.work/`
and retained by CI for 30 days. The simulation designs, reports, and
interpretation are described in the
[simulation guide](https://github.com/joshuamyers22/holocron/blob/main/docs/guides/simulation-and-edge-evidence.md).
`make build` uses the locked build backend offline and without isolation, then
inspects and independently installs both wheel and source distribution into
fresh environments. Each installation runs dependency validation and the
supported Phase 3 public workflow from outside the checkout. `make clean-build`
additionally rejects source-tree changes and is the required CI/release gate.

The project scope and delivery gates are defined in
[project plan](https://github.com/joshuamyers22/holocron/blob/main/PROJECT_PLAN.md).
Statistical contributions must follow the
[contributing guide](https://github.com/joshuamyers22/holocron/blob/main/CONTRIBUTING.md)
and the independent-development policy.

## Documentation

The documentation site includes a complete executable Phase 3 workflow,
generated public API reference, and a generated inventory of every compatibility
disposition. Build or preview it locally with:

```sh
make docs-check
make docs
```

Edit the authoritative compatibility manifest or public Python source, then run
`make docs-generate` to refresh generated pages. The ordinary `make check` gate
rejects stale generated content, failed examples, invalid internal links, and
MkDocs warnings.
