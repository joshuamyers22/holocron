# Phase 9 clean build and installation matrix

**Decision date:** 2026-09-20  
**Scope:** second Phase 9 deliverable  
**Status:** evidence contract and CI execution are ready; completion awaits one retained four-cell run from a single clean revision

## Decision

Holocron's declared artifact-installability matrix is:

| Runner | CPython | Expected architecture |
|---|---:|---|
| Ubuntu 24.04 | 3.11 | x86_64 |
| Ubuntu 24.04 | 3.12 | x86_64 |
| macOS 15 | 3.11 | arm64 |
| macOS 15 | 3.12 | arm64 |

This matrix follows the two Python classifiers and the two accepted operating-
system families. It is an installation contract. It does not expand the
numerical-parity envelope in ADR-009, which remains CPython 3.12.14 with NumPy
2.5.3 on the two named platform/backend combinations.

Every cell starts from a clean checkout and frozen dependency resolution. It
builds the wheel and source distribution offline, inspects both archives,
installs each into its own fresh environment, runs dependency consistency
checks, and exercises the broad public smoke program outside the checkout.
Successful cells retain both artifacts and one schema-valid report for 90 days.

## Evidence contract

The authoritative plan is `governance/phase-9-build-matrix.json`. Each report
binds the plan digest, matrix ID, exact Git revision, observed runtime and NumPy/
uv versions, package version, artifact filenames/sizes/SHA-256 values, and all
seven required checks. Reports can only be emitted with `--require-clean` after
the environment matches its declared cell.

Run the repository topology check with:

```sh
make phase-9-build-matrix-check
```

After downloading the four JSON reports from one CI run into a directory, make
the evidence decision with:

```sh
make phase-9-build-matrix-evidence EVIDENCE_DIRECTORY=/path/to/reports
```

The aggregation gate rejects missing or duplicate cells, unknown environments,
changed plan digests, failed/missing checks, absent wheel or sdist records, and
reports from different revisions.

## Current disposition

The plan, schemas, semantic checker, artifact evidence producer, tests, and CI
job are implemented. No four-cell run of this new workflow exists yet because
these changes have not been committed and pushed. Therefore this deliverable is
not marked complete. A passing first run must be retained and aggregated before
the Phase 9 plan checkbox can close.

Passing this gate does not authorize distribution, external beta testing,
capability promotion, consequential use, or a stable release. Those decisions
remain independently gated.
