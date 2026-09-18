# holocron Project Memory

This is a bounded retrieval index for durable project knowledge. It is not an
activity log, task tracker, transcript, or source of truth. Verify every entry
against the linked implementation, test, issue, or decision record before acting.

Do not record secrets, personal data, client data, hidden reasoning, or other
restricted material. Consult an existing key before editing and update it in
place. Remove stale entries and resolved work instead of preserving a narrative;
Git history provides the audit trail.

## Durable constraints

| Key | Constraint | Evidence | Last verified |
|---|---|---|---|
| `independent-python` | Holocron is an independent Python implementation of `rms`, not a runtime R bridge or thin wrapper. | `README.md`; `PROJECT_PLAN.md` | 2026-09-17 |
| `distribution-gate` | Holocron remains private and may not be distributed until its final license and provenance review is approved. | `docs/adr/ADR-001-independent-oracle.md` | 2026-09-17 |
| `reference-snapshot` | Local `rms-master` 8.2-0 is byte-identical to upstream commit `a4e4a305a029090e737562fb4d35bdb705db7d63`; all 363 files are covered by a deterministic manifest. | `REFERENCE_SOURCE.md`; `reference/manifests/` | 2026-09-17 |

## Accepted decisions

| Key | Decision and rationale | Evidence | Last verified |
|---|---|---|---|
| `production-template` | The repository was generated from the production template's `python-data-quant` archetype, then adapted into a typed scientific library; reusable controls remain while the template CLIs, market-data publisher, generic analysis/validation flows, and demo data were removed. | `docs/adr/ADR-011-production-scaffold-adaptation.md`; `docs/architecture/PACKAGE_STRUCTURE.md` | 2026-09-17 |
| `docker-oracle` | R `rms` runs only in a pinned Docker oracle with JSON I/O; Python implementation code is original and R is not a runtime dependency. | `docs/adr/ADR-001-independent-oracle.md`; `reference/r/` | 2026-09-17 |
| `package-identity` | Holocron uses repository/project name `holocron`, import name `holocron`, and prospective distribution name `holocron-rms` because `holocron` is occupied on PyPI. | `docs/adr/ADR-002-project-and-package-identity.md`; `pyproject.toml` | 2026-09-17 |
| `compatibility-contract` | Compatibility is claimed per manifest entry; all 121 exports and 160 S3 methods have an owner/status, and only evidence-backed entries may advance beyond experimental. | `docs/adr/ADR-004-compatibility-contract.md`; `compatibility/rms-8.2.0.yaml` | 2026-09-17 |
| `release-gate` | Tag-triggered release jobs fail closed unless the repository variable `EXTERNAL_DISTRIBUTION_APPROVED` is exactly `true`; setting it requires the distribution review recorded by governance. | `.github/workflows/release.yml`; `governance/GOVERNANCE.md` | 2026-09-17 |
| `numerical-envelope` | ADR-009 accepts the current RCS-design and well-conditioned OLS profiles for float64 under CPython 3.12.14/NumPy 2.5.3 on macOS 15 arm64 with Accelerate and Ubuntu 24.04 x86_64 with OpenBLAS. Other model-family profiles remain provisional, and installability outside the matrix is not a parity claim. | `docs/adr/ADR-009-supported-numerical-envelope.md`; `governance/evidence/tolerance-pilot/`; `.github/workflows/ci.yml` | 2026-09-17 |
| `design-boundaries` | Holocron owns an immutable allowlisted formula/design contract and uses an ordered mapping of named iterables as its dependency-neutral baseline data boundary; dataframe libraries may only be explicit adapters. | `docs/adr/ADR-005-formula-design-engine.md`; `docs/adr/ADR-006-canonical-data-boundary.md` | 2026-09-17 |
| `serialization` | Supported persistence is strict bounded canonical JSON, never arbitrary pickle. Published schema versions retain meaning; breaking changes require a new version, and old-version support requires explicit tested migrations. SHA-256 fingerprints identify canonical documents but are not signatures. | `docs/adr/ADR-008-model-result-serialization.md`; `schemas/serialization-manifest.json` | 2026-09-18 |

## Non-obvious current state

