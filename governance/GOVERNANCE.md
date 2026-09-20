# Governance and release authority

## Current authority

Holocron is privately owned and maintained by `joshuamyers22`, who currently
acts as product owner, maintainer, Python/API owner, security contact, and
triage owner for the compatibility inventory.

Ron Mexico serves as the independent statistical reviewer for the Phase 3
alpha, Phase 4 private experimental, and Phase 5 private experimental scopes
and approved all three scoped reviews on 2026-09-18. The accountable maintainer
closed the Phase 6, Phase 7, and Phase 8 technical exit gates on 2026-09-19.
No independent Phase 6, Phase 7, or Phase 8 approval is claimed. Independent
verification and legal/license reviewer roles remain unfilled; numerical review
remains a separate promotion gate outside the approved Phase 5 scope.
Until those qualified reviewers are appointed and their applicable gates pass:

- implemented capabilities may be marked only `experimental`; `mapped` and
  `unsupported` remain non-parity namespace dispositions, and no capability may
  advance to `implemented`;
- no stable, clinical, regulated, or full-parity claim may be made;
- no package artifact may be published externally; and
- the repository must remain private.

The Phase 3, Phase 4, and Phase 5 statistical approvals and the Phase 6–8
technical completion decisions are scope-specific; they are not approval of
future phases, capability promotion, external distribution, or a broader
compatibility claim. The remaining vacancies are
staffing constraints, not an inference that one maintainer constitutes
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
  has no deferred or unsupported entries and ADR-010 explicitly adopts that
  meaning.

## Resourcing assumption

Phase 1 was bounded to the parity laboratory and 20–30 representative cases and
is complete for private experimental development. There is no approved monetary
budget or staffing commitment for the multi-year full-parity program. Scope and
dates must be re-estimated before expanding beyond the accepted pilot; lack of
specialist review pauses promotion rather than lowering gates. See
`governance/PHASE_1_COMPLETION.md`.
