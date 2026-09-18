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
  Kaplan–Meier workflows; 12 design/OLS cases run independent Python parity and
  13 later-family cases are labeled frozen oracle baselines.
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
