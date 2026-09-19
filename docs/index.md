# Holocron

Holocron is an independent Python implementation of Frank Harrell's R `rms`
package. It is building a Python-native Regression Modeling Strategies workflow
with explicit design metadata, statistical evidence, and capability-level parity
claims.

!!! warning "Experimental and incomplete"
    Do not use Holocron for consequential analysis, inference, prediction, or
    clinical decisions. No external package has been published.

The current experimental surface supports only:

- immutable predictor-distribution metadata;
- allowlisted formulas with numeric, categorical, scored-ordered, spline, and
  restricted two-way interaction designs; and
- classical ordinary least squares, Gaussian/identity and binomial/logit
  generalized linear models, and binary logistic regression for a
  full-rank, caller-supplied design; and
- typed covariance, likelihood, residual, interval prediction, coefficient-
  summary, declared-term ANOVA, and single linear-contrast operations; and
- diagonal quadratic penalties for OLS and binary `lrm`, plus robust/clustered
  and iid bootstrap covariance for every currently supported estimator path.
- experimental cumulative-link ordinal regression, exact-grid mixed-censoring
  conversion, and single-cluster random-intercept models; and
- experimental right-censored Efron/Breslow Cox,
  exact/left/right/interval-censored Weibull/exponential
  accelerated-failure-time, and Kaplan–Meier estimators with typed curves,
  means, and event-time quantiles; and
- immutable exact bootstrap, repeated K-fold, and caller-declared resample
  plans with whole-procedure execution, explicit partial-failure status, and
  typed failure-rate/reason and metric-coverage reporting.
- model-independent weighted binary-probability metrics and right-censored
  fixed-horizon survival validation with grouped calibration, threshold
  classification, and integrated summaries.
- metric-wise optimism correction and pointwise parametric calibration
  correction over retained OLS/binary training-assessment pairs.
- OLS/binary influence, covariance-correlation VIF, robust/model uncertainty,
  bounded scalar penalty-trace, and declared-group backward-selection helpers.
- immutable backend-neutral numeric and categorical plot specifications with
  semantic layers, annotations, metadata, and required alternative text.
- typed model/result adapters and dependency-free accessible inline SVG for
  effects, contrasts, ANOVA, validation, calibration, survival, and diagnostics.
- strict additive OLS/logit nomogram points geometry and accessible inline SVG.
- typed raw-value tables, result adapters, strict JSON, and safe deterministic
  dependency-free LaTeX output.
- five manifest-bound executable galleries spanning effects/inference,
  validation/calibration, survival, diagnostics, and nomogram/reporting tasks.
- deterministic structural SVG accessibility audits and exact golden fixtures
  for every supported plot layer, axis-scale kind, orientation, and nomogram.

The core estimator envelope is also checked by seven seeded simulation
scenarios totaling 2,620 outer replications and a 16-case numerical edge corpus.
Phases 3–7 are complete for private experimental development. Phases
3–5 passed their scoped independent statistical reviews; Phases 6–7 passed
accountable technical exit reviews without claiming independent approval. The
Phase 4 approval covers the
ordinal, censoring, random-effects, and documented parity-exception evidence;
the Phase 5 approval covers the declared survival scope, Phase 6 covers its
declared resampling, validation, diagnostics, and failure-reporting envelope,
and Phase 7 covers its owned presentation and documentation envelope.
All six Phase 7 deliverables are implemented within their experimental
envelopes: plot specifications, typed result adapters/SVG, additive nomogram
geometry/rendering, structured table/LaTeX reporting, five tested galleries,
and deterministic SVG assurance. Its accountable technical exit review passes
without claiming independent approval or R presentation-method parity. Phase 8
is next.
Capability promotion,
consequential use, and external distribution remain separately blocked.

The Phase 5 survival envelope has its own seven-scenario, 1,280-replication
simulation gate covering continuous and tied Cox data, strata and offsets,
right- and mixed-censored Weibull AFT data, Kaplan–Meier coverage, and
censoring-adjusted validation metrics. Its technical thresholds pass; scoped
independent numerical/statistical review by Ron Mexico also passes, closing the
Phase 5 private-development exit gate. Capabilities remain experimental.

The implemented APIs are checked against 60 cases from the pinned R `rms`
8.2-0 oracle. Sixteen cover Cox, parametric-survival, Kaplan–Meier, and
fixed-horizon survival validation,
censoring likelihoods, risk-set features, baseline quantities, curves, means,
quantiles, residuals, accuracy, discrimination, and marginal calibration.
Interval-censored and clustered ordinal paths have registered
oracle cases; one-sided censoring has a documented parity exception.
See the generated [compatibility inventory](compatibility.md) for the exact
surface and evidence links.

## Start here

- [Install the private development checkout](installation.md).
- [Define predictor distributions and adjustment values](guides/data-distributions.md).
- [Build safe formulas and reconstructible numeric designs](guides/formulas-and-designs.md).
- [Run the complete Phase 3 getting-started workflow](getting-started.md).
- [Fit the supported generalized and logistic models](guides/generalized-models.md).
- [Fit ordinal and censored-response models](guides/ordinal-censoring.md).
- [Fit supported survival models](guides/survival-models.md).
- [Use the supported post-estimation operations](guides/post-estimation.md).
- [Use penalties and alternative covariance estimators](guides/regularization-and-covariance.md).
- [Inspect and reproduce simulation and numerical-edge evidence](guides/simulation-and-edge-evidence.md).
- [Create and execute exact resample plans](guides/resampling.md).
- [Validate binary probabilities and survival predictions](guides/validation-metrics.md).
- [Diagnose and compare supported fitted models](guides/diagnostics-and-selection.md).
- [Build backend-neutral plot specifications](guides/plot-specifications.md).
- [Audit accessible SVG and review renderer snapshots](guides/svg-assurance.md).
- [Build structured tables and safe LaTeX output](guides/reporting.md).
- [Follow the adjusted-effects and inference gallery](examples/gallery/effects-and-inference.md).
- [Follow the validation and calibration gallery](examples/gallery/validation-and-calibration.md).
- [Follow the survival gallery](examples/gallery/survival.md).
- [Follow the diagnostics gallery](examples/gallery/diagnostics.md).
- [Follow the nomogram and reporting gallery](examples/gallery/nomogram-and-reporting.md).
- [Understand the interpretation boundary](interpretation-and-limitations.md).
- [Compare Python and R concepts](guides/r-migration.md).
- [Contribute through the frozen development environment](development.md).

## Compatibility means evidence

Holocron does not claim drop-in or package-wide parity. Each claim must identify
a Python entry point, pinned R behavior, oracle cases, a named field-aware
tolerance policy, and known differences. `experimental` means the narrow
contract has parity evidence; it does not mean the broader R function is
implemented or production-ready.
