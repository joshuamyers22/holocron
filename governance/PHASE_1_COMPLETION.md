# Phase 1 completion record

- Completion date: 2026-09-17
- Scope: private experimental development
- Accountable owner: joshuamyers22

| Required deliverable | Status | Evidence |
|---|---|---|
| Generated and adapted production repository | Complete | `docs/adr/ADR-011-production-scaffold-adaptation.md`; `docs/architecture/PACKAGE_STRUCTURE.md` |
| Frozen Python and R environments | Accepted | `governance/PHASE_1_FROZEN_ENVIRONMENTS.md` |
| Versioned parity-laboratory contract | Accepted | `governance/PHASE_1_PARITY_LAB_CONTRACT.md`; `schemas/`; `reference/contracts.py` |
| Representative vertical corpus | Complete: 25 statistical cases | `reference/cases/`; `reference/expected/` |
| Cross-platform numerical envelope | Accepted for the implemented slice | `docs/adr/ADR-009-supported-numerical-envelope.md`; `governance/evidence/tolerance-pilot/` |
| Initial documentation and generated compatibility inventory | Accepted | `governance/PHASE_1_DOCUMENTATION.md` |
| Clean artifact build and installation smoke tests | Accepted | `governance/PHASE_1_ARTIFACT_INSTALLATION.md` |
| Minimal end-to-end evidence slice | Passed | `tools/run_phase_1_vertical_slice.py`; `tests/test_phase_1_vertical_slice.py`; `.github/workflows/ci.yml` |

## Exit-gate disposition

The Phase 1 exit gate passes for private experimental development. The named
`ols-rcs-explicit` case validates against the versioned oracle-case schema,
generates an explicit-knot restricted cubic spline design, fits full-rank OLS,
calls the public prediction API, and validates the resulting output. The shared
field-aware comparator then checks 19 exact and 76 numeric values against the
committed output produced by the pinned R `rms` 8.2-0 oracle under the accepted
`well-conditioned-ols-v1` policy.

`make phase-1-e2e` runs that workflow locally and writes schema-valid evidence
to `.work/phase-1-evidence/ols-rcs-explicit.json`. The acceptance form,
`make phase-1-exit-gate`, additionally rejects dirty source or an unknown Git
revision. CI runs the clean gate on every push and pull request and retains the
evidence, including its source identity and input/output hashes, for 30 days.
The release workflow requires the same gate.

The comparison uses an immutable R-produced fixture so the routine CI path is
repeatable without installing R or Docker. Live-oracle regeneration and
verification remain separate, explicit workflows governed by the reference
contract.

## Boundaries after completion

This completion record does not approve external distribution or promote any
capability beyond `experimental`. The license/provenance review and specialist
reviewer requirements remain open. The 13 logistic, ordinal, and survival
fixtures remain oracle baselines rather than independent Python parity claims.
Phase 2 design-system work subsequently began.
