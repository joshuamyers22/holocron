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
| `license-gate` | Statistical implementation is blocked until the permitted use of GPL `rms-master` source and Holocron's distribution license are approved. | `PROJECT_PLAN.md` ADR-001 | 2026-09-17 |
| `reference-snapshot` | The initial statistical source is local `rms-master` 8.2-0 dated 2026-09-11; identity hashes are recorded in `REFERENCE_SOURCE.md`. | `REFERENCE_SOURCE.md` | 2026-09-17 |

## Accepted decisions

| Key | Decision and rationale | Evidence | Last verified |
|---|---|---|---|
| `production-template` | The repository is generated from the production template's `python-data-quant` archetype and will be adapted into a scientific library. | `README.md`; `PROJECT_PLAN.md` | 2026-09-17 |

## Non-obvious current state

| Key | State worth retrieving later | Evidence | Last verified |
|---|---|---|---|
| `pre-implementation` | The repository contains production scaffolding and generated template fixtures; no `rms`-compatible estimator has been implemented or validated. | `README.md` | 2026-09-17 |

## Verified traps and failed approaches

| Key | Symptom and cause | Evidence or reproducer | Last verified |
|---|---|---|---|
No verified trap is recorded.

## Open threads

| Key | Unresolved question or next evidence | Owner | Review by |
|---|---|---|---|
| `license-provenance` | Approve ADR-001 before statistical implementation or external distribution. | joshuamyers22 | Before Phase 1 implementation |
| `github-remote` | Create and push the GitHub repository after `gh` authentication is repaired. | joshuamyers22 | 2026-09-17 |
