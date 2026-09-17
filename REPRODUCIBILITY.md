# Reproducibility

Holocron separates three reproducibility concerns: the Python development
environment, the pinned R reference environment, and the identity of every
statistical case and result.

## Python environment

`pyproject.toml` declares supported runtime ranges and `uv.lock` is the sole
exact development lock. Install with `uv sync --frozen --dev`; CI uses the same
frozen operation. The installed package currently depends only on NumPy. The
canonical table boundary and broader estimator-backend policy await ADR-006 and
ADR-007, so dataframe and model libraries are not implicit parts of the runtime
contract.

Record the Holocron version, Python version, NumPy version, platform, and BLAS or
LAPACK identity with consequential numerical results. A release candidate must
be tested from its built wheel and source distribution in a clean environment,
not only from an editable checkout.

## R reference environment

The initial compatibility line is `rms` 8.2-0 at commit
`a4e4a305a029090e737562fb4d35bdb705db7d63`. The complete source-file manifest,
namespace inventory, container inputs, installed R packages, external libraries,
and fixture-producing image digest live under `reference/`. Oracle builds verify
the full source tree before installation and runtime containers have no network,
capabilities, or writable root filesystem.

Reference upgrades create a new compatibility line with reviewed side-by-side
evidence. Existing fixtures are never silently regenerated. R and Docker are
test tools and are absent from Holocron distributions and production runtime.

## Statistical cases and results

Every oracle case has versioned JSON input and expected output under
`reference/`, with deterministic comparison tests in `tests/`. A capability's
compatibility status and evidence links are recorded in
`compatibility/rms-8.2.0.yaml`. Exact metadata comparisons and numerical
tolerances follow ADR-004; method-specific tolerance profiles must be approved
before a capability advances beyond experimental.

Every future fit or validation evidence artifact must identify:

- package, dependency, platform, and numerical-library versions;
- code revision and model/design specification;
- ordered generated columns, sample declaration, and retained-row identity;
- caller-supplied input identifiers and hashes;
- family, link, covariance, weights, offsets, penalties, and missing-data policy;
- RNG and resample-plan identity when stochastic operations are used;
- convergence and warning statuses; and
- schema version and deterministic output hash.

Evidence artifacts must not include raw sensitive data. Resampling must repeat
all learned transformations and model fitting inside each training sample unless
the estimand explicitly fixes a step in advance.

## Development practices

Run `make check`, `make build`, and `make audit` before review. Rebuild the live
oracle with the approved source snapshot when oracle behavior or environment
identity is in scope. Notebooks may explore and communicate, but maintained
calculations belong in typed modules with deterministic tests; notebook output is
not release evidence by itself.
