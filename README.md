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

Phases 0–2 are complete for private experimental development, and Phase 3 is
active. Its first deliverable—experimental `ols`, Gaussian/identity and
binomial/logit `Glm`, and binary `lrm` estimators—is complete. The Phase 1 exit
gate is recorded in the
[completion record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_1_COMPLETION.md);
the evidence-backed Phase 2 disposition is recorded in its
[completion record](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_2_COMPLETION.md).
All six Phase 2 deliverables—immutable data-distribution metadata, the
allowlisted formula/core design engine, and explicit factor/restricted-
interaction handling, plus stable design/result schemas and a serialization
policy, exhaustive transformation differential/property tests, and the R
design-specification migration guide—are complete within their experimental
envelopes. The exit gate checks all 18 design-system parity cases, adversarial
names, and exact serialized prediction reconstruction. External distribution
and capability promotion remain blocked by the governance reviews described
there.

The evidence-backed experimental surface implements predictor-distribution
metadata, safe formulas, numeric and factor transformations, restricted
interactions, classical full-rank ordinary least squares, bounded generalized
linear models, and unpenalized binary logistic regression. These are checked
across 31 independent parity cases against committed outputs from a Dockerized
R oracle. Another nine ordinal and survival cases are frozen as oracle baselines
for later implementation and are not current parity claims.
Compatibility is claimed
only for capabilities and support envelopes backed by the
[compatibility manifest](https://github.com/joshuamyers22/holocron/blob/main/compatibility/rms-8.2.0.yaml).
The current numerical envelope is CPython 3.12.14 with NumPy 2.5.3 on macOS 15
arm64/Accelerate and Ubuntu 24.04 x86_64/OpenBLAS, as defined by ADR-009.

Transformation breadth is additionally checked by deterministic generative
tests covering every supported degree, knot-count, level-count, and ordered pair
of restricted-interaction component kinds.

## Library API

Holocron is a typed library and intentionally installs no command-line tools.
Its current public namespaces are `holocron.design`, `holocron.formula`,
`holocron.models`, and `holocron.exceptions`:

```python
from holocron.design import DataDistribution, DesignSpec
from holocron.formula import Formula
from holocron.models import fit_ols

x = (-2.0, -1.0, 0.0, 1.0, 2.0, 3.0)
y = (0.2, 0.8, 1.1, 1.7, 2.5, 3.6)

metadata = DataDistribution.from_data({"x": x}, labels={"x": "Predictor"})
spec = DesignSpec.from_formula(Formula.parse("y ~ rcs(x, [-2, 0, 1.5, 3])"))
design = spec.transform({"x": x})
fit = fit_ols(y, design)
predictions = fit.predict(design)
restored_fit = type(fit).from_json(fit.to_json())
```

`metadata["x"]` retains adjustment, effect, display, and overall ranges without
depending on global state or the original input iterable.

Design specifications, realized matrices, OLS results, and binary-logistic
results use strict versioned data-only JSON. Fitting from a `DesignMatrix`
carries its specification fingerprint into the result and checks that identity
during prediction. The public schemas ship under `holocron/schemas`; arbitrary
pickle interchange is not supported.

Explicit categorical and scored-ordered terms plus hierarchical two-way
restricted interactions are supported by the design compiler. Automatic knot
or level selection, unrestricted or higher-order interactions, missing-data
policies, aliased-fit handling, other GLM families/links, penalties, robust
covariance, and broader model families are not supported by this slice.
Unsupported behavior must fail explicitly
rather than silently substitute a different method. See the
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

The canonical development environment uses CPython 3.12.14 and uv 0.12.7;
package metadata permits Python 3.11 or later. Both tool versions and the full
dependency/build graph are frozen and checked as described in the
[environment contract](https://github.com/joshuamyers22/holocron/blob/main/docs/reproducibility/FROZEN_ENVIRONMENTS.md).

```sh
make setup
make check
make phase-1-e2e
make build
make audit
```

`make check` runs formatting, linting, strict type checking, unit and parity
fixture tests, frozen-environment checks, and reference-metadata validation.
It also executes the Phase 1 design-to-fit-to-prediction slice and writes
schema-valid parity evidence under `.work/phase-1-evidence/`. CI reruns its
clean-checkout form and retains the evidence for 30 days.
`make build` uses the locked build backend offline and without isolation, then
inspects and independently installs both wheel and source distribution into
fresh environments. Each installation runs dependency validation and the
supported RCS-to-OLS workflow from outside the checkout. `make clean-build`
additionally rejects source-tree changes and is the required CI/release gate.

The project scope and delivery gates are defined in
[project plan](https://github.com/joshuamyers22/holocron/blob/main/PROJECT_PLAN.md).
Statistical contributions must follow the
[contributing guide](https://github.com/joshuamyers22/holocron/blob/main/CONTRIBUTING.md)
and the independent-development policy.

## Documentation

The initial documentation site includes executable getting-started examples,
generated public API reference, and a generated inventory of every compatibility
disposition. Build or preview it locally with:

```sh
make docs-check
make docs
```

Edit the authoritative compatibility manifest or public Python source, then run
`make docs-generate` to refresh generated pages. The ordinary `make check` gate
rejects stale generated content, failed examples, invalid internal links, and
MkDocs warnings.
