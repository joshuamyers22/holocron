# ADR-003: Immutable R reference and update policy

- Status: accepted
- Date: 2026-09-17
- Owner: joshuamyers22

## Context and options

Parity claims require an immutable executable reference. The local
`rms-master` snapshot declares version 8.2-0 but is not itself a Git checkout
and upstream has no `8.2-0` tag. A moving branch, package version alone, or a
container tag alone cannot identify the reference sufficiently.

## Decision and consequences

The initial compatibility line is the following combined identity:

- `rms` version 8.2-0 at Git commit
  `a4e4a305a029090e737562fb4d35bdb705db7d63`;
- the 363-file manifest and aggregate manifest digest in
  `reference/manifests/`;
- R 4.5.3 from the digest-pinned Rocker image;
- the dated Posit Package Manager snapshot declared in the Dockerfile;
- Hmisc 5.3-0 at commit
  `778bd69d83961577be1f73fa1e36781bd3fd099f`;
- the complete installed-package and external-library manifest returned by the
  oracle health operation; and
- the platform-specific oracle image digest recorded with generated fixtures.

The local source snapshot was compared recursively with the upstream commit and
was byte-identical outside Git metadata. Docker builds verify every source file
against the committed checksum manifest before installing `rms`.

Reference upgrades are explicit compatibility migrations. They require a new
manifest, side-by-side oracle evidence, changed-default review, compatibility
manifest updates, fixture review, and release notes. Existing fixtures are not
silently regenerated. Upstream HEAD may be tested as a non-blocking canary only.

## Verification

`tools/build_reference_inventory.py --check` must reproduce the source and
namespace artifacts from the approved snapshot. `make oracle-check` must verify
the executable environment and deterministic cases. Reconsider the freeze if
the source commit disappears, a dependency artifact becomes unavailable, or a
reference defect requires a documented parity exception.
