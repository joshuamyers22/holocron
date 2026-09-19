# Changelog

Notable changes are recorded here using semantic versioning.

## Unreleased

- Created the production repository scaffold for Holocron.
- Added the independent Python implementation project plan.
- Completed the private-development Phase 0 governance, threat, risk, and
  provenance records while retaining the external-distribution gate.
- Matched the local `rms-master` 8.2-0 tree to immutable upstream commit
  `a4e4a305a029090e737562fb4d35bdb705db7d63` and added a complete 363-file
  checksum manifest.
- Cataloged all 121 exports, 160 S3 methods, and six registered Fortran routines
  with owned compatibility dispositions.
- Selected `holocron-rms` as the prospective distribution name while retaining
  `holocron` as the import package.
- Added complete oracle package/runtime metadata and whole-tree build
  verification.
- Adapted the generated quantitative application scaffold into a typed
  scientific library with explicit `design`, `models`, and `exceptions` public
  namespaces.
- Removed template-only CLIs, market-data publication, generic regression and
  walk-forward examples, demo datasets, and their unused Polars/Statsmodels
  dependencies.
- Froze the canonical Python evidence environment to CPython 3.12.14 and uv
  0.12.7, including the complete development and non-isolated build toolchain.
- Added machine-checked Python and R environment manifests plus live validation
  of the accepted Docker oracle image identity and platform.
- Formalized versioned oracle case, output, tolerance-policy, and parity-evidence
  schemas; the Python and live R checks now share named field-aware comparison
  profiles and emit hashed evidence records.
- Expanded the Phase 1 oracle corpus to 25 statistical cases spanning spline
  design, OLS, binary logistic, ordinal, Cox, parametric survival, and
  Kaplan–Meier workflows; 12 design/OLS cases initially ran independent Python
  parity and 13 later-family cases were frozen as future baselines.
- Accepted ADR-009's float64 numerical envelope for RCS design and
  well-conditioned OLS after all 12 independent cases passed on macOS
  arm64/Accelerate and Ubuntu x86_64/OpenBLAS; added schema-validated pilot
  reports and a required cross-platform CI matrix.
- Added the initial strict MkDocs site with executable offline examples,
  source-generated API reference, and a generated 281-capability compatibility
  inventory; the ordinary quality gate rejects stale pages, invalid links, and
  documentation warnings.
- Added a clean artifact gate that builds and inspects wheel and source
  distributions offline, independently installs both into fresh environments,
  validates dependencies and checkout isolation, and smoke-tests the supported
  RCS-to-OLS workflow in CI and release jobs.
- Closed the private-development Phase 1 exit gate with a clean, repeatable
  design-to-fit-to-prediction workflow that compares against the pinned R
  oracle output, emits schema-valid hashed parity evidence, and retains it in CI.
- Added immutable data-distribution metadata with documented `datadist` summary
  and adjustment rules, explicit categorical ordering, labels and units,
  missingness counts, canonical serialization, and four pinned-R parity cases.
- Added an immutable allowlisted formula AST and deterministic numeric design
  compiler for identity, raw polynomial, linear-spline, and explicit-knot RCS
  terms, with bounded parsing, canonical serialization, adversarial-name tests,
  and four pinned-R design parity cases.
- Added explicit unordered and scored-ordered factor nodes, first-level
  reference coding with fail-closed unseen-level handling, and hierarchical
  two-way restricted interactions that omit doubly nonlinear products; four
  additional pinned-R cases qualify the generated values and metadata.
- Stabilized versioned schemas for reconstructible design specifications,
  realized design matrices, and OLS results; added strict bounded canonical JSON,
  design/result fingerprints, wrong-design prediction rejection, packaged schema
  assets, and the initial cross-version migration policy in ADR-008.
- Added deterministic exhaustive transformation tests with an independent scalar
  reference, full supported degree/knot/level cardinality coverage, all 36
  ordered restricted-interaction kind pairs, permutation/batching and spline-tail
  properties, and systematic fail-closed invalid-value checks.
- Completed the R design-specification migration guide with executable
  `datadist`-to-design-to-OLS reconstruction, a comprehensive concept map,
  matrix-level verification procedure, serialization guidance, and explicit
  stop conditions for unsupported `rms` behavior.
- Closed the private-development Phase 2 exit gate across all 18 independently
  implemented design-system parity cases, with aggregate schema-valid evidence,
  an adversarial-name requirement, exact serialized prediction reconstruction,
  estimator-promotion enforcement, and retained clean-CI evidence.
- Completed the first Phase 3 deliverable with owned Gaussian/identity and
  binomial/logit `Glm`, binary unpenalized `lrm`, structured convergence/rank/
  separation failures, strict binary-result serialization, seven direct new or
  promoted pinned-R parity cases, and the accepted numerical-backend policy.
- Completed the second Phase 3 deliverable with typed covariance, likelihood,
  residual, prediction, coefficient-summary, declared-term ANOVA, and linear-
  contrast operations; added three vertical OLS/Glm/lrm oracle cases, a named
  field-aware inference policy, installed-artifact smoke coverage, and explicit
  compatibility boundaries for broader `rms` behavior.
- Completed the third Phase 3 deliverable with diagonal quadratic penalties for
  OLS and binary `lrm`, named simple/sandwich penalty covariance, robust and
  clustered covariance, deterministic or seeded iid bootstrap covariance, three
  vertical pinned-R cases, installed-artifact coverage, and explicit fail-closed
  regularization and resampling boundaries.