| Key | State worth retrieving later | Evidence | Last verified |
|---|---|---|---|
| `first-slice` | Explicit-knot restricted cubic spline design and classical full-rank OLS pass deterministic parity fixtures from the live rms 8.2-0 oracle. | `src/holocron/design/splines.py`; `src/holocron/models/linear.py`; `reference/expected/` | 2026-09-17 |
| `phase-0` | Phase 0 repository deliverables are complete for private development; vacant statistical, numerical, verification, and license-review roles block capability promotion and external distribution. | `PROJECT_PLAN.md`; `governance/GOVERNANCE.md` | 2026-09-17 |
| `phase-1-exit-gate` | Phase 1 is complete for private experimental development. Clean CI executes the named RCS-to-OLS prediction slice, compares it with the pinned R output, emits schema-valid hashed evidence, and retains the evidence as a workflow artifact. Distribution and capability-promotion blocks remain. | `governance/PHASE_1_COMPLETION.md`; `.github/workflows/ci.yml`; `tools/run_phase_1_vertical_slice.py` | 2026-09-17 |
| `public-api` | The installed package has no CLI; its root exposes only version plus `design`, `formula`, `models`, and `exceptions`, and domain `__all__` declarations define the supported public names. | `src/holocron/__init__.py`; `docs/architecture/PACKAGE_STRUCTURE.md`; `tests/test_public_api.py` | 2026-09-17 |
| `frozen-environments` | The canonical Python evidence environment is CPython 3.12.14 with uv 0.12.7 and a hashed dependency/build lock; the separate R oracle is frozen by source/base/repository identities, full health evidence, Linux/arm64 platform, and image ID. Static checks run in CI; oracle rebuilds require live identity and behavior checks. | `governance/PHASE_1_FROZEN_ENVIRONMENTS.md`; `docs/adr/ADR-012-frozen-environment-contract.md`; `environments/` | 2026-09-17 |
| `parity-lab-contract` | Oracle cases, expected outputs, named field-aware tolerances, and emitted parity evidence use versioned JSON schemas. Exact comparison is the default; approximate rules are allowlisted by field path and shared by Python and live-R checks. | `governance/PHASE_1_PARITY_LAB_CONTRACT.md`; `schemas/`; `reference/contracts.py` | 2026-09-17 |
| `phase-1-corpus` | The oracle corpus has 25 statistical cases across RCS design, OLS, binary logistic, ordinal, Cox, parametric survival, and Kaplan–Meier workflows, plus environment health. Twelve design/OLS cases have independent Python parity; 13 later-family cases are explicitly frozen oracle baselines, not parity claims. | `reference/cases/`; `reference/expected/`; `governance/PHASE_1_PARITY_LAB_CONTRACT.md` | 2026-09-17 |
| `documentation-contract` | The strict MkDocs site executes marked offline examples and rejects broken internal links or stale generated API/compatibility pages; the full compatibility page is derived from the authoritative 281-entry manifest. | `mkdocs.yml`; `tools/generate_docs.py`; `governance/PHASE_1_DOCUMENTATION.md` | 2026-09-17 |
| `artifact-installation-gate` | CI and release builds require a clean checkout, build wheel and sdist offline from the frozen backend, inspect contents, install each into a distinct fresh environment, and run the supported RCS-to-OLS workflow without checkout leakage. | `tools/build_and_smoke_artifacts.py`; `governance/PHASE_1_ARTIFACT_INSTALLATION.md`; `.github/workflows/ci.yml` | 2026-09-17 |
| `data-distribution` | Phase 2 data-distribution metadata is complete for the experimental envelope: immutable numeric/categorical summaries, adjustment rules, labels/units, missingness counts, extension/override operations, canonical serialization, and four pinned-R parity cases. It does not provide ambient global state or a dataframe adapter. | `governance/PHASE_2_DATA_DISTRIBUTION.md`; `src/holocron/design/distributions.py`; `reference/cases/datadist-*.json` | 2026-09-17 |
| `formula-design` | The Phase 2 allowlisted formula/design compiler supports explicit numeric, unordered categorical, scored-ordered, and hierarchical two-way restricted-interaction terms. Parsing never evaluates source; levels/reference order are explicit, unseen values fail closed, and doubly nonlinear products are omitted. Its deterministic suite exhausts all declared degree/knot/level cardinalities and all 36 ordered interaction-kind pairs against an independent scalar reference; 14 frozen R transformation/design cases remain the cross-language authority. | `governance/PHASE_2_FORMULA_DESIGN.md`; `governance/PHASE_2_CATEGORICAL_INTERACTIONS.md`; `governance/PHASE_2_TRANSFORMATION_TESTS.md`; `tests/test_transformation_properties.py`; `reference/cases/design-*.json` | 2026-09-18 |
| `design-result-schemas` | Stable schemas cover distributions, formulas, reconstructible design specs, realized matrices, and OLS results. Matrices and matrix-fitted OLS results retain the design-spec fingerprint; exact-version readers reject malformed, oversized, non-finite, duplicate-key, unknown-field, and inconsistent documents. Public schema assets ship in wheel and sdist. | `governance/PHASE_2_SERIALIZATION.md`; `schemas/`; `src/holocron/_serialization.py` | 2026-09-18 |

## Verified traps and failed approaches

| Key | Symptom and cause | Evidence or reproducer | Last verified |
|---|---|---|---|
| `hmisc-version` | Rocker's R 4.5.3 repository snapshot contains Hmisc 5.2-5, but rms 8.2-0 requires >=5.3-0; the oracle installs Hmisc 5.3-0 from pinned commit `778bd69d83961577be1f73fa1e36781bd3fd099f`. | `reference/r/Dockerfile`; `reference/expected/oracle-environment.json` | 2026-09-17 |
| `npsurv-estimator-forwarding` | `rms::npsurv` 8.2-0 does not forward `...` to `survival::survfit`, so a requested alternate estimator would silently remain Kaplan–Meier; the Phase 1 oracle exposes Kaplan–Meier only. | `reference/r/oracle.R`; `reference/cases/npsurv-*.json` | 2026-09-17 |
| `hatch-editable` | Hatchling's non-isolated editable build additionally requires `editables`; both are explicit exact development dependencies so no hidden build resolution occurs. | `pyproject.toml`; `uv.lock`; `Makefile` | 2026-09-17 |

## Open threads

| Key | Unresolved question or next evidence | Owner | Review by |
|---|---|---|---|
| `distribution-license` | Approve the final distribution license and provenance review before making Holocron public or publishing artifacts. | joshuamyers22 | Before external distribution |
| `specialist-reviewers` | Appoint statistical, numerical, independent verification, and license reviewers before promoting a capability from experimental or distributing artifacts. | joshuamyers22 | Before capability promotion |
