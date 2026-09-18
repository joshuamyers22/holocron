# Phase 1 frozen-environment completion record

- Decision date: 2026-09-17
- Scope: Phase 1 private development
- Accountable owner: joshuamyers22
- Result: complete

## Acceptance statement

The Phase 1 “frozen Python and R environments” deliverable is complete for the
current private-development compatibility line. The accepted contracts are
defined by ADR-012 and the two machine-readable manifests under `environments/`.

The canonical Python evidence environment is CPython 3.12.14 with uv 0.12.7 and
the exact hashed `uv.lock` resolution. Runtime, development, editable-install,
and package-build dependencies are closed over the lock. Project builds are
non-isolated so the build frontend cannot create an unrecorded second resolution.

The separate R oracle is accepted as `holocron-rms-oracle:8.2-0` on Linux/arm64
at image ID
`sha256:98f03964f0cd7bb713a27a745adab4ef5e44a466f782270a7ee5c1c8877d6704`.
Its base image, R repository snapshot, source commits, complete source manifest,
installed package inventory, external numerical libraries, locale, RNG, native
routines, and runtime controls are recorded and checked.

## Acceptance evidence

- `make setup` installed the exact Python/tool/build graph without an isolated
  project build.
- `make check` passed lint, formatting, strict typing, 17 unit/parity tests, the
  static frozen-environment check, and reference metadata validation.
- `make build` built and inspected the wheel and source distribution using the
  locked non-isolated backend.
- `make audit` found no known runtime vulnerabilities or denied dependency
  licenses.
- `make reference-source-check RMS_SOURCE=/Users/josh/Downloads/rms-master`
  reproduced the complete 363-file reference inventory.
- `make frozen-environments-live` matched the local oracle image ID and platform.
- `make oracle-check` matched the complete live health response and both current
  statistical parity fixtures.

## Boundaries and remaining approvals

This acceptance freezes the canonical evidence environments; it does not approve
a public support matrix, external distribution, or promotion of statistical
capabilities beyond experimental. The R image identity is platform-specific,
and a rebuild is accepted only through the migration procedure in ADR-012.

ADR-009 defines the current Python, OS, architecture, NumPy, and BLAS/LAPACK
evidence envelope; future capabilities and platform additions require new
calibration. Vacant statistical, numerical,
independent-verification, and license reviewers remain blocking under the Phase
0 governance record.
