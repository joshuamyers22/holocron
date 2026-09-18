# Independent Python Implementation of `rms`: Production Project Plan

**Status:** Active — Phases 0–2 complete; Phase 3 core estimators and result operations accepted for private development
**Plan date:** 2026-09-17  
**Reference implementation:** Frank Harrell's R package `rms`  
**Project name:** `holocron`  
**Target:** A production-quality, independent Python scientific library with demonstrated statistical fidelity to the approved R `rms` reference release

## 1. Executive summary

The project will create an **independent Python implementation of `rms`** that reproduces the statistical behavior and integrated workflow of the R package without requiring R at runtime. “Independent” means Python-native architecture, original Python implementation code, an owned public API and result model, and no runtime delegation to R. It does not imply affiliation with or endorsement by the R package's author. The goal is not a thin wrapper around R, a collection of loosely related model calls, or a syntax-level imitation of R's S3 interface. The goal is a coherent Python library that preserves the important `rms` contract:

- model-design metadata travels with a fitted model;
- transformations, adjustment values, factor encodings, interactions, and knots remain reproducible;
- estimation, inference, prediction, contrasts, validation, calibration, and visualization agree with the reference implementation within pre-specified tolerances;
- users receive structured results with explicit assumptions, convergence states, and unsupported cases; and
- releases are reproducible, tested against a pinned R oracle, documented, traceable, and safe to install.

This is a multi-year scientific-software program, not an ordinary package port. The local `rms-master` snapshot exports more than one hundred symbols and has a large S3 method surface spanning linear, binary, ordinal, random-effects ordinal, survival, generalized least-squares, quantile, censored-response, validation, calibration, and graphics workflows. A credible full-fidelity effort requires statistical methodologists, numerical software engineers, independent verification, and a staged release strategy.

Phase 0 selected an isolated, independently authored implementation path. `rms`
is licensed GPL (version 2 or later), while Holocron currently remains private
and proprietary. The local `rms-master` tree is used to inventory observable
behavior, public interfaces, test scenarios, native numerical components, known
defects, and edge cases. It must not be mechanically translated or copied into
the Python implementation. ADR-001 approves private implementation work while
external distribution remains blocked pending qualified license/provenance
review. The longer-term distribution decision may select one of these controls:

1. **Source-informed, GPL-compatible implementation:** engineers may study the GPL source in detail, but Python code remains independently designed and written; any adapted material is identified, attributed, and handled under compatible terms; or
2. **Separated specification/implementation workflow:** source reviewers use `rms-master` to produce behavioral specifications and oracle cases, while implementers work from those specifications, public method literature, and black-box outputs rather than translating R or Fortran code.

In either path, the product remains an independent Python implementation rather
than an R bridge.

## 2. Source baseline and authority

### 2.1 Production engineering baseline

This plan applies the repository and scientific-Python practices from the local production template at commit `8879be48f3b760e65f6bed32f8740314fe92910d` (2026-09-16):

- [Production repository standard](../production-project-template/standards/PRODUCTION_REPOSITORY_STANDARD.md)
- [Python engineering guide](../production-project-template/docs/PYTHON_ENGINEERING_GUIDE.md)
- [Production blueprint](../production-project-template/docs/PRODUCTION_BLUEPRINT.md)
- [Scientific Python documentation guide](../production-project-template/docs/SCIENTIFIC_PYTHON_DOCUMENTATION_GUIDE.md)
- [Statistical analysis plan template](../production-project-template/templates/STATISTICAL_ANALYSIS_PLAN.md)
- [Repository setup checklist](../production-project-template/checklists/REPOSITORY_SETUP.md)
- [Release readiness checklist](../production-project-template/checklists/RELEASE_READINESS.md)
- [Agent working agreement](../production-project-template/AGENTS.md)

The repository was generated from the template's `python-data-quant` archetype
because it already contains reproducibility, numerical-boundary,
evidence-artifact, and statistical-review controls. The Phase 1 repository
adaptation removed application-only dataset and CLI examples, established a
typed scientific-library surface, and retained the applicable production
controls. See ADR-011.

### 2.2 Local `rms-master` statistical source baseline

The primary project source is the read-only local snapshot at [`/Users/josh/Downloads/rms-master`](../../Downloads/rms-master). The snapshot must be treated as reference material, not as the destination repository or a Python architecture template. Its authoritative entry points are:

- [`DESCRIPTION`](../../Downloads/rms-master/DESCRIPTION) for version, dependency, and license identity;
- [`NAMESPACE`](../../Downloads/rms-master/NAMESPACE) for exported functions and S3 methods;
- [`NEWS`](../../Downloads/rms-master/NEWS) for changed behavior and compatibility risks;
- [`man/`](../../Downloads/rms-master/man) for public contracts;
- [`inst/tests/`](../../Downloads/rms-master/inst/tests) for behavior scenarios and regression history;
- [`R/`](../../Downloads/rms-master/R) and [`src/`](../../Downloads/rms-master/src) for source-informed specification and numerical review under the approved provenance policy;
- [`orm-random-effects-methodology.md`](../../Downloads/rms-master/orm-random-effects-methodology.md) and [`orm-random-effects-implementation.md`](../../Downloads/rms-master/orm-random-effects-implementation.md) for the newly added ordinal random-effects model.

Snapshot facts verified on 2026-09-17:

- package version `8.2-0`, dated 2026-09-11;
- R 4.4 or later and Hmisc 5.3-0 or later;
- 102 R source files, 108 manual files, 129 files under `inst/tests`, eight
  top-level native source files, and one Ratfor source file;
- `DESCRIPTION` SHA-256 `0528cd8378601f0b05a6e6fb3daa89e8dfc6211adb82246c2f4eb7dec12ae23b`;
- `NAMESPACE` SHA-256 `db1cc94792cceaca300e00e38229580349b3d93ee18493f6097d7ae91f63ef6b`;
- `NEWS` SHA-256 `84cd6605bee5ec3c7314533e89f6a5bfb0429038140438462389ea1566f5c912`.

