# Changelog

Notable changes are recorded here using semantic versioning.

## Unreleased

- Added the fail-closed Phase 9 artifact-installability matrix for Ubuntu 24.04
  and macOS 15 across CPython 3.11 and 3.12. Every clean cell builds and inspects
  wheel/sdist, independently installs both formats, runs dependency and broad
  public-API smoke checks, and retains schema-valid revision/digest-bound
  evidence for 90 days. The deliverable awaits its first complete CI run.
- Added the fail-closed Phase 9 release-candidate and external-beta evidence
  process for a future `1.0.0rcN` series. Strict schemas and semantic checks
  require two distinct candidates, exact per-candidate distribution approval,
  three independent external reviewers, five-workflow coverage, accepted-final-
  candidate feedback, and resolved blocker/high findings. The truthful initial
  registry contains no candidates or feedback and remains blocked by ADR-010,
  qualified license/provenance approval, and external cohort recruitment.
- Closed the Phase 8 private-development exit gate after an accountable
  technical review confirmed all five deliverables, final dispositions for all
  281 namespace entries, zero deferred entries, public migration paths,
  approved unsupported rationales and alternatives, passing retained-profile
  budgets, the 26-test focused suite, the 216-test full gate, and isolated
  wheel/sdist installation. The decision claims no independent approval,
  mapped-behavior parity, capability promotion, consequential-use authority,
  external-distribution authority, or stable-release approval.
- Completed Phase 8 migration tooling and deprecation policy with an installed
  281-entry catalog, typed exact/raw-symbol planning, strict serialized plans,
  Markdown/JSON reporting, artifact smoke coverage, and an enforceable registry
  requiring visible warnings, replacements, changelog guidance, two minor
  releases, and 90 days before ordinary public API removal.
- Completed retained-profile performance tuning with five deterministic
  validation and survival workloads, raw `cProfile` retention, structural call
  and peak-memory budgets, cross-platform CI evidence, and bounded nested-risk-
  set acceleration for ordinary Cox fits while preserving delayed-entry behavior.
- Completed the Phase 8 namespace disposition across all 281 pinned exports and
  S3 methods: 50 remain evidence-backed experimental capabilities, 125 have
  approved Python-native mappings, and 106 are explicitly unsupported with
  family-level alternatives; removed all deferred and generic placeholder
  entries and added machine-enforced review metadata and public-path checks.
- Completed the Phase 8 multiple-imputation adapter with Rubin pooling for OLS
  and binary-logistic fits, pooled optimism-corrected validation and calibration,
  explicit Chan–Meng likelihood-ratio adjustment, typed information tables,
  strict schemas, and packaged artifact smoke coverage; mapped `processMI`,
  `prmiInfo`, and `processMI.fit.mult.impute` to the bounded Python contracts.
- Completed the first Phase 8 deliverable with bounded Python-native mapped
  replacements for fixed-covariance `Gls`, single-quantile `Rq`, right-censored
  Buckley–James `bj`, and one-scale Weibull/exponential `pphsm`; added immutable
  typed results, strict canonical schemas, prediction and failure-mode tests,
  and approved mappings or unsupported rationales for the remaining Phase 8
  exports while retaining `processMI`/`prmiInfo` for the next deliverable.
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
- Completed the sixth Phase 6 deliverable with typed resample reports that
  retain exact successful/failed split IDs, counts and rates, grouped bounded
  failure reasons, optional per-metric planned/successful coverage, and an
  explicit complete-only or allow-partial aggregation disposition. Partial
  executions remain partial, and all-failed executions never permit aggregation.
- Closed the Phase 6 private-development exit gate after an accountable
  technical review passed whole-procedure refitting, exact materialized-plan
  replay, failure-policy, leakage-warning, focused-test, full-check, and
  installed-artifact criteria. The decision claims no independent approval and
  does not promote capabilities beyond experimental.
- Completed the first Phase 7 deliverable with a new `holocron.graphics`
  namespace for immutable backend-neutral plot specifications: numeric and
  categorical axes, line/point/band/bar/interval layers, semantic annotations
  and metadata, legend ordering, required alternative text, and strict
  canonical JSON. No renderer, graphics dependency, or R graphics parity is
  introduced.
- Completed the second Phase 7 deliverable with typed adapters for effects,
  contrasts, ANOVA, probability/survival validation, calibration, survival
  curves, and current diagnostics, plus a dependency-free renderer for bounded
  accessible inline SVG. Semantic and accessibility-contract tests do not yet
  constitute pixel-baseline, browser-certification, or R graphics parity.
- Completed the third Phase 7 deliverable with strict backend-neutral nomogram
  geometry for additive identity-bound OLS and binary-logistic models. The
  shared-points identity reconstructs model predictions, geometry has canonical
  JSON/schema identity, and an owned accessible SVG renderer covers predictor,
  total-points, and response axes. Interactions fail explicitly; no R nomogram
  parity is claimed.
- Completed the fourth Phase 7 deliverable with a new `holocron.reporting`
  namespace for bounded typed raw-value tables, strict canonical JSON/schema
  identity, result adapters spanning supported inference, validation,
  resampling, and diagnostic objects, and safe deterministic dependency-free
  LaTeX output. No R `latex.*` layout or oracle parity is claimed.
- Completed the fifth Phase 7 deliverable with five deterministic offline
  galleries for effects/inference, validation/calibration, survival,
  diagnostics, and nomogram/reporting tasks. A strict manifest and docs gate
  require exact gallery/navigation coverage, one coherent executable workflow,
  interpretation and boundary sections, and every declared result/rendering
  output. Structural accessibility and renderer regression were intentionally
  left to the subsequent assurance deliverable.
- Completed the sixth Phase 7 deliverable with a fail-closed structural SVG
  accessibility audit, higher-contrast semantic colors, stable non-color dash
  cues, outlined translucent marks, and five exact human-reviewable golden SVGs
  spanning every plot layer, all axis scale kinds, both categorical
  orientations, annotations/legends, and nomograms. The gate is canonical SVG
  assurance, not browser, rasterization, assistive-technology, WCAG, or R
  graphics certification.
- Closed the Phase 7 private-development exit gate after an accountable
  technical review passed plot-source preservation within capability-level
  parity boundaries, renderer semantics/accessibility, five canonical SVG
  fixtures, five manifest-bound executable galleries, the 31-test focused
  suite, the 189-test full gate, and clean wheel/sdist installation. The
  decision claims no independent approval, R presentation-method parity,
  browser/WCAG certification, capability promotion, consequential-use
  authority, or external-distribution approval.
