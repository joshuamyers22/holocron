# Phase 9 release-candidate and external-beta program

**Decision date:** 2026-09-19

**Scope:** first Phase 9 deliverable; `1.0.0` release candidates and external beta feedback

**Decision:** evidence contracts and fail-closed gates complete; candidate series and external feedback blocked

## Locked program

`phase-9-release-candidate-plan.json` defines a private `1.0.0rcN` series. The
target is intentionally 1.0 because Phase 9 qualifies a stable release; the
plan does not itself define or approve the stable API. ADR-010 must first define
the exact stable core and compatibility meaning required by the project plan.

A complete series requires at least two ordered candidates with distinct clean
source revisions. Every candidate retains its version/tag, wheel and source-
distribution hashes, and passing complete-check, dependency-audit, and clean
artifact-smoke evidence. Non-final candidates must be superseded and the final
candidate must be accepted.

External distribution remains a separate prerequisite. Each distributed
candidate needs a written approval tied to its exact source revision from a
qualified license/provenance reviewer. That record must approve the license,
provenance process, package name, notices, and external beta distribution. The
existing repository-variable gate remains fail-closed as a second control.
That workflow gate binds approval to the tag commit SHA and a named approval
record; a stale global boolean is insufficient.

## Feedback contract

Completion requires retained feedback from at least three independent external
reviewers across all five declared workflows: design/core modeling, survival,
validation/calibration, graphics/reporting, and migration. The accepted final
candidate must receive feedback. Every blocker or high-severity finding must be
resolved; lower-severity findings must still have an explicit disposition and
resolution when closed.

The registry stores pseudonymous reviewer IDs, independence and retention
attestations, bounded environment details, workflows, ratings, summaries, and
findings. It rejects extra identity fields. Names, emails, organizations,
restricted datasets, and free-form personal information must not be committed.
Test fixtures use synthetic records and are never evidence of external review.

`tools.check_phase_9_release_candidates` schema-validates both documents and
then enforces cross-record identity, version, ordinal, revision, approval,
feedback, workflow, finding, and status invariants. `make phase-9-rc-check`
validates the current record; `make phase-9-rc-exit-gate` additionally requires
real completion. The release workflow runs the structural check for prerelease
tags and requires the completion gate for a final tag.

## Current disposition

The program is valid and explicitly blocked. It contains zero release
candidates and zero external feedback records. Three blockers remain:

1. ADR-010 has not defined and approved the 1.0 stable core.
2. No qualified license/provenance reviewer has approved an exact candidate
   commit, license, provenance process, package name, and notices.
3. No authorized external beta cohort has been recruited.

These conditions require new authority and real external participation. They
cannot be satisfied by generated fixtures, maintainer self-review, relabeling
internal tests, or publishing without approval. Consequently the first Phase 9
deliverable is not complete and is not checked off in the project plan. The
repository now has the machinery to record and verify it without weakening the
distribution gate or fabricating evidence.
