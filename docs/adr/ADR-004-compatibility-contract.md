# ADR-004: Behavioral compatibility contract

- Status: accepted
- Date: 2026-09-17
- Owner: joshuamyers22

## Context and options

R `rms` combines statistical algorithms, R language conventions, global state,
S3 dispatch, formatting, and graphics. A claim of compatibility could mean API
similarity, numerical similarity on examples, or an evidence-backed behavioral
contract. Only the last meaning is sufficiently precise for scientific use.

## Decision and consequences

Holocron claims compatibility capability by capability, never package-wide by
implication. `compatibility/rms-8.2.0.yaml` is authoritative for the pinned
reference and assigns every exported symbol and registered S3 method an owner,
tier, milestone, and one of these states:

- `experimental`: implemented narrowly, with incomplete acceptance evidence;
- `implemented`: accepted within a documented support envelope;
- `mapped`: intentionally served by a different documented Python API;
- `unsupported`: reviewed and intentionally unavailable; or
- `deferred`: triaged for a later phase.

Compatibility targets observable statistical behavior and stored design
semantics, not R syntax or S3 object layout. A capability may move to
`implemented` only when its specification, oracle cases, tolerance profile,
edge/property tests, applicable simulations, documentation, and independent
review are complete. Unsupported combinations fail closed.

Comparison proceeds from normalized inputs and design matrices through
objectives, estimates, covariance, prediction, and derived output. Discrete
metadata is exact. Numerical tolerances are named and method-specific; they
cannot be widened merely to make a failing fixture pass. Accepted differences
require a versioned parity-exception record with statistical impact and approval.

Python APIs use semantic versioning. Expanding a support envelope is additive;
changing an estimand, parameterization, default, or accepted tolerance is a
statistical contract change and requires an ADR/release classification even if
the Python signature is unchanged.

## Verification

Repository checks validate that the compatibility manifest covers every
export/S3 entry exactly once and that implemented or experimental entries name
real evidence. Documentation must generate compatibility claims from this
manifest. Reconsider the contract if users require syntax-level emulation or if
a model family cannot be represented without exposing R-specific semantics.