The snapshot is not a Git checkout, but it is byte-identical outside Git metadata
to upstream commit `a4e4a305a029090e737562fb4d35bdb705db7d63`. The deterministic
363-file manifest has digest
`40a3805d92ecd6bd1318db842c8c78e05595e48345b46c5e9e21ef01cd7a0bce`.
The snapshot's `CLAUDE.md` still names version 8.1-1; `DESCRIPTION` and `NEWS`
take precedence and establish version 8.2-0.

The random-effects implementation notes also warn that native `.f90`/`init.c` copies may become stale across development machines. Therefore, source inspection alone cannot establish executable behavior: the snapshot must be built, its routine registrations checked, and its `inst/tests` cases run in the pinned oracle environment. Upstream test scripts may identify scenarios and expected behavior, but they must not be copied into the Python suite unless the approved license/provenance policy permits it; project-authored cases should otherwise be written from the specification and observed outputs.

Supplement the local snapshot with these primary sources:

- [`rms` repository](https://github.com/harrelfe/rms)
- [`rms` package site](https://hbiostat.org/R/rms/)
- [`rms` CRAN documentation](https://cran.r-project.org/package=rms)
- *Regression Modeling Strategies*, second edition, and the maintained course notes
- primary papers cited for the implemented estimators, diagnostics, calibration methods, and performance measures

The local version 8.2-0 snapshot and matching immutable commit are the initial
specification baseline. No `8.2-0` upstream tag existed at Phase 0 verification,
so commit plus file manifest define the artifact. A moving upstream branch is not
an acceptable release oracle. Upstream `master` may be exercised separately as a
non-blocking compatibility canary.

### 2.3 Source-of-truth precedence

When sources disagree, use this order:

1. approved project requirements, ADRs, and statistical specifications;
2. executable parity cases against the pinned R reference environment;
3. cited mathematical definitions and primary method literature;
4. public `rms` documentation for the pinned version;
5. the local `rms-master` source and tests, only as permitted by the approved independent-development and license policy;
6. secondary tutorials and examples.

The book and documentation explain intent but do not by themselves define every numerical edge case. The R oracle supplies observed behavior, but an upstream defect is not automatically a behavior to preserve. Suspected defects require a parity-exception record and statistical review.

## 3. Product charter

### 3.1 Users

- biostatisticians and epidemiologists migrating established `rms` workflows;
- statistical programmers who need Harrell-style model development and validation in Python;
- researchers who need auditable regression, ordinal, and survival analysis;
- library authors who need structured design metadata and post-estimation operations;
- regulated or high-assurance teams that require reproducible numerical evidence.

### 3.2 Critical user journeys

1. Define predictor distributions and adjustment values.
2. Specify nonlinear effects, ordered predictors, stratification, and restricted interactions.
3. Fit a supported regression or survival model with explicit missing-data, weight, offset, and covariance semantics.
4. Obtain structured coefficients, uncertainty, model tests, diagnostics, and convergence information.
5. Compute predictions, contrasts, effect summaries, survival quantities, and uncertainty without reconstructing the original design manually.
6. Perform bootstrap or cross-validation optimism correction and model calibration using the entire modeling procedure inside each resample.
7. Generate publication-quality effect plots, calibration plots, survival plots, and nomograms from structured plot data.
8. Reproduce a result from source data, code revision, model specification, seed/resample identity, and locked environments.
9. Translate a documented R `rms` workflow into an explicitly mapped Python workflow and see any known behavioral difference.

### 3.3 Measurable success criteria

- Every exported symbol and S3 method in the pinned `rms` reference has a reviewed disposition in a versioned compatibility manifest: implemented, mapped to a Python-native equivalent, intentionally unsupported, or deferred.
- Every claimed compatible operation has differential tests against the pinned R oracle across ordinary, adversarial, and degenerate cases.
- Deterministic design transformations and metadata agree exactly after canonicalization or within a documented machine-precision tolerance.
- Model estimates, likelihoods, covariance matrices, predictions, contrasts, and derived quantities satisfy method-specific absolute and relative tolerance contracts established before final implementation acceptance.
- Stochastic validation and calibration agree either by using identical resample indices or by passing pre-specified Monte Carlo equivalence criteria.
- Simulation studies demonstrate expected bias, coverage, calibration, discrimination, and type-I-error behavior for each estimator family; parity on a few fixtures is insufficient.
- Clean installations, complete quality gates, documentation builds, wheel/sdist smoke tests, and release artifacts reproduce in CI from frozen dependencies.
- No stable release claims full compatibility while unresolved blocking parity exceptions remain in its advertised capability set.

### 3.4 Non-goals for the initial program

- Runtime delegation to R through `rpy2`, subprocesses, or a service.
- Independent implementation of the separate Bayesian `rmsb` package.
- Pixel-identical reproduction of base R, lattice, ggplot2, or Plotly output. The compatibility target is the statistical plot data and documented semantics.
- Preservation of R-specific language behavior when a clearer typed Python API is safer. Differences must be mapped and documented.
- Automatic causal interpretation, variable selection approval, or model adequacy certification.
- Silent fallback to a statistically different method when the requested method is unsupported.
- Optimization through compiled extensions before correctness profiles show a measured need.

## 4. Blocking decisions and ADRs

The following ADRs are required before their dependent work begins; accepted
records remain binding implementation constraints.

| ADR | Decision | Deadline | Blocks |
|---|---|---:|---|
| ADR-001 | Independent-development provenance, permitted use of `rms-master`, and compatible distribution license | End of Phase 0 | All implementation |
| ADR-002 | Distribution name, import name, trademarks/attribution, and repository owner | End of Phase 0 | Repository publication |
| ADR-003 | Immutable R reference version, dependency lock, container digest, and update policy | End of Phase 0 | Oracle fixtures and parity claims |
| ADR-004 | Compatibility definition: behavioral parity, API mapping policy, and versioning of differences | End of Phase 0 | Public API |
| ADR-005 | Formula/design engine: owned AST plus adapter strategy | Before Phase 2 | Transformations and all models |
| ADR-006 | Canonical table/array boundary and pandas interoperability | Before Phase 2 | Data ingestion and formulas |
| ADR-007 | Numerical backends and rules for using Statsmodels/SciPy versus owned solvers | Before first estimator | Estimation |
| ADR-008 | Model/result serialization and cross-version support policy | Before beta persistence | Persistence and evidence artifacts |
| ADR-009 | Supported Python, NumPy/SciPy, platforms, BLAS, and reproducibility envelope | Before public alpha | CI and support policy |
| ADR-010 | Release scope and precise meaning of `1.0` | Before beta | Public expectations |

The licensing ADR must also decide how the template's GPL-denying dependency check is adapted. Test-only R oracle components must be isolated from Python runtime distributions, and their licenses and notices must remain visible in the reference environment.

ADRs 001–004 and ADR-009 are accepted for private development. The distribution
gate in ADR-001 remains binding; acceptance is not legal clearance for
publication.

## 5. Scope and compatibility tiers

### 5.1 Compatibility manifest

Maintain `compatibility/rms-<version>.yaml` as the authoritative,
machine-readable mapping. Each entry includes:

- R symbol or S3 method;
- Python public entry point;
- capability tier and release milestone;
- supported model families and combinations;
- reference documentation and mathematical source;
- test case IDs and oracle artifact versions;
- tolerance profile;
- known differences and status;
- statistical and implementation owners.

CI must reject a public compatibility claim without a manifest entry and linked evidence. Documentation should generate the user-facing compatibility table from this manifest.

### 5.2 Tier A: design system and primary workflow

This tier establishes the integrated architecture on which every later feature depends.

- predictor summaries and adjustment values corresponding to `datadist`;
- design metadata and assignment behavior corresponding to `Design` and `DesignAssign`;
- `asis`, `pol`, `lsp`, `rcs`, `catg`, `scored`, `strat`, `matrx`, and `gTrans` behavior;
- restricted interactions and interaction metadata;
- stable labels, units, factor levels, reference values, and new-level policies;
- `ols`, `Glm`, binary `lrm`, and their core result operations;
- `predict`, `Predict`, `summary`, `anova`, `contrast`, `specs`, `vcov`, `residuals`, and likelihood-ratio operations for supported models;
- structured plotting data for effects and contrasts.

### 5.3 Tier B: ordinal and survival core

- ordinal `lrm` and `orm`, including supported cumulative probability families;
- `orm` single-cluster random intercepts, adaptive Gauss–Hermite quadrature, and the `mix_re` dual-scale random-effects specification added in the local 8.2-0 snapshot;
- correct marginal likelihoods, information matrices, variance-component boundary behavior, and clustered-null likelihood-ratio comparisons for random-effects models;
- censoring representations corresponding to `Ocens` and conversion helpers;
- the 8.2-0 exact-grid Turnbull/self-consistency behavior used when converting left-, right-, interval-, and mixed-censored outcomes for ordinal modeling;
- Cox proportional-hazards models corresponding to `cph`, including ties, strata, entry times, weights, offsets, and baseline quantities;
- parametric survival models corresponding to `psm`;
- nonparametric survival summaries corresponding to `npsurv`;
- survival, hazard, mean, quantile, exceedance-probability, and survival-curve operations;
- ordinal and survival diagnostics with structured statuses.

### 5.4 Tier C: validation, calibration, and robustness

- the reusable resampling engine corresponding to `predab.resample`;
- `validate` methods by supported estimator;
- `calibrate` methods for ordinary, binary, ordinal, Cox, and parametric survival models;
- `val.prob`, grouped calibration, `val.surv`, discrimination measures, and out-of-sample log likelihood;
- `bootcov`, `robcov`, influence diagnostics, VIF, and selected model-diagnostic functions;
- `pentrace`, penalties, effective degrees of freedom, and documented shrinkage behavior;
- `fastbw` only after its inferential limitations are prominently documented and parity-tested.

### 5.5 Tier D: extended models and presentation

- `Gls`, including the `corFloorExp` correlation structure, `Rq`, `bj`, and `pphsm` or documented Python-native replacements with equivalent estimands;
- nomograms based on structured scale/axis data;
- survival, calibration, hazard-ratio, ANOVA, validation, and residual plots;
- LaTeX/table rendering from structured results;
- multiple-imputation integration through an adapter, including variance-combination rules;
- code-generation helpers such as SAS/Perl output only if users still require them and security review approves them.

### 5.6 Full-parity exit condition

The program is not “complete” merely because the most popular models work. Full parity requires a reviewed disposition for the complete pinned namespace and S3 method inventory, including helpers that affect observable behavior. Intentionally unsupported R-specific presentation methods are acceptable only when the manifest identifies a supported Python replacement or explains why no replacement is appropriate.

## 6. Proposed architecture

### 6.1 Architectural principles

- Own the statistical contract and design metadata; do not expose a third-party fit object as the public result type.
- Keep formula parsing and design construction separate from numerical estimation.
- Keep deterministic policy pure and inject randomness, resample plans, plotting backends, and filesystem operations.
- Treat convergence, singularity, insufficient support, unsupported combinations, and unavailable quantities as distinct structured states.
- Avoid import-time I/O, ambient global options, mutable process-wide model configuration, and implicit network access.
- Preserve a narrow Polars/dataframe-interchange-to-NumPy boundary with explicit row identity, column order, dtype, categories, nulls, units, and ownership.
- Use float64 as the initial numerical contract. Any other dtype requires separate validation.
- Use factorizations and linear solves rather than explicit matrix inverses.

### 6.2 Suggested package structure

```text
src/<package>/
├── api/                 # stable user-facing fitting and post-fit entry points
├── design/              # distributions, terms, transformations, interactions
├── formula/             # allowlisted AST, parsing, term resolution, schemas
├── data/                # table adapters and explicit array boundaries
├── models/              # model-family specifications and public result types
├── backends/            # numerical estimator implementations/adapters
├── inference/           # covariance, tests, contrasts, robust/bootstrap methods
├── survival/            # censoring types and survival-specific quantities
├── validation/          # resampling, optimism correction, calibration, metrics
├── graphics/            # backend-neutral plot specifications and renderers
├── reporting/           # summaries, tables, LaTeX, evidence artifacts
├── compatibility/       # R-to-Python mapping and migration helpers
├── exceptions.py        # stable exception hierarchy
├── statuses.py          # warnings, convergence, support, and issue codes
└── _version.py
```

Reference-only infrastructure should remain outside the importable package:

```text
reference/
├── r/                   # project-authored oracle scripts, lock, and environment metadata
├── source-manifest/     # hashes and inventory for the local rms-master snapshot
├── cases/               # declarative input/specification cases
├── expected/            # reviewed, provenance-tagged compact oracle artifacts
└── schemas/             # versioned parity artifact schemas
```

### 6.3 Core domain objects

- `DataDistribution`: immutable predictor limits, adjustment values, labels, units, and categorical levels.
- `DesignSpec`: ordered terms, transformations, parameters, interactions, encodings, and generated-column identity.
- `ModelSpec`: response semantics, family/link, penalties, weights, offsets, strata, censoring, and solver policy.
- `FitResult`: coefficients, information/covariance access, log likelihood, convergence record, design identity, training-sample declaration, and version metadata.
- model-specific results such as `OrdinalFitResult`, `CoxFitResult`, and `ParametricSurvivalFitResult` only where they add genuine invariants.
- `PredictionResult`, `ContrastResult`, `ValidationResult`, `CalibrationResult`, and `PlotSpec`: structured, typed results; formatted text is never the only interface.
- `ResamplePlan`: explicit resample indices, method, random-generator identity, seed/state, strata, and failure policy.
- `ParityEvidence`: reference versions, input hash, case ID, tolerances, outputs, warnings, and disposition.

Fit objects must contain everything needed to reconstruct the design for supported post-fit operations. They must not depend on an ambient `datadist`-like global setting.

### 6.4 Formula and transformation safety

Do not evaluate arbitrary Python or R-like source. Use an allowlisted expression tree with registered transformations. The design engine must:

- preserve term, factor, level, and generated-column identity;
- retain knots, boundary behavior, normalization parameters, and nonlinear-column grouping;
- define categorical ordering, unseen-level behavior, and missingness explicitly;
- prevent duplicate or ambiguous generated names;
- encode restricted interactions as first-class design rules;
- support inspection and deterministic serialization;
- reject unsupported expressions with a precise error instead of silently changing the model.

Formulaic or Patsy may be used as a parser/backend only if their behavior passes the compatibility suite and the package retains ownership of the resulting design contract. A package-specific AST is preferred for critical `rms` semantics.

### 6.5 Backend strategy

Statsmodels, SciPy, NumPy, and specialized survival libraries may supply algorithms, but only behind owned adapters and only after parity qualification. For each estimator:

1. write the mathematical and behavioral specification;
2. compare candidate backends on parameterization, objective, ties, weights, offsets, penalties, covariance, failure behavior, and result precision;
3. accept a backend where it satisfies the contract;
4. otherwise implement the missing layer or estimator with independent references and focused numerical review;
5. retain an interchangeable test oracle, not a public backend switch that exposes inconsistent behavior.

Compiled extensions are optional later optimizations. Any extension must retain a tested pure-Python/NumPy/SciPy reference path unless an ADR justifies otherwise.

## 7. Statistical fidelity program

### 7.1 Reference environment

Build a digest-pinned Linux container containing:

- the approved R runtime;
- the exact `rms` source artifact and SHA-256;
- locked R dependencies, including Hmisc and survival;
- locale, timezone, RNG kind, thread counts, and BLAS/LAPACK identity;
- original project-authored oracle scripts;
- a machine-readable environment manifest.

Do not require this container for ordinary Python installation or the fast PR test lane. Use it for fixture generation, nightly differential tests, release qualification, and investigations.

### 7.2 Declarative parity cases

Each case should define:

- case ID and capability requirement;
- data-generation or fixture provenance and hash;
- response and predictor schemas, units, labels, factor order, and missingness;
- model/design specification;
- seed and exact resample indices where applicable;
- outputs to compare;
- expected warnings, errors, or convergence status;
- absolute/relative/statistical tolerance profile;
- source citations and reviewer.

Cases should cover, at minimum:

- continuous, binary, unordered categorical, ordered categorical, and matrix predictors;
- default and explicit knots, ties at knots, repeated values, and extreme ranges;
- interactions involving linear, nonlinear, categorical, and stratification terms;
- offsets, frequency/case weights, penalties, clusters, and robust covariance;
- complete data, approved missing-data paths, NaN, infinity, and invalid values;
- rank deficiency, quasi/complete separation, ill conditioning, sparse ordinal intercepts, and optimizer non-convergence;
- right, left, and interval censoring; delayed entry; tied event times; heavy censoring; and strata;
- clustered ordinal outcomes, single- and dual-scale random effects, boundary variance estimates, cluster-size imbalance, AGQ escalation, and within-cluster `mix_re` identifiability;
- empty/single-level factors, unseen prediction levels, duplicated names, and row reordering;
- small samples, high parameter-to-observation ratios, and large but bounded stress cases.

### 7.3 Comparison hierarchy

Compare the earliest meaningful layer first so downstream mismatches remain diagnosable:

1. input normalization and retained row identity;
2. predictor summaries and adjustment values;
3. term graph, knots, encodings, column order, and design matrix;
4. objective/deviance and score/information at fixed parameters;
5. fitted parameters and convergence record;
6. covariance/information and hypothesis tests;
7. predictions and derived quantities;
8. resampling summaries and calibration curves;
9. plot data and annotations;
10. formatted representations, with relaxed formatting-only compatibility.

### 7.4 Tolerance policy

Do not use one universal `allclose` threshold. Establish named profiles before accepting each model family. Initial engineering targets for well-conditioned float64 fixtures are:

- discrete metadata, categories, column order, and resample indices: exact;
- deterministic transformations: exact where algebra permits, otherwise approximately `1e-12` absolute/relative;
- objectives, coefficients, and predictions: approximately `1e-8` absolute and `1e-7` relative;
- covariance matrices and derived standard errors: approximately `1e-7` absolute and `1e-6` relative;
- tail probabilities: compare on an appropriate probability or log-probability scale;
- iterative smoothers and survival curves: method-specific grid and interpolation tolerances;
- stochastic summaries: identical resamples when possible; otherwise pre-specified Monte Carlo confidence bounds.

These are pilot targets, not permission to loosen checks until they pass. Phase 1 must calibrate them across platforms and condition numbers, then record the final profiles in an ADR. Every tolerance exception needs a numerical explanation and reviewer.

### 7.5 Simulation validation

Differential testing can faithfully reproduce a bug, so every estimator also requires simulation studies against known data-generating processes. Depending on the method, evaluate:

- bias and root mean squared error;
- confidence-interval coverage;
- type-I error under null models;
- calibration intercept/slope and prediction error;
- discrimination metrics;
- survival-function and quantile recovery;
- penalty and effective-degrees-of-freedom behavior;
- robustness to censoring, imbalance, separation, and misspecification;
- resampling optimism correction.

Simulation plans, replication counts, seeds, estimands, metrics, and acceptance regions must be approved before results are inspected. Retain aggregate evidence and enough per-replication detail to diagnose failures without committing excessive artifacts.

### 7.6 Metamorphic and property tests

Add tests for invariants that should hold independently of R output:

- row permutation with restored identity does not change a deterministic fit;
- reference-level changes transform parameters but preserve predictions;
- equivalent formula/design specifications produce the same linear predictor;
- predict-on-training-data agrees with fitted-value definitions;
- covariance matrices are symmetric and meet expected definiteness conditions;
- survival probabilities stay in `[0, 1]` and obey required monotonicity;
- quantiles are ordered where defined;
- confidence limits are ordered and transformed consistently;
- serialization round trips retain model/design identity;
- resample plans are reproducible and do not leak held-out observations;
- plots consume the same structured data returned to users.

### 7.7 Parity exceptions

Record every accepted difference in `compatibility/exceptions/<id>.md` with:

- affected capability and versions;
- minimal reproducer and oracle evidence;
- statistical consequence;
- whether the R behavior appears intentional, undocumented, or defective;
- Python decision and rationale;
- user-facing warning/documentation;
- approval and re-review trigger.

Silent deviations are release blockers.

## 8. Engineering quality system

### 8.1 Repository baseline

The generated repository should include:

- `src/` layout and standard `pyproject.toml` metadata;
- a resolver-generated `uv.lock` and frozen CI installation;
- `AGENTS.md`, `PROJECT_MEMORY.md`, `PROJECT_BRIEF.md`, `REPRODUCIBILITY.md`, `SECURITY.md`, `CONTRIBUTING.md`, and `CHANGELOG.md`;
- ADR, work-note, threat-model, statistical-analysis, improvement, and verification-loop templates;
- `Makefile` with a truthful `make check` gate;
- GitHub Actions with least-privilege permissions and full-SHA action pins;
- Dependabot or equivalent dependency/action updates;
- wheel and source-distribution builds;
- trusted PyPI publishing, provenance, checksums, and CycloneDX SBOMs;
- private vulnerability reporting and named response owners.

A runtime Docker image is unnecessary for a pure Python library. The R oracle container is a test/reproducibility asset, not the product runtime.

### 8.2 Toolchain

Initial defaults, subject to ADRs and license review:

- Hatchling build backend;
- `uv` for dependency resolution and locked environments;
- Ruff formatting and linting;
- Pyright strict mode for public boundaries and core policy;
- Pytest, Hypothesis, coverage, and mutation testing for selected high-risk numerical policy;
- NumPy and SciPy as core numerical dependencies;
- Polars or dataframe-interchange support at the canonical tabular boundary;
- optional pandas adapter isolated from the internal data model;
- Sphinx or MkDocs with generated API reference, executable examples, link checking, and warnings-as-errors.

Dependencies must be minimal, pinned by compatible ranges in package metadata and exact versions in development/release locks, license-audited, and exercised in lower/upper-bound compatibility jobs.

### 8.3 CI lanes

| Lane | Trigger | Required evidence |
|---|---|---|
| Fast | Every pull request | lint, format, types, unit/property tests, architecture rules, docs smoke, build |
| Numerical | Every pull request touching statistical code | focused golden cases, condition/rank cases, deterministic benchmarks |
| Oracle | Nightly and labeled pull requests | live differential tests against pinned R container |
| Simulation | Nightly/weekly by cost | registered operating-characteristic studies with retained summaries |
| Compatibility | Weekly | supported Python/OS/NumPy/SciPy matrix and optional adapters |
| Supply chain | Scheduled and release | dependency audit, licenses, secret scan, SBOM, artifact inspection |
| Release | Version tag | clean full gate, oracle suite, docs, wheels/sdist, install smoke, provenance |

Network access must not be required for the ordinary unit suite or documentation examples. Release candidates should install from built artifacts in clean environments, not from the source checkout.

### 8.4 Test layers

- unit tests for formulas, transformations, likelihood components, covariance operations, and errors;
- contract tests for table adapters, plot specs, serialization, and backend adapters;
- differential tests against R;
- property/metamorphic tests;
- statistical simulation tests;
- integration tests for complete model-to-validation workflows;
- documentation example tests;
- wheel/sdist installation and import smoke tests;
- performance and memory regression tests on representative fixed workloads;
- fuzz tests for the allowlisted formula parser and malformed serialized artifacts.

Coverage thresholds should follow risk. Core design and likelihood code requires near-complete branch coverage plus mutation/property evidence; presentation adapters need an appropriate lower threshold. A repository-wide percentage alone is not an acceptance argument.

### 8.5 Reproducibility artifact

Every consequential fit or validation operation should be able to emit a versioned evidence record containing:

- package and dependency versions;
- code revision when available;
- model and design specifications;
- ordered generated columns and hashes;
- sample declaration and retained-row identity hash;
- input identifiers/hashes supplied by the caller;
- family, link, covariance, weights, offsets, penalties, and missing-data policy;
- RNG/bit-generator and resample-plan identity;
- convergence and warning statuses;
- result schema version and output hash.

Do not put raw sensitive data into the evidence artifact.

## 9. Documentation and migration experience

Use separate documentation sections for installation, getting started, task guides, examples, API reference, interpretation/limitations, R migration, development, and releases.

Required initial guides include:

- migrating `datadist` and design transformations;
- fitting and interpreting OLS and binary logistic models;
- restricted cubic splines and tests of nonlinearity;
- predictions, contrasts, and adjustment values;
- internal validation and optimism correction;
- calibration without binning as the default explanation;
- ordinal-model semantics;
- Cox and parametric survival workflows;
- nomograms and their limitations;
- missing data and multiple-imputation boundaries;
- exact differences from the pinned R release.

Documentation rules:

- NumPy-style docstrings define shapes, units, defaults, missing values, warnings, errors, and fitted attributes.
- API signatures are generated from source.
- Every result object has a documented structured schema.
- Important interpretation limits appear beside the output, not only on a general disclaimer page.
- Maintained examples are deterministic, offline, bounded, and executed in CI.
- Plots state what is estimated, how uncertainty is computed, and what cannot be inferred.
- Migration pages map R idioms to supported Python idioms and link to parity evidence.
- The package must not call itself a drop-in replacement unless the compatibility manifest supports that specific claim.

## 10. Security, privacy, and misuse controls

The threat model should include:

- arbitrary-code execution through formula parsing, callbacks, or deserialization;
- denial of service through huge design expansions, pathological resampling counts, dense conversion, or adversarial model inputs;
- unsafe pickle/joblib model loading;
- malicious or malformed dataframe producers;
- dependency and build-chain compromise;
- leakage of sensitive row labels, formulas, or data through exceptions and evidence artifacts;
- misleading success when convergence, rank, censoring support, or calibration is inadequate.

Controls include:

- an allowlisted formula AST with no general `eval`;
- preflight limits for generated columns, interactions, prediction grids, and resamples;
- explicit dense/sparse conversion and memory estimates;
- safe, versioned serialization rather than implicit pickle as the supported exchange format;
- sanitized errors and no library telemetry by default;
- stable warning/status codes;
- dependency locks, audits, SBOMs, artifact provenance, and secret scanning;
- failure-closed behavior for unsupported statistical combinations.

## 11. Delivery phases and gates

Effort estimates are planning ranges, not commitments. They assume a core team of three scientific-Python engineers, two statistical methodologists, one numerical/test engineer, and part-time documentation, release, and legal support. Full parity is likely a 30–48 month program; a useful core release can arrive earlier without claiming complete compatibility.

### Phase 0 — Charter, legal path, and reference freeze (4–6 weeks)

**Status:** Complete for private development on 2026-09-17. External
distribution remains blocked, and vacant specialist-review roles prevent any
capability from advancing beyond `experimental`.

**Deliverables**

- approved project brief and governance model;
- ADR-001 through ADR-004;
- deterministic manifest of `/Users/josh/Downloads/rms-master`, immutable R reference artifact, and dependency/container manifests;
- complete namespace/S3 inventory and initial capability tiers;
- source/provenance policy and contributor attestation process;
- staffing, review ownership, budget, and release definitions;
- initial risk register and threat model.

**Exit gate**

Independent-development and license/provenance policy is approved; the reference environment can be rebuilt and hashed; every local-snapshot public symbol has an owner or triage status.

### Phase 1 — Repository and parity laboratory (6–10 weeks)

**Status:** Complete for private experimental development as of 2026-09-17
([completion record](governance/PHASE_1_COMPLETION.md)). Phase 2 is complete.

**Deliverables**

- [x] generated and adapted production repository;
- [x] frozen Python and R environments
  ([acceptance record](governance/PHASE_1_FROZEN_ENVIRONMENTS.md));
- [x] case schema, oracle runner, artifact schema, and field-aware comparator
  ([acceptance record](governance/PHASE_1_PARITY_LAB_CONTRACT.md));
- [x] 25 statistical oracle cases covering design, OLS, logistic, ordinal, and
  survival examples (12 independently implemented Python parity cases and 13
  frozen oracle baselines for later model-family implementation);
- [x] tolerance ADR based on a cross-platform pilot
  ([ADR-009](docs/adr/ADR-009-supported-numerical-envelope.md));
- [x] initial docs site and generated compatibility page
  ([acceptance record](governance/PHASE_1_DOCUMENTATION.md));
- [x] clean artifact build and smoke tests
  ([acceptance record](governance/PHASE_1_ARTIFACT_INSTALLATION.md)).

**Exit gate**

A minimal end-to-end slice generates a design, fits one simple model, predicts, emits evidence, and compares to R through repeatable CI.

**Disposition:** Passed. The clean CI gate executes the public RCS-to-OLS
prediction path, compares it to the pinned R output with the accepted
field-aware policy, writes schema-valid evidence, and retains that evidence as a
workflow artifact. See the [Phase 1 completion record](governance/PHASE_1_COMPLETION.md).

### Phase 2 — Design system (12–18 weeks)

**Status:** Complete for private experimental development. All six deliverables
and the evidence-emitting exit gate are accepted; capability promotion and
external distribution remain separately blocked.

**Deliverables**

- [x] data-distribution metadata
  ([acceptance record](governance/PHASE_2_DATA_DISTRIBUTION.md));
- [x] formula AST and core transformations
  ([acceptance record](governance/PHASE_2_FORMULA_DESIGN.md));
- [x] categorical/ordered handling and restricted interactions
  ([acceptance record](governance/PHASE_2_CATEGORICAL_INTERACTIONS.md));
- [x] stable design/result schemas and serialization draft
  ([acceptance record](governance/PHASE_2_SERIALIZATION.md));
- [x] exhaustive transformation differential/property tests
  ([acceptance record](governance/PHASE_2_TRANSFORMATION_TESTS.md));
- [x] R migration guide for design specifications
  ([acceptance record](governance/PHASE_2_R_MIGRATION_GUIDE.md)).

**Exit gate**

Tier A design cases, including adversarial naming and prediction reconstruction, pass the approved exact/tolerance contracts. No estimator is promoted while its design metadata is unstable.

**Disposition:** Passed. All 18 independently implemented data-distribution,
transformation, and formula-design cases pass 472 exact and 456 numeric checks
against the pinned R oracle. The gate requires adversarial names, exactly
reconstructs new-data predictions after strict JSON round trips, preserves the
design fingerprint, and confirms that no estimator was promoted. See the
[Phase 2 completion record](governance/PHASE_2_COMPLETION.md).

### Phase 3 — Linear, generalized, and binary logistic core (16–24 weeks)

**Status:** In progress. The first two deliverables are complete for the private
experimental envelope; penalties and robust/bootstrap covariance are next.

**Deliverables**

- [x] `ols`, `Glm`, and binary `lrm` equivalents
  ([acceptance record](governance/PHASE_3_CORE_ESTIMATORS.md));
- [x] covariance, likelihood, residual, prediction, summary, ANOVA, and contrast
  operations
  ([acceptance record](governance/PHASE_3_RESULT_OPERATIONS.md));
- penalties and robust/bootstrap covariance for supported models;
- simulation reports and numerical edge-case corpus;
- complete getting-started workflow.

**Exit gate**

Registered parity and simulation thresholds pass; convergence/rank/separation failures are structured and documented; independent statistical review approves alpha scope.

### Phase 4 — Ordinal regression and censoring model (20–32 weeks)

**Deliverables**

- multi-intercept `lrm` and `orm` families;
- sparse/banded information handling where needed;
- single random-intercept `orm`, adaptive Gauss–Hermite quadrature with convergence escalation, and `mix_re` dual-scale random effects;
- boundary-aware variance-component inference and the correct clustered-null comparison for model likelihood-ratio tests;
- ordinal probabilities, means, quantiles, exceedance probabilities, tests, and diagnostics;
- left-, right-, interval-, and mixed-censoring representations plus Turnbull/self-consistency conversion behavior;
- scale and stress evidence for many response levels.

**Exit gate**

Ordinal, clustered random-effects, and censored cases pass parity, operating-characteristic, quadrature, sparsity, and failure-mode gates. Memory growth, conditioning limits, and unsupported random-effects/y-dependent-effect combinations are published.

### Phase 5 — Survival models (24–36 weeks)

**Deliverables**

- `cph`, `psm`, and `npsurv` equivalents;
- ties, strata, entry times, weights, offsets, baseline survival/hazard, and residuals;
- survival, hazard, mean, quantile, and curve prediction APIs;
- right/left/interval censoring coverage where defined by the selected model;
- time-dependent validation primitives.

**Exit gate**

Survival parity suite and simulations pass across censoring/tie/strata regimes; numerical reviewers approve likelihood and information implementations.

### Phase 6 — Validation, calibration, diagnostics, and model summaries (18–28 weeks)

**Deliverables**

- common resampling engine with exact resample plans;
- model-specific `validate` and `calibrate` behavior;
- probability and survival validation metrics;
- optimism-corrected performance and calibration;
- influence, robustness, VIF, penalty tracing, and supported selection helpers;
- failure-rate and partial-resample reporting.

**Exit gate**

Whole-procedure refitting is proven inside each resample; stochastic equivalence and failure policies pass; examples prevent common leakage and apparent-calibration errors.

### Phase 7 — Graphics, nomograms, reporting, and documentation (16–24 weeks)

**Deliverables**

- backend-neutral plot specifications;
- effect, contrast, ANOVA, validation, calibration, survival, and diagnostic renderers;
- nomogram geometry and renderer;
- structured tables and LaTeX output;
- task-oriented documentation and tested galleries;
- accessibility and visual-regression checks for supported renderers.

**Exit gate**

Plot source data passes parity; renderers pass semantic and accessibility checks; every supported workflow has executable documentation with interpretation boundaries.

### Phase 8 — Extended models and namespace completion (24–40 weeks)

**Deliverables**

- `Gls`, `Rq`, `bj`, `pphsm`, and remaining exported helpers or approved replacements;
- multiple-imputation adapter;
- complete namespace disposition;
- performance tuning driven by retained profiles;
- migration tooling and deprecation policy.

**Exit gate**

The compatibility manifest has no unreviewed entries. Deferred or unsupported entries have approved rationale and user-facing alternatives.

### Phase 9 — Stable release qualification (10–16 weeks)

**Deliverables**

- release candidate series and external beta feedback;
- clean full-matrix builds and artifact installation evidence;
- independent statistical, numerical, security, API, and documentation reviews;
- completed release-readiness checklist;
- signed/traceable artifacts, SBOM, provenance, changelog, and support policy;
- incident, vulnerability, rollback/yank, and compatibility-response procedures.

**Exit gate**

All advertised capabilities meet their evidence contracts; no blocking parity/security/statistical findings remain; accountable maintainers approve the exact tagged commit.

## 12. Release strategy

- `0.1`–`0.x`: design and estimator previews; APIs may change; capability claims are narrow and manifest-backed.
- `1.0`: stable core workflow only if ADR-010 defines it precisely. It must not imply complete namespace parity unless that is true.
- later minor releases: additive, parity-qualified capabilities with migration notes.
- major releases: intentional API/statistical contract changes.
- patch releases: defects that do not intentionally change the public statistical contract; numerical changes still require parity evidence.

Maintain two upstream tracks:

- **Pinned compatibility line:** the immutable R release against which a Python release makes claims.
- **Upstream canary:** periodic tests against current `rms` development. Failures create triage issues but do not silently change the stable contract.

When adopting a newer reference version, publish a compatibility report, changed-default review, new oracle digest, fixture migration, and versioned exception assessment.

## 13. Governance and review

### 13.1 Required roles

- product/maintainer owner;
- statistical architecture lead;
- model-family statistical owners;
- numerical methods lead;
- Python/API lead;
- verification and release owner independent of the implementation owner for high-risk changes;
- security/supply-chain owner;
- documentation and migration owner;
- legal/license reviewer for the implementation path.

### 13.2 Change control

Any change to a likelihood, parameterization, default knot/adjustment rule, covariance, resampling procedure, calibration method, warning threshold, or serialized schema requires:

- a linked requirement or defect;
- before/after parity and simulation evidence;
- an ADR when the contract changes;
- statistical and numerical review;
- documentation and compatibility-manifest updates in the same change;
- an explicit release-note classification.

An implementation author may not be the sole approver of a statistical acceptance exception or release.

### 13.3 Definition of done for a capability

A capability is complete only when:

- its mathematical and behavioral specification is approved;
- its compatibility entry and known differences are current;
- public types, errors, warnings, and statuses are documented;
- unit, property, differential, edge-case, and applicable simulation tests pass;
- deterministic and stochastic reproducibility are addressed;
- performance and memory are bounded for declared input sizes;
- examples execute offline from the built artifact;
- dependency/license/security review passes;
- an independent reviewer approves the evidence.

## 14. Principal risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| GPL/provenance conflict | Distribution must stop or be relicensed | Approve independent-development controls in Phase 0; prohibit unreviewed translation; preserve provenance; legal review; isolate oracle |
| Hidden dependency on Hmisc semantics | Apparent `rms` parity fails in design/post-fit behavior | Inventory transitive observable behavior; include Hmisc versions in oracle |
| Backend parameterization mismatch | Plausible but statistically different results | Fixed-parameter objective/score tests before fitted-result tests; owned adapters |
| Overfitting fixtures to R outputs | Golden cases pass while methods are wrong | Simulation, metamorphic tests, literature-derived analytic cases |
| Numerical instability | Platform-dependent coefficients or invalid uncertainty | conditioning/rank policy, stable factorizations, sparse methods, adversarial matrices |
| Scope underestimation | Partial package marketed as complete | capability manifest, tiered releases, explicit staffing and exit gates |
| R global-state semantics leak into Python | Non-reproducible, thread-unsafe behavior | immutable explicit contexts stored in fits; no ambient global design state |
| Formula execution vulnerability | Arbitrary code execution | allowlisted AST; parser fuzzing; no general evaluation |
| Unsafe serialization | Code execution or silent model drift | non-executable versioned format; strict schema validation; no supported arbitrary pickle loading |
| Resampling leakage | Optimistic validation/calibration | resample the whole procedure; exact plan tests; retained per-resample evidence |
| Upstream evolution | Compatibility claims become ambiguous | pinned reference line plus non-blocking head canary and explicit upgrades |
| Maintainer concentration | Bus-factor and review weakness | CODEOWNERS by model family, contributor guide, independent release ownership |

## 15. Initial epic backlog

1. **E00 — Governance and license:** charter, ADRs, repository identity, attribution, contribution provenance.
2. **E01 — Local source inventory:** `rms-master` manifest, namespace/S3 catalog, Hmisc behavior dependencies, compatibility manifest generator.
3. **E02 — Reference oracle:** R container, lock, case schema, output normalizer, comparator.
4. **E03 — Python production skeleton:** generated repository, CI, locks, docs, artifact/release pipeline.
5. **E04 — Data and design contracts:** table boundary, distribution metadata, formula AST, transformations, interactions.
6. **E05 — Core results and evidence:** typed results, statuses, errors, serialization, reproducibility record.
7. **E06 — Linear and GLM estimators:** OLS/GLM likelihoods, covariance, prediction, diagnostics.
8. **E07 — Logistic and ordinal estimators:** binary/multi-intercept likelihoods, censoring, clustered random effects, AGQ, sparse information, derived quantities.
9. **E08 — Survival estimators:** Cox, parametric, nonparametric, censoring, survival quantities.
10. **E09 — Inference and post-estimation:** ANOVA, summary, contrasts, likelihood tests, robust/bootstrap covariance.
11. **E10 — Validation and calibration:** resampling engine, optimism correction, calibration, metrics.
12. **E11 — Graphics and reporting:** plot specs, renderers, nomograms, tables, LaTeX.
13. **E12 — Extended models:** GLS, quantile regression, Buckley–James, partial proportional hazards, MI adapter.
14. **E13 — Documentation and migration:** task guides, examples, R mapping, differences, citations.
15. **E14 — Release and operations:** compatibility matrix, supply chain, RC program, support and incident procedures.

Every epic should be decomposed into vertical, reviewable capabilities rather than layers that cannot be exercised end to end.

## 16. First 30 days

1. Appoint the maintainer, statistical lead, numerical lead, and license reviewer.
2. Approve the independent-development policy, distribution license, and permitted use of the GPL `rms-master` source; direct mechanical translation remains prohibited unless explicitly licensed and reviewed.
3. Select the canonical distribution/import name and repository owner after checking package-index and trademark conflicts.
4. Create the full file manifest for `/Users/josh/Downloads/rms-master`, then freeze and hash the matching R reference release and its dependencies.
5. Generate the complete namespace/S3 manifest from the pinned source.
6. Choose 20–30 representative vertical cases from design through prediction/validation.
7. Write ADRs 001–004 and the project brief.
8. Generate the repository from the production template only after the license path is approved.
9. Build the R oracle container and one end-to-end parity case.
10. Run an architecture/tolerance pilot for `datadist` + `rcs` + OLS + prediction.
11. Re-estimate staffing and milestone ranges from the pilot evidence.

## 17. Approval record

- Product owner: joshuamyers22
- Statistical lead: vacant; required before capability promotion
- Numerical lead: vacant; required before capability promotion
- Python/API lead: joshuamyers22 (acting)
- Verification owner: vacant; must be independent before capability promotion
- License reviewer: vacant; required before external distribution
- Approved reference release and digest: `rms` 8.2-0 at
  `a4e4a305a029090e737562fb4d35bdb705db7d63`, file-manifest SHA-256
  `40a3805d92ecd6bd1318db842c8c78e05595e48345b46c5e9e21ef01cd7a0bce`
- Selected implementation/license path: independently authored Python with an
  isolated test-only R oracle; private proprietary development; external
  distribution blocked pending qualified review
- Approved repository and package names: Holocron project,
  `joshuamyers22/holocron` repository, `holocron` import, `holocron-rms`
  prospective distribution
- Decision date: 2026-09-17
