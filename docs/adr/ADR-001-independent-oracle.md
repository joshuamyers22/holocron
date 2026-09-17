# ADR-001: Independent implementation with a Dockerized R oracle

- Status: accepted
- Date: 2026-09-17
- Owners: joshuamyers22
- Supersedes / superseded by: none

## Context and forces

Holocron needs statistical fidelity to R `rms` 8.2-0 without becoming an R
wrapper or mechanically translating GPL-licensed R, C, or Fortran source. The R
reference must be reproducible, isolated from the Python runtime, and usable for
differential tests. Private proprietary development is approved; the eventual
external distribution license still requires qualified review.

## Options considered

1. Call R at runtime through `rpy2` or a service.
2. Translate the upstream implementation into Python.
3. Write original Python from public statistical specifications and compare its
   observable behavior with an isolated R oracle.

## Decision

Use option 3.

- R and `rms` run only in a digest-pinned Docker oracle.
- The required Hmisc 5.3-0 is installed from pinned Git commit
  `778bd69d83961577be1f73fa1e36781bd3fd099f`; the base repository's 5.2-5 is
  insufficient for `rms` 8.2-0.
- The local `/Users/josh/Downloads/rms-master` snapshot enters the oracle build
  as an external named build context; it is not committed or packaged with
  Holocron.
- Oracle requests and responses use a small, versioned JSON protocol.
- Holocron algorithms and tests are project-authored from mathematical/public
  behavioral specifications and oracle observations. No mechanical source or
  test translation is allowed.
- R is never a Holocron runtime dependency.
- The repository remains private and external distribution stays blocked until
  the distribution license and provenance process receive final review.

## Consequences

- Benefits: clean runtime boundary, reproducible comparisons, Python-native API,
  and diagnosable numerical differences.
- Costs and new failure modes: a large oracle image, dual environments, possible
  dependency drift, and the need to distinguish upstream defects from desired
  compatibility.
- Operational/security implications: oracle containers run without network,
  capabilities, or writable root filesystems after build. Inputs are data-only
  JSON; arbitrary formulas are not accepted by the oracle protocol.
- Reversibility and exit strategy: the oracle may be rebuilt for a new pinned R
  release through a separate compatibility migration; Python code remains
  independent of the container.

## Verification

- Verify image base and R package identities through the oracle health response.
- Store source and image digests with generated fixtures.
- Require differential tests for each claimed compatible method.
- Reconsider if legal review rejects the provenance boundary, the oracle cannot
  be rebuilt reproducibly, or runtime R becomes necessary for a claimed feature.
