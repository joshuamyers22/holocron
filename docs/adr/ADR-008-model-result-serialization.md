# ADR-008: Model and result serialization

- Status: accepted
- Date: 2026-09-18
- Owner: joshuamyers22

## Context

Design reconstruction, fitted-result exchange, and audit evidence need durable
identities without making Python implementation details executable. Pickle and
similar object-graph formats can execute code while loading and couple stored
objects to module layout. Unversioned JSON would avoid code execution but could
silently reinterpret statistical meaning after a release.

## Decision

Holocron's supported interchange is bounded, data-only UTF-8 JSON. Every
document has an exact `schema_version`, rejects unknown fields, duplicate keys,
non-finite numbers, malformed Unicode, and documents larger than 64 MiB, and is
checked again by the owning Python type for cross-field invariants. Arbitrary
pickle, joblib, callback, class path, and import reconstruction are not supported.

Canonical writers sort object keys, omit insignificant whitespace, preserve
Unicode, and reject non-JSON values. A SHA-256 fingerprint of those exact UTF-8
bytes provides deterministic identity. Fingerprints detect accidental mismatch;
they are not signatures and do not establish authenticity.

The accepted schemas are:

| Python type | Schema version |
|---|---|
| `DataDistribution` | `holocron-data-distribution/v1` |
| `Formula` | `holocron-formula/v2` |
| `DesignSpec` | `holocron-design-spec/v2` |
| `DesignMatrix` | `holocron-design-matrix/v1` |
| `OlsResult` | `holocron-ols-result/v1` |
| `BinaryLogisticResult` | `holocron-binary-logistic-result/v1` |
| `OrdinalResult` | `holocron-ordinal-result/v1` |
| `CoxResult` | `holocron-cox-result/v2` |
| `ParametricSurvivalResult` | `holocron-parametric-survival-result/v2` |
| `NonparametricSurvivalResult` | `holocron-nonparametric-survival-result/v2` |
| `ResamplePlan` | `holocron-resample-plan/v1` |
| `PlotSpec` | `holocron-plot-spec/v1` |
| `NomogramGeometry` | `holocron-nomogram-geometry/v1` |
| `TableSpec` | `holocron-table-spec/v1` |

`DesignMatrix` stores its specification fingerprint and intercept policy. An
OLS fit made directly from that matrix derives the intercept policy, stores the
same identity, and rejects prediction from a matrix with another specification.
Raw array fits default to an intercept and remain supported, but have a null
design fingerprint and therefore cannot provide this check.

Published schema versions retain their field meaning. A breaking semantic or
structural change creates a new version and schema file; it never edits the old
version into a new meaning. The survival v2 readers accept their exact version
plus the shipped v1 shape and perform a bounded, tested, one-step migration in
memory. V1 files remain unchanged and packaged; writers emit only v2. Other
readers accept only their declared version. Future cross-version loading needs
the same explicit migration path: readers must not guess a version or silently
discard fields. Retention duration and migration-support windows remain a
beta-release decision.

The JSON Schemas and serialization manifest ship in wheel and source
distributions under `holocron/schemas`. Repository schemas remain the
authoritative source. JSON Schema describes local shapes; constructors enforce
relationships such as matrix width, term-slice partitioning, covariance
symmetry, full-rank dimensions, and residual degrees of freedom.

## Consequences and verification

The format is portable, inspectable, deterministic, and non-executable, at the
cost of larger files and exact-version readers. OLS documents contain fitted
values and residuals and may reveal sensitive input-derived information; callers
own access control, encryption, and retention. Fingerprints must not be treated
as integrity protection against an attacker who can replace both content and
digest.

Tests cover schema validity, canonical round trips, malformed and duplicate JSON,
tampered identities, inconsistent dimensions, and wrong-design prediction. The
artifact gate verifies the public schemas exist in both built formats and that a
fresh installation can round-trip a design matrix and OLS result.
