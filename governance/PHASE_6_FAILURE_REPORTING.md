# Phase 6 failure-reporting acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 6 deliverable: failure-rate and partial-resample reporting
- Disposition: complete within the exact-plan execution envelope

## Accepted contract

`report_resample_execution` consumes an exact `ResampleExecution` and returns a
typed `ResampleReport`. The report retains the plan fingerprint, exact status,
successful and failed split identifiers, planned/success/failure counts and
rates, and deterministic failure-reason groups keyed by the bounded exception
type and message already retained by the engine.

Callers may supply bounded named contributor counts for metrics that are
undefined on some otherwise successful resamples. Each metric report separates
planned coverage from coverage among successful refits and reports the number
of successful outcomes omitted for that metric. It never treats an undefined
metric as a refit failure or silently substitutes zero.

The default aggregation policy is `complete-only`. On a partial execution it
reports `aggregation_permitted=False`; `allow_partial=True` records an explicit
opt-in and permits downstream aggregation only when at least one resample
succeeded. The source status remains `partial`, every failure remains visible,
and an all-failed execution never permits aggregation under either policy.
Reporting itself does not aggregate arbitrary callback values.

## Evidence

Focused tests cover complete, partial, and all-failed executions; exact split
identity; count/rate identities; deterministic grouping of repeated and distinct
failure reasons; complete-only and allow-partial dispositions; per-metric
planned and successful coverage; undefined-metric omissions; all-failed metric
coverage; malformed inputs; and inconsistent result-object rejection. Existing
optimism-correction tests continue to prove that partial aggregation requires
an explicit opt-in. Executable documentation and wheel/sdist installation smoke
tests exercise the public reporting API.

## Boundaries and next step

A report describes observed execution failures; it cannot establish that those
failures are missing at random, ignorable, or harmless. Exception text is a
bounded diagnostic category, not a stable machine error code. The contract does
not serialize arbitrary callback results, retry failed splits, impute missing
metrics, pool heterogeneous plans, or choose an acceptable failure threshold
for an application.

All six Phase 6 deliverables are now implemented. Their combined technical
review passes in `PHASE_6_COMPLETION.md`, closing the private-development exit
gate without claiming independent approval or advancing any compatibility-
manifest status.
