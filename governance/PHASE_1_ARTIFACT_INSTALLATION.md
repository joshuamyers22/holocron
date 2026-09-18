# Phase 1 Artifact Installation Acceptance Record

**Status:** Accepted for private experimental development

**Accepted:** 2026-09-17

**Owner:** joshuamyers22

## Scope

This record accepts clean wheel/source-distribution builds and independent
installation smoke tests as the Phase 1 artifact deliverable. It does not
authorize external distribution, accept the Phase 1 exit gate, or promote any
statistical capability beyond its manifest status.

## Build contract

- `make build` clears `dist/` and uses the frozen uv interpreter and locked,
  non-isolated Hatchling backend without network access.
- Both the wheel and source distribution are required and inspected for project
  identity, package contents, typed-package metadata, runtime dependencies,
  absent command entry points, and forbidden reference/development content.
- SHA-256 digests for both artifacts are emitted to the build log.
- `make clean-build` first rejects tracked and untracked source changes. CI and
  release workflows require this target from their fresh checkouts.

## Installation contract

- The wheel and source distribution are each installed into a distinct, newly
  created virtual environment with no system-site-package access. The source
  distribution is first rebuilt into an installation wheel by the frozen,
  non-isolated backend outside the source checkout.
- Runtime dependencies are constrained to exact versions exported from
  `uv.lock`; a missing platform wheel may be fetched from the configured index.
- Dependency consistency is checked after each installation.
- Smoke execution uses isolated Python mode, removes `PYTHONPATH`, and runs from
  a temporary directory outside the repository.
- The smoke program proves that `holocron` resolves inside the temporary
  environment rather than the editable checkout, then verifies distribution and
  import versions, the absent CLI, explicit-knot spline design, full-rank OLS,
  and prediction.
- Temporary installation environments are deleted after the gate; only the
  inspected artifacts remain in `dist/`.

## Automation evidence

- `tools/build_and_smoke_artifacts.py` owns the build, inspection, fresh-install,
  isolation, and workflow checks.
- `.github/workflows/ci.yml` runs `make clean-build` for every push and pull
  request.
- `.github/workflows/release.yml` runs the same gate before any authorized
  release artifact can be attached.

## Remaining Phase 1 work

The minimal vertical slice must still emit a schema-valid evidence artifact and
compare it to the pinned R oracle through repeatable CI before the Phase 1 exit
gate is accepted.
