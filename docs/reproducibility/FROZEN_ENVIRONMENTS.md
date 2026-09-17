# Frozen Python and R environments

Holocron has two separate executable environments with different purposes. The
Python environment builds and tests the independent implementation. The R
environment is a test-only oracle and is never a runtime dependency. Their
authoritative machine-readable records are:

- `environments/python-3.12.14-lock.json`
- `environments/r-oracle-8.2-0-lock.json`
- `uv.lock` for the complete cross-platform Python resolution and artifact hashes
- `reference/expected/oracle-environment.json` for the complete installed R
  package, external-library, BLAS, RNG, locale, timezone, platform, and native
  routine inventory

`make frozen-environments` validates both static contracts on every ordinary CI
run. `make frozen-environments-live` additionally verifies the locally tagged
Docker image ID and platform. `make oracle-check` executes the oracle and requires
its health response and statistical cases to match committed evidence.

## Meaning of frozen

Frozen means that the accepted interpreter/tool versions, dependency graph,
artifact hashes, source identities, container inputs, and observed executable
environment are immutable inputs to the current compatibility line. A change to
any of them is a reviewed environment migration, not an incidental refresh.

This does not mean that every rebuild produces byte-identical filesystem layers.
Registry transport metadata, Docker layer creation, and OS repository delivery
can differ. The accepted R image is therefore identified by its exact local
content ID and platform, while rebuilds must also reproduce the full observable
health manifest before their image identity can replace it. A different image ID
is not silently accepted even when statistical fixtures happen to pass.

The canonical environment is not the public support matrix. Package metadata
currently permits Python 3.11 and later, but the frozen development/CI/release
environment is CPython 3.12.14. Supported Python, OS, architecture, NumPy, BLAS,
and SciPy combinations remain a separate ADR-009 decision and compatibility
matrix.

## Python environment

The canonical Python contract is:

- CPython 3.12.14, selected exactly by `.python-version`;
- uv 0.12.7, enforced by `[tool.uv].required-version` and pinned in GitHub
  Actions;
- exact runtime, development, editable-build, and build-backend packages in
  `uv.lock` and the Python environment manifest;
- SHA-256 hashes for every resolved distribution artifact in `uv.lock`; and
- Hatchling 1.32.0 builds without isolation from the already synchronized lock,
  enforced for Holocron by uv configuration and the build commands, preventing
  a second unrecorded build dependency resolution.

Set up and verify it with:

```sh
make setup
make frozen-environments
```

`make setup` first installs the locked tools without the project, then performs
the editable project build without isolation. This two-stage operation is
required because Hatchling's editable build uses the explicitly locked
`editables` package. `make build` also disables build isolation and uses the same
locked Hatchling environment. Setup and the ordinary gate first check that the
lock agrees with project metadata; all `uv run` commands use frozen mode so a
verification command cannot rewrite the accepted resolution.

The published package keeps compatible dependency ranges rather than exact
development pins; downstream applications own their own lock. Holocron's
release and parity evidence always uses the canonical locked environment.

## R oracle environment

The R oracle contract is:

- `rocker/r-ver:4.5.3` at base-image digest
  `sha256:c3f39b365d1077fe24f8e9ab2742e352b6d3950897f51af1624a5bb5550c21c0`;
- R 4.5.3 on Linux arm64 for the accepted local oracle image;
- Posit Package Manager snapshot dated 2026-04-23;
- `rms` 8.2-0 at commit
  `a4e4a305a029090e737562fb4d35bdb705db7d63`, protected by the complete
  363-file source manifest;
- Hmisc 5.3-0 at commit
  `778bd69d83961577be1f73fa1e36781bd3fd099f`;
- 93 installed R/base packages and ten external-library identities; and
- accepted image ID
  `sha256:67a496a40101a3e400e95342e491bcd82be5c811cc402d5731cb0649328fa84e`.

Rebuild and qualify a candidate with:

```sh
make reference-source-check RMS_SOURCE=/absolute/path/to/rms-master
make oracle-build RMS_SOURCE=/absolute/path/to/rms-master
make frozen-environments-live
make oracle-check
```

An intentional update requires new source/input hashes, a regenerated complete
health response, review of every changed R package or external library, live
oracle parity, and an updated environment manifest. Never overwrite evidence
from the previous compatibility line merely to accommodate drift.
