# ADR-006: Canonical data boundary

- Status: accepted
- Date: 2026-09-17
- Owner: joshuamyers22

## Context

Holocron needs a stable statistical contract without forcing callers to adopt a
specific dataframe library. Dataframe-native category order, missing values,
labels, units, row identifiers, and zero-copy views differ enough that implicit
conversion would make learned design metadata difficult to audit.

## Decision

The canonical baseline boundary is an ordered mapping of unique string column
names to finite, one-dimensional Python iterables. Public operations snapshot
caller-owned iterables before validation. Columns in one operation must have an
equal row count, and column order is semantically significant.

Numeric columns use float64 for the initial contract. Missing numeric summaries
may explicitly accept `None` and NaN when the operation documents exclusion;
infinite values and mixed implicit coercions are rejected. Categorical levels
and their order must be declared instead of inferred from incidental row order.
Labels and units are explicit metadata rather than dataframe attributes.

Future pandas, Polars, Arrow, and dataframe-interchange support will be adapters
into this boundary. An adapter must specify copying and ownership, row identity,
dtype conversion, null handling, category order, and duplicate-name behavior.
No dataframe package becomes a runtime dependency merely by adding an adapter.

## Consequences and verification

The baseline is intentionally conservative but dependency-neutral and easy to
serialize. `DataDistribution.from_data` is its first implementation. Adapter
work remains open and may not claim parity until replay tests prove that the
canonical snapshot is identical to direct construction.
