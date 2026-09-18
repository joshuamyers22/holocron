# ADR-009: Supported numerical envelope and tolerance policy

- Status: accepted for private experimental development
- Date: 2026-09-17
- Owner: joshuamyers22
- Supersedes / superseded by: none

## Context and forces

Floating-point parity depends on the Python and NumPy versions, operating
system, architecture, and BLAS/LAPACK implementation. A single development
machine or a permissive universal `allclose` threshold would not establish a
credible compatibility envelope. Conversely, matching one set of fixtures does
not justify public support for every platform accepted by package metadata.

The Phase 1 implementation has two independently executable capabilities:
restricted cubic spline design and well-conditioned, full-rank OLS over those
designs. Logistic, ordinal, and survival fixtures are currently R oracle
baselines without independent Python implementations. Their profiles therefore
cannot be accepted by this cross-platform pilot.

## Decision

The accepted Phase 1 numerical evidence envelope is:

| Component | Accepted value |
|---|---|
| Precision | float64 |
| Python | CPython 3.12.14 |
| NumPy | 2.5.3 |
| Linux | Ubuntu 24.04, x86_64, SciPy OpenBLAS 0.3.34.106.0 |
| macOS | macOS 15, arm64, system Accelerate BLAS/LAPACK |
| Reference | `rms` 8.2-0 at `a4e4a305a029090e737562fb4d35bdb705db7d63` |

This is the envelope for numerical parity claims, not the package installation
floor and not authorization for external distribution. Python 3.11 and other
environments may remain installable during private development, but they carry
no parity claim until added through reviewed evidence. SciPy is not currently a
runtime dependency. Windows, Linux arm64, macOS x86_64, other BLAS/LAPACK
implementations, other NumPy versions, and non-float64 inputs are outside this
accepted envelope.

The following named profiles and rules in `reference/tolerances.json` are
accepted for the current cases labeled `python-parity`:

- `data-distribution-v1`: exact structure and categorical metadata; numeric
  summaries use `1e-12` absolute and `1e-12` relative tolerance.
- `deterministic-transform-v1`: exact structure and metadata; spline basis
  values use `1e-12` absolute and `1e-12` relative tolerance.
- `formula-design-v1`: exact formula, AST, generated-column, and term metadata;
  transformed design values use `1e-12` absolute and relative tolerance.
- `well-conditioned-ols-v1`: exact structure and metadata; design values use
  `1e-12` absolute/relative; coefficients, fitted values, residuals, and sigma
  use `1e-8` absolute and `1e-7` relative; covariance values use `1e-7`
  absolute and `1e-6` relative.

The comparator applies numeric acceptance using Python `math.isclose`; a value
passes when its absolute difference does not exceed the larger applicable
absolute or relative allowance. Unlisted fields remain exact. No global numeric
tolerance exists.

The thresholds retain the project plan's pre-specified engineering budgets.
They were not inferred by widening around observed errors. In the original
Phase 1 cross-platform calibration, the largest observed absolute difference
was `1.49e-13`; the largest relative difference was `4.82e-12`, occurring near
zero where the absolute rule governs. The later distribution and formula-design
profiles use the pre-specified deterministic `1e-12` budget. These are
engineering gates for experimental parity, not thresholds for statistical
significance or clinical materiality.

The profiles for binary logistic, ordinal, Cox, parametric survival, and
nonparametric survival remain provisional oracle-repeatability policies. Each
must receive its own cross-platform calibration and profile revision or explicit
acceptance before its Python capability can advance.

## Evidence and enforcement

Revision `bdd5b6eac6e86039f5adbc8ab81afcbc90014f12` executed the original 12
independent Phase 1 cases against the same committed R fixtures and policy hash
on both platforms:

| Platform | Cases | Maximum absolute error | Maximum relative error | Evidence |
|---|---:|---:|---:|---|
| macOS 15 arm64 / Accelerate | 12 | `1.4654943925052066e-13` | `5.750852837135746e-13` | `governance/evidence/tolerance-pilot/macos-15-arm64.json` |
| Ubuntu 24.04 x86_64 / OpenBLAS | 12 | `1.4876988529977098e-13` | `4.815187764525943e-12` | `governance/evidence/tolerance-pilot/ubuntu-24.04-x86_64.json` |

Both reports came from CI run
[`35289401790`](https://github.com/joshuamyers22/holocron/actions/runs/35289401790).
They record the source revision, dirty-tree state, runtime and numerical-library
identity, oracle identity, policy hash, per-case comparison counts, errors, and
outcome, and validate against `schemas/tolerance-pilot.schema.json`.

The required CI matrix now reruns all 20 implemented cases on `ubuntu-24.04`
and `macos-15` for every pull request and push. `make tolerance-pilot`
reproduces the report on the current platform. The immutable table above remains
the Phase 1 acceptance evidence; each later Phase 2 acceptance record identifies
its additional cases and policy. Static repository checks reject missing Phase
1 platforms, dirty or failed evidence, differing pilot revisions, or an altered
historical policy identity.

## Consequences and boundaries

- A platform-specific difference inside a named rule is acceptable only when
  the complete case passes; observed error alone is not a reason to widen a
  rule.
- A tolerance change requires a versioned profile or reviewed contract change,
  fresh reports on both platforms, compatibility metadata review, and release
  classification under ADR-004.
- A failure is investigated as an implementation, fixture, environment, or
  reference change. It must not be resolved by silently loosening a threshold.
- These OLS rules cover only the declared full-rank, well-conditioned fixtures.
  Rank-deficient or ill-conditioned cases require explicit failure or
  conditioning contracts rather than larger tolerances.
- This decision does not replace simulation evidence, statistical review, or
  the external-distribution gate.

Reconsider this ADR when adding a platform, Python/NumPy version, numerical
backend, dtype, estimator family, materially different conditioning regime, or
iterative/stochastic algorithm; when a runner image changes numerical-library
identity; or when observed errors consume the accepted budget unexpectedly.
