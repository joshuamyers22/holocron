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
| `reference-snapshot` | The initial statistical source is local `rms-master` 8.2-0 dated 2026-09-11; identity hashes are recorded in `REFERENCE_SOURCE.md`. | `REFERENCE_SOURCE.md` | 2026-09-17 |

## Accepted decisions

| Key | Decision and rationale | Evidence | Last verified |
|---|---|---|---|
| `production-template` | The repository is generated from the production template's `python-data-quant` archetype and will be adapted into a scientific library. | `README.md`; `PROJECT_PLAN.md` | 2026-09-17 |
| `docker-oracle` | R `rms` runs only in a pinned Docker oracle with JSON I/O; Python implementation code is original and R is not a runtime dependency. | `docs/adr/ADR-001-independent-oracle.md`; `reference/r/` | 2026-09-17 |

## Non-obvious current state

| Key | State worth retrieving later | Evidence | Last verified |
|---|---|---|---|
| `first-slice` | Explicit-knot restricted cubic spline design and classical full-rank OLS pass deterministic parity fixtures from the live rms 8.2-0 oracle. | `src/holocron/design/splines.py`; `src/holocron/models/linear.py`; `reference/expected/` | 2026-09-17 |

## Verified traps and failed approaches

| Key | Symptom and cause | Evidence or reproducer | Last verified |
|---|---|---|---|
| `hmisc-version` | Rocker's R 4.5.3 repository snapshot contains Hmisc 5.2-5, but rms 8.2-0 requires >=5.3-0; the oracle installs Hmisc 5.3-0 from pinned commit `778bd69d83961577be1f73fa1e36781bd3fd099f`. | `reference/r/Dockerfile`; `reference/expected/oracle-environment.json` | 2026-09-17 |

## Open threads

| Key | Unresolved question or next evidence | Owner | Review by |
|---|---|---|---|
| `distribution-license` | Approve the final distribution license and provenance review before making Holocron public or publishing artifacts. | joshuamyers22 | Before external distribution |
