# Releases

Holocron is at version 0.1.0 for private development. No public release or
package-index publication is authorized.

## Current release gate

A tag-triggered release remains fail-closed unless governance records a qualified
license and provenance approval and the repository variable
`EXTERNAL_DISTRIBUTION_APPROVED` is exactly `true`. Passing CI or building a wheel
does not satisfy that gate.

Release candidates must use frozen dependencies, pass the complete quality gate,
build wheel and source distributions from a clean checkout, install from those
artifacts in clean environments, and inspect their contents. Compatibility and
documentation must describe the same public surface. `make clean-build` performs
the package build offline, constrains fresh-install dependencies to `uv.lock`,
and is required by both CI and the release workflow.

Changes planned for the next version are recorded in the
[changelog](https://github.com/joshuamyers22/holocron/blob/main/CHANGELOG.md).
