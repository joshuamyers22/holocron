# Governance and release authority

## Current authority

Holocron is privately owned and maintained by `joshuamyers22`, who currently
acts as product owner, maintainer, Python/API owner, security contact, and
triage owner for the compatibility inventory.

The statistical architecture, numerical verification, independent verification,
and legal/license reviewer roles are intentionally unfilled. Until qualified
reviewers are appointed:

- capabilities may be marked only `experimental` or `deferred`;
- no stable, clinical, regulated, or full-parity claim may be made;
- no package artifact may be published externally; and
- the repository must remain private.

This is a staffing constraint, not an inference that one maintainer constitutes
independent review.

## Decision rights

- The maintainer accepts ordinary engineering changes and reversible
  experimental APIs.
- A statistical-method change requires statistical and numerical reviewers
  before promotion to `implemented`.
- A parity exception requires an approver other than its implementation author.
- External distribution requires an identified license reviewer and written
  approval of the exact license, provenance process, names, notices, and commit.
- A stable release requires all roles and evidence named in the project plan.

## Phase and release definitions

- Phase completion means its repository deliverables exist and its explicit
  gates are either satisfied or recorded as external release blockers.
- `0.x` artifacts, if later authorized, advertise only manifest-backed
  experimental capabilities.
- `1.0` does not mean full namespace parity unless the compatibility manifest
  has no deferred entries and ADR-010 explicitly adopts that meaning.

## Resourcing assumption

Phase 1 is bounded to the parity laboratory and 20–30 representative cases.
There is no approved monetary budget or staffing commitment for the multi-year
full-parity program. Scope and dates must be re-estimated after the Phase 1
pilot; lack of specialist review pauses promotion rather than lowering gates.
