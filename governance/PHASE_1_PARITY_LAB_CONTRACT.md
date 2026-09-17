# Phase 1 parity-laboratory contract acceptance

- Status: accepted for private experimental development
- Date: 2026-09-17
- Owner: joshuamyers22
- Scope: oracle cases, committed outputs, comparison policies, and run evidence

## Accepted contract

The parity laboratory uses versioned JSON Schema Draft 2020-12 contracts for
data-only oracle cases, committed expected outputs, named tolerance policies,
and emitted comparison evidence. All cases are discovered rather than listed in
code. Each case links one expected output and one named profile; case identity,
operation, protocol version, file links, profile existence, and operation-specific
constraints are checked before execution.

Comparison is exact by default. Approximate comparison is allowlisted only for
declared field paths, every declared path must match the expected output, and
ambiguous or unused policies fail validation. The independent Python parity
tests and live R oracle checks use the same policy implementation.

Every live comparison emits a schema-validated evidence record containing the
code revision and dirty-tree state, Python and Holocron versions, pinned R identity, exact case and
fixture hashes, canonical actual-output hash, named policy, comparison counts,
maximum observed errors, outcome, and bounded mismatch details. Evidence is
written under ignored `.work/oracle-evidence/` unless an explicit destination is
provided.

## Verification evidence

- `make check` validates all schemas, policies, fixtures, cross-document links,
  compatibility-manifest profile links, unit parity checks, formatting, and
  strict types without Docker.
- `make oracle-check` executes every case against the pinned isolated R image,
  validates the live response shape, applies the shared named profile, and emits
  evidence before enforcing the result.
- The accepted initial corpus contains oracle health, explicit-knot restricted
  cubic spline design, and full-rank OLS with spline design and prediction.

## Boundaries

This accepts the parity-laboratory infrastructure, not the final numerical
tolerances or Phase 1 case breadth. The current numeric rules are named pilot
profiles. Cross-platform and conditioning evidence plus an approved tolerance
ADR remain required before those thresholds become capability acceptance
criteria. The R oracle and contract code are development assets and are excluded
from Holocron distributions and runtime behavior.
