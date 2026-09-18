# Phase 2 data-distribution metadata acceptance record

- Acceptance date: 2026-09-17
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The first Phase 2 deliverable is complete within the experimental envelope.
`holocron.design.DataDistribution` snapshots named predictor columns and retains
immutable `VariableDistribution` records containing:

- adjustment values and effect, display, and overall ranges;
- continuous/discrete/categorical/ordered classification and retained levels;
- labels, units, non-missing counts, and missing counts;
- the effect/display quantile policy, categorical adjustment policy, and
  discrete-value threshold; and
- a versioned canonical JSON representation and SHA-256 fingerprint.

Numeric summaries implement the documented `rms::datadist` binary, three-level,
median, quantile, range-fallback, constant, and discrete-retention rules.
Unordered categorical adjustment uses the mode with declared-level tie-breaking
or the first declared level. Ordered predictors use the declared middle level.
Metadata can be extended with new same-row-count columns or copied with an
explicit adjustment override; neither operation mutates the original object.

## Acceptance evidence

- Four versioned cases produced by the pinned R `rms` 8.2-0 oracle cover numeric
  defaults, categorical and ordered predictors, custom quantile/adjustment
  policies, and missing numeric observations.
- Independent Python evaluation passes 109 exact and 74 numeric comparisons
  under `data-distribution-v1`; the observed maximum error is at float64 machine
  precision.
- Unit tests cover validation failures, caller-input snapshotting, immutability,
  extension, overrides, missingness, deterministic serialization, schema
  validation, and round trips.
- `schemas/data-distribution.schema.json` versions the portable metadata form;
  repository checks validate that schema and all oracle links.
- ADR-005 and ADR-006 establish the owned-design and canonical-data boundaries
  required before Phase 2 implementation.

## Deliberate boundaries

There is no ambient equivalent of R `options(datadist=...)`; later fits must
store the metadata they use. Categorical levels must be explicit. The default
display quantiles are computed independently from each variable's non-missing
count, following the reference documentation rather than reusing the first
numeric variable's probability when missingness differs. For an even number of
ordered levels, Holocron selects the lower middle level explicitly.

Dataframe/date-time adapters, formula integration, row-level model missing-data
handling, automatic knot selection, and prediction adjustment semantics remain
later Phase 2 work. Labels and units are retained metadata but do not perform
unit conversion. The capability remains `experimental`; this acceptance does
not approve external distribution or capability promotion.