- Completed the fourth Phase 3 deliverable with a schema-locked seven-scenario,
  2,620-replication simulation plan; recovery, coverage, calibration,
  discrimination, type-I-error, robust-covariance, bootstrap, and penalization
  reports; and a 16-case numerical edge corpus with clean revision-bound
  evidence and cross-platform CI execution.
- Completed the fifth Phase 3 deliverable with one CI-executed getting-started
  workflow spanning explicit metadata and design, OLS and binary `lrm`, named
  inference and future prediction, robust/bootstrap covariance, penalization,
  and strict JSON reconstruction, with adjacent interpretation and stop
  boundaries.
- Closed the private-development Phase 3 exit gate after 19 vertical cases
  passed 422 exact and 1,452 numeric pinned-R comparisons, all seven registered
  simulation scenarios and 16 numerical-edge cases passed, and independent
  statistical reviewer Ron Mexico approved the experimental alpha scope.
- Implemented the Phase 4 ordinal/censoring functional surface: five-link
  cumulative models, multi-intercept `lrm`, exact-grid Turnbull conversion,
  mixed-censoring likelihoods, bordered-tridiagonal information updates,
  escalating adaptive quadrature, single and dual-scale cluster effects,
  boundary inference, prediction/test diagnostics, strict result JSON, a
  64-level stress case, and installed-artifact smoke coverage. The Phase 4
  parity, simulation, cross-platform, and independent-review exit gate closed
  after Ron Mexico approved the private experimental scope.
- Completed the first Phase 5 deliverable with independent right-censored
  Efron/Breslow Cox, Weibull/exponential accelerated-failure-time, and
  unstratified Kaplan–Meier implementations; added typed survival prediction,
  strict result schemas, artifact smoke coverage, and six cases passing 190
  exact and 446 numeric pinned-R comparisons.
- Completed the second Phase 5 deliverable with Cox counting-process entry,
  strata, positive weights, offsets, per-stratum baseline hazard/survival, and
  martingale/deviance residuals; Weibull scale strata, weights, offsets, hazard
  prediction, and four residual kinds; and weighted stratified counting-process
  Kaplan–Meier curves. Three new vertical cases raise survival parity to 432
  exact and 721 numeric comparisons, while v2 result schemas retain tested v1
  migrations and packaged historical schemas.
- Completed the third Phase 5 deliverable with typed survival curves, Cox and
  Kaplan–Meier event-time quantiles and restricted means, and analytic Weibull/
  exponential quantiles and means. Three new cases raise survival parity to 509
  exact and 899 numeric pinned-R comparisons.
- Completed the fourth Phase 5 deliverable with an explicit `SurvivalResponse`
  contract and exact, left-, right-, and interval-censored Weibull/exponential
  AFT likelihoods. Two new cases raise survival parity to 579 exact and 1,019
  numeric pinned-R comparisons.
- Implemented the fifth Phase 5 deliverable with model-independent fixed-horizon
  IPCW Brier scores, cumulative/dynamic AUC and Dxy, Kaplan–Meier observed
  survival, marginal calibration error, and integrated Brier score. Two new
  cases raise survival parity to 599 exact and 1,071 numeric comparisons.
- Added the locked Phase 5 survival simulation gate: seven seeded scenarios and
  1,280 replications cover Cox recovery, ties, strata and offsets, right- and
  mixed-censored Weibull AFT recovery, Kaplan–Meier coverage, and censoring-
  adjusted validation accuracy. All thresholds pass with no failed replication;
  CI retains clean and macOS/Ubuntu platform reports while independent review
  and the Phase 5 exit gate remain open.
- Closed the Phase 5 private-development exit gate after Ron Mexico
  independently approved the survival likelihood, information, risk-set,
  censoring, prediction, validation, and simulation-threshold evidence on
  2026-09-18. Survival capabilities remain experimental and broader promotion
  and distribution gates remain separate.
- Completed the first Phase 6 deliverable with immutable exact bootstrap,
  repeated K-fold, and caller-declared resample plans; strict canonical JSON
  reconstruction and fingerprints; row-aligned selection; whole-procedure
  execution; explicit complete/partial/failed outcomes; bounded resource
  limits; and shared use by the existing bootstrap-covariance path.
- Completed the second Phase 6 deliverable for fixed realized designs with
  model-specific OLS and binary-logistic validation indices, parametric
  recalibration curves, fresh fits inside every exact split, retained
  training/assessment results, and fail-closed or explicitly partial outcomes.
  Aggregation, optimism correction, ordinal/survival methods, smooth
  calibration, and pinned-R method parity remain deferred.
- Completed the third Phase 6 deliverable with weighted model-independent
  binary-probability validation, including discrimination, Brier/log scores,
  likelihood-quality indices, logistic recalibration, Spiegelhalter testing,
  grouped calibration, and threshold metrics. Expanded right-censored
  survival validation with grouped Kaplan--Meier calibration, IPCW threshold
  metrics, integrated AUC, and integrated absolute calibration error. A new
  pinned `rms::val.prob` case passes 4 exact and 21 numeric comparisons.
- Completed the fourth Phase 6 deliverable with metric-wise optimism correction
  for retained OLS and binary-logistic training/assessment pairs and pointwise
  correction of their parametric calibration curves. Results retain the source
  plan fingerprint, completion status, failure rate, and pairwise contributor
  counts; partial executions fail closed unless explicitly allowed.
- Completed the fifth Phase 6 deliverable with exact OLS and one-step binary
  influence diagnostics, covariance-correlation VIFs, robust/model uncertainty
  comparisons, explicit bounded OLS/lrm penalty traces, and fresh-refit
  backward selection over caller-declared coefficient groups. These owned
  Python contracts remain separate from deferred R `vif`, `pentrace`, and
  `fastbw` compatibility claims.
