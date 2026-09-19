# Phase 7 structured reporting acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 7 deliverable: structured tables and LaTeX output
- Disposition: complete within the declared owned-reporting envelope

## Accepted contract

`holocron.reporting.TableSpec` is an immutable backend-neutral table contract.
It carries identified typed columns, identified rows with raw text/integer/
floating/null cells, optional caption and notes, and bounded string metadata.
Column policies declare semantic type, alignment, precision, and optional unit.
Numeric cells remain numeric in strict canonical JSON; displayed strings are a
renderer concern.

The initial typed adapters cover supported model coefficient summaries,
contrasts, ANOVA tests, aggregate probability validation, horizon survival validation,
optimism-corrected validation, exact resample reporting, influence diagnostics,
robust/model uncertainty comparisons, penalty traces, and VIFs. They copy
declared result quantities and preserve unavailable values as null. They do not
recompute inference or invent missing quantities.

The schema version is `holocron-table-spec/v1`; canonical JSON has stable
SHA-256 identity and rejects unknown fields, duplicate keys, non-finite values,
type mismatches, duplicate identifiers, and resource-limit violations. The
schema ships in wheels and source distributions.

`render_latex` consumes only `TableSpec`. It emits deterministic standard
`table`/`tabular` markup or an embeddable `tabular` fragment without importing a
rendering dependency. Every caller-controlled text context is escaped, there is
no raw-markup escape hatch, missing cells are explicit, and p-value threshold
display never replaces the retained raw value.

## Evidence

Focused tests cover schema-valid canonical round trips and fingerprints, raw
numeric preservation, strict type/field/duplicate-key rejection, deterministic
LaTeX, all special-character escapes, null and p-value formatting, tabular-only
output, and every adapter family. Public API, executable documentation, strict
typing, lint, CI, and installed wheel/sdist smoke paths include reporting.

## Boundaries and next step

This acceptance does not map or claim parity with R `latex.*` methods. Complex
headers, row spans, long-table pagination, styling systems, LaTeX compilation,
raw executable markup, and filesystem output remain outside the contract.
Validation adapters expose supported aggregate result objects; calibration
curve points remain plot data rather than a second table representation.

The next Phase 7 deliverable is task-oriented documentation and tested
galleries. Broader accessibility evidence, visual regression, and the Phase 7
exit gate remain open.
