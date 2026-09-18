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

## Non-obvious current state

| Key | State worth retrieving later | Evidence | Last verified |
|---|---|---|---|
| `first-slice` | Explicit-knot restricted cubic spline design and classical full-rank OLS pass deterministic parity fixtures from the live rms 8.2-0 oracle. | `src/holocron/design/splines.py`; `src/holocron/models/linear.py`; `reference/expected/` | 2026-09-17 |
| `phase-0` | Phase 0 repository deliverables are complete for private development; vacant statistical, numerical, verification, and license-review roles block capability promotion and external distribution. | `PROJECT_PLAN.md`; `governance/GOVERNANCE.md` | 2026-09-17 |
| `public-api` | The installed package has no CLI; its root exposes only version plus `design`, `models`, and `exceptions`, and domain `__all__` declarations define the supported public names. | `src/holocron/__init__.py`; `docs/architecture/PACKAGE_STRUCTURE.md`; `tests/test_public_api.py` | 2026-09-17 |
| `frozen-environments` | The canonical Python evidence environment is CPython 3.12.14 with uv 0.12.7 and a hashed dependency/build lock; the separate R oracle is frozen by source/base/repository identities, full health evidence, Linux/arm64 platform, and image ID. Static checks run in CI; oracle rebuilds require live identity and behavior checks. | `governance/PHASE_1_FROZEN_ENVIRONMENTS.md`; `docs/adr/ADR-012-frozen-environment-contract.md`; `environments/` | 2026-09-17 |
| `parity-lab-contract` | Oracle cases, expected outputs, named field-aware tolerances, and emitted parity evidence use versioned JSON schemas. Exact comparison is the default; approximate rules are allowlisted by field path and shared by Python and live-R checks. | `governance/PHASE_1_PARITY_LAB_CONTRACT.md`; `schemas/`; `reference/contracts.py` | 2026-09-17 |
| `phase-1-corpus` | The oracle corpus has 25 statistical cases across RCS design, OLS, binary logistic, ordinal, Cox, parametric survival, and Kaplan–Meier workflows, plus environment health. Twelve design/OLS cases have independent Python parity; 13 later-family cases are explicitly frozen oracle baselines, not parity claims. | `reference/cases/`; `reference/expected/`; `governance/PHASE_1_PARITY_LAB_CONTRACT.md` | 2026-09-17 |

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
