# ADR-012: Frozen Python and R environment contract

- Status: accepted
- Date: 2026-09-17
- Owner: joshuamyers22
- Supersedes / superseded by: none

## Context and forces

Statistical parity can be affected by interpreter, numerical-library, BLAS,
compiler, package, locale, RNG, and build-tool changes. `uv.lock` and the oracle
health response already captured much of this state, but the Python patch version
was not exact, build isolation performed a second dependency resolution, and no
single check tied both environment records together.

ADR-009 remains reserved for the eventual supported platform and numerical
compatibility matrix. This decision defines only the canonical environments used
to generate current evidence.

## Decision

- Freeze the canonical environment to CPython 3.12.14 and uv 0.12.5.
- Enforce the uv version through project configuration and use its hashed lock as
  the complete Python resolution.
- Include Hatchling and its editable-build dependency in the development lock.
  Configure uv to build Holocron without isolation, and synchronize the locked
  build tools before installing the project.
- Record the selected Python packages and the lock/version-file digests in a
  machine-readable environment manifest.
- Treat the R oracle as a separate test environment identified by immutable base
  digest, dated R repository, `rms` and Hmisc commits, source manifest, complete
  health response, accepted platform, and exact built image ID.
- Validate both contracts in ordinary CI without Docker. Require a separate live
  check of the Docker image ID and full oracle behavior when rebuilding or
  changing the R environment.
- Define an environment update as a reviewed migration with regenerated evidence;
  never silently refresh a lock, health fixture, or accepted image identity.

## Consequences

Local development, CI, and release builds now share an exact Python interpreter,
uv version, package graph, and build backend. An unexpected tool, installed
package, lock change, or oracle-input change fails the environment gate.

The accepted R image identity is architecture-specific. This Phase 1 freeze does
not establish the public support matrix or guarantee byte-identical Docker layer
rebuilds. Cross-platform numerical equivalence and supported BLAS combinations
remain work for ADR-009 and the tolerance pilot.

## Verification

- `make setup` must succeed from the exact Python and dependency locks.
- `make frozen-environments` checks static Python and R identities in CI.
- `make frozen-environments-live` checks the local oracle image ID and platform.
- `make oracle-check` compares the complete live environment response and parity
  cases with committed evidence.
- `make build` uses the locked backend without build isolation and artifact
  inspection confirms the distribution boundary.
