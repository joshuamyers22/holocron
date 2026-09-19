# Phase 6 exact-resampling acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 6 deliverable: common resampling engine with exact resample plans
- Disposition: complete within the declared sequential engine envelope

## Accepted contract

`ResamplePlan` is an immutable, fully materialized schedule with bounded
observation, split, and total-index counts. It provides:

- seeded iid bootstrap plans whose assessment sample is the original data;
- seeded repeated K-fold plans that assess every row exactly once per repeat;
- exact caller-declared plans that preserve row order and multiplicity;
- unique persisted row identifiers, with optional selection-time identity
  checking to reject reordering or source-row substitution;
- stable split identifiers, repeat/fold coordinates, canonical JSON, strict
  exact-version reconstruction, and a SHA-256 schedule fingerprint; and
- explicit analysis/assessment row selection that rejects row-count drift and,
  when source identifiers are supplied, row-identity drift.

`run_resample_plan` accepts no fitted model. It calls a caller-owned procedure
once per split so transformations, selection, fitting, prediction, and scoring
can be repeated inside the resample. The default policy raises on the first
failure. The explicit record policy retains bounded exception type/message
records and distinguishes complete, partial, and failed execution with an exact
failure rate and plan fingerprint.

The pre-existing `bootstrap_covariance` path now obtains generated and declared
schedules through `ResamplePlan`, eliminating its private RNG schedule format
without changing its fail-closed estimator-specific result contract.

## Evidence

Focused tests verify deterministic seeded generation, canonical and schema-
valid round trips, exact custom ordering and multiplicity, K-fold partition
invariants, plan-bound whole-procedure refitting, complete/partial/failed
semantics, strict failure behavior, row alignment, malformed JSON rejection,
resource bounds, public exports, and the integrated bootstrap-covariance path.
The public schema is shipped in wheel and source distributions, and installed-
artifact smoke tests reconstruct and execute a plan outside the checkout.

## Boundaries and next step

This slice does not implement model-specific validation or calibration,
optimism correction, parallel/distributed execution, or built-in grouped,
stratified, blocked, and temporal generators. Those schedules may be supplied
as exact plans, but their scientific validity remains the caller's
responsibility. Arbitrary callback results are not serialized.

The next Phase 6 deliverable is model-specific `validate` and `calibrate`
behavior. Phase 6 remains open, and no capability advances beyond
`experimental`.
