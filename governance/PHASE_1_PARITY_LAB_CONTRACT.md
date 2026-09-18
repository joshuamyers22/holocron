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
- The accepted corpus contains one environment-health case and 25 statistical
  cases: six restricted-cubic-spline designs, six full-rank spline OLS fits,
  four binary logistic fits, three ordinal fits, two Cox fits, two parametric
  survival fits, and two Kaplan–Meier estimates.
- At Phase 1 acceptance, 12 design and OLS cases were recomputed by the
  independent Python implementation and the 13 later-family cases were frozen
  oracle baselines. Subsequent phases implemented the binary-logistic, ordinal,
  and survival targets; every original statistical case is now labeled
  `python-parity`. The expanded corpus contains 49 Python-parity cases plus the
  environment-health case.

## Boundaries

This accepts the parity-laboratory infrastructure and Phase 1 corpus breadth.
ADR-009 separately accepts the design and well-conditioned OLS tolerances within
its exact cross-platform numerical envelope. It does not accept parity or final
tolerances for unimplemented model families. The R oracle and contract code are
development assets and are excluded from Holocron distributions and runtime
behavior.
