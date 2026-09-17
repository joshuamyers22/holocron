# Holocron

Holocron is an independent Python implementation of Frank Harrell's R `rms`
package. It aims to reproduce the integrated Regression Modeling Strategies
workflow—design metadata, estimation, inference, prediction, validation,
calibration, and graphics—with statistical fidelity and a Python-native API.

The project is distributed internally as `holocron-rms` and imported as
`holocron`. No external package has been published.

## Current status

Holocron is experimental and incomplete. Do not use it for consequential
analysis, inference, prediction, or clinical decisions.

The first qualified vertical slice implements explicit-knot restricted cubic
spline design and classical full-rank ordinary least squares. Both are checked
against committed outputs from a Dockerized R oracle. Compatibility is claimed
only for capabilities and support envelopes backed by the
[compatibility manifest](https://github.com/joshuamyers22/holocron/blob/main/compatibility/rms-8.2.0.yaml).

## Library API

Holocron is a typed library and intentionally installs no command-line tools.
Its current public namespaces are `holocron.design`, `holocron.models`, and
`holocron.exceptions`:

```python
from holocron.design import RestrictedCubicSplineSpec
from holocron.models import fit_ols

x = (-2.0, -1.0, 0.0, 1.0, 2.0, 3.0)
y = (0.2, 0.8, 1.1, 1.7, 2.5, 3.6)

spec = RestrictedCubicSplineSpec((-2.0, 0.0, 1.5, 3.0))
design = spec.transform(x)
fit = fit_ols(y, design, feature_names=("x", "x'", "x''"))
predictions = fit.predict(design)
```

Automatic knot placement, formula parsing, missing-data policies, aliased-fit
handling, robust covariance, and broader model families are not supported by
this slice. Unsupported behavior must fail explicitly rather than silently
substitute a different method. See the
[package architecture](https://github.com/joshuamyers22/holocron/blob/main/docs/architecture/PACKAGE_STRUCTURE.md) for API and
dependency boundaries.

## Reference and oracle

The statistical reference is the local `rms` 8.2-0 snapshot at
`/Users/josh/Downloads/rms-master`, frozen to upstream commit
`a4e4a305a029090e737562fb4d35bdb705db7d63`. The R source is GPL-licensed
reference material and is not copied into Holocron or its distributions.

R and `rms` run only in a pinned, isolated Docker oracle with versioned JSON
input/output. Holocron never calls R at runtime. To rebuild and verify it:

```sh
make oracle-build RMS_SOURCE=/Users/josh/Downloads/rms-master
make oracle-health
make oracle-check
```

See the [oracle documentation](https://github.com/joshuamyers22/holocron/blob/main/reference/README.md)
and [ADR-001](https://github.com/joshuamyers22/holocron/blob/main/docs/adr/ADR-001-independent-oracle.md)
for the provenance boundary
and two-stage oracle/independent-test workflow. External distribution remains
blocked pending qualified license and provenance review.

## Development

Python 3.11 or later and `uv` are required for the development environment.

```sh
make setup
make check
make build
make audit
```

`make check` runs formatting, linting, strict type checking, unit and parity
fixture tests, and reference-metadata validation. `make build` creates and
inspects both wheel and source distribution, including checks that reference
source and retired template application modules are absent.

The project scope and delivery gates are defined in
[project plan](https://github.com/joshuamyers22/holocron/blob/main/PROJECT_PLAN.md).
Statistical contributions must follow the
[contributing guide](https://github.com/joshuamyers22/holocron/blob/main/CONTRIBUTING.md)
and the independent-development policy.
