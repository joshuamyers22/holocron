# Development

Holocron uses a frozen uv environment and a single required local gate:

```sh
make setup
make check
```

The repository's [contributing guide](https://github.com/joshuamyers22/holocron/blob/main/CONTRIBUTING.md)
defines signed-commit, independent-development, test, and review requirements.
The [frozen-environment guide](reproducibility/FROZEN_ENVIRONMENTS.md) explains
the Python and R identities.

## Documentation workflow

Edit authored pages under `docs/`, then run:

```sh
make docs-generate
make docs-check
make docs
```

`make docs-generate` rebuilds API pages from public module exports and the
compatibility page from the manifest. `make docs-check` rejects stale generated
content, executes marked Python examples, validates internal links and anchors,
and builds with warnings treated as errors. `make docs` starts the local preview
server.

The Phase 7 gallery inventory in
`governance/phase-7-gallery-manifest.json` is also enforced. Gallery pages must
match the manifest and navigation exactly, contain one coherent executable
workflow plus goal/interpretation/boundary sections, and produce every declared
model, result, plot, SVG, table, and LaTeX output.

Documentation examples must remain deterministic and offline. Mark a Python
fence with `# holocron: execute` when it should be executed by the quality gate.
Generated pages carry a header and should never be edited directly.

## SVG assurance workflow

Run `make svg-check` to audit the structural accessibility contract and compare
all supported plot and nomogram renderers with their committed golden SVGs.
The fixtures are reviewable text files under `tests/snapshots/svg/`. After an
intentional renderer change, inspect the SVG diff before running
`uv run --frozen python -m tools.check_svg_snapshots --update`; snapshot refresh
is never an automatic response to a failed gate. The
[SVG assurance guide](guides/svg-assurance.md) defines coverage and boundaries.

## Artifact workflow

`make build` clears `dist/`, builds the wheel and source distribution offline,
inspects their contents, and installs each artifact into an independent temporary
environment. The smoke program runs in isolated Python mode from outside the
checkout, verifies package identity and dependency consistency, and executes the
supported spline-design, OLS-fit, and prediction path.

Use `make clean-build` for release-style evidence. It rejects tracked or
untracked source changes before building; CI and the gated release workflow use
this target. Temporary installation environments are removed after the checks.

## Performance profile workflow

`make phase-8-profiles` runs five fixed validation and survival workloads,
checks structural call and peak-memory budgets, and retains a JSON report plus
raw `cProfile` files under `.work/phase-8-performance/`. Wall-clock medians are
diagnostic rather than portable gates. Use `make phase-8-profiles-clean` for
clean-source review evidence. The [performance profile guide](guides/performance-profiles.md)
defines the workloads, interpretation, and change policy.

## Migration and deprecation workflow

After changing the compatibility manifest or deprecation registry, run
`make migration-catalog` to regenerate the installed catalog and then
`make migration-check`. The check rejects stale source hashes, incomplete
namespace coverage, invalid public paths, short warning windows, duplicate
notices, and package-version drift. The
[migration and deprecation guide](guides/migration-and-deprecation.md) defines
the user-facing planner and removal guarantees.

## Phase 9 release-candidate workflow

`make phase-9-rc-check` validates the release-candidate plan and current beta
registry without pretending an incomplete program has passed. The stronger
`make phase-9-rc-exit-gate` is reserved for the final Phase 9 evidence decision
and fails until genuine candidates, exact distribution approvals, and external
feedback meet every locked criterion.

## Phase 9 artifact-matrix workflow

`make phase-9-build-matrix-check` validates the exact Ubuntu 24.04/macOS 15 by
CPython 3.11/3.12 plan and its CI wiring. Each CI cell requires a clean checkout,
builds and inspects wheel and sdist artifacts, installs each in a distinct fresh
environment, runs dependency and public-API smoke checks, and retains both
artifacts plus a schema-valid report for 90 days.

Download the four reports from one revision and run:

```sh
make phase-9-build-matrix-evidence EVIDENCE_DIRECTORY=/path/to/reports
```

The aggregator rejects partial, mixed-revision, wrong-environment, or plan-
drifted evidence. This is installability evidence, not a broader numerical-
parity claim.

## Phase 1 evidence workflow

`make phase-1-e2e` executes the accepted RCS-design, OLS-fit, and prediction case,
compares it with the pinned R oracle output under the named field-aware policy,
and writes schema-valid evidence to `.work/phase-1-evidence/`. Use
`make phase-1-exit-gate` from a clean checkout when producing acceptance
evidence. CI runs that clean form and retains its artifact for 30 days.

## Phase 2 evidence workflow

`make phase-2-evidence` checks every independently implemented data-
distribution, transformation, and formula-design case against its pinned R
output. It also requires the adversarial-name case, round-trips a design
specification, matrix, and fitted result before reconstructing new-data
predictions, and verifies that no Phase 3 estimator has been promoted in the
compatibility manifest.

The command writes one schema-valid aggregate record to
`.work/phase-2-evidence/phase-2-exit.json`. Use `make phase-2-exit-gate` from a
clean checkout for acceptance evidence. CI and the gated release workflow run
the clean form; CI retains its artifact for 30 days.

## Phase 4 evidence workflow

`make phase-4-evidence` runs all six ordinal oracle cases, 232 locked simulation
replications, adaptive-quadrature checks, 16/32/64-level sparsity checks, and
the declared failure corpus. It writes a schema-valid aggregate report to
`.work/phase-4-evidence/phase-4-exit.json`. Use `make phase-4-evidence-clean`
for review evidence. CI runs the same package on Ubuntu and macOS and retains
both platform reports. A passing report establishes technical evidence; it does
not substitute for independent statistical approval. Ron Mexico approved the
registered Phase 4 private experimental scope on 2026-09-18, so a passing report
now records the exit gate as closed.

## Compatibility changes

Update the authoritative compatibility manifest in the same change as a public
capability. A claim beyond `deferred` needs an owned Python entry point, oracle
cases, a named tolerance profile, known differences, and the governance evidence
required by [ADR-004](adr/ADR-004-compatibility-contract.md).
