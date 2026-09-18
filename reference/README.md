# R `rms` parity oracle

This directory contains the test-only oracle for qualifying Holocron's
independent Python methods. It is not included in the Python distribution and
is never called at runtime by the `holocron` package.

## Pinned identity

- Base image: `rocker/r-ver:4.5.3` at the digest in `r/Dockerfile`
- R package: local `rms` 8.2-0 source matching commit
  `a4e4a305a029090e737562fb4d35bdb705db7d63`; every file is checked against
  `manifests/rms-8.2-0-files.sha256` during the build
- Hmisc: 5.3-0 from Git commit
  `778bd69d83961577be1f73fa1e36781bd3fd099f`
- Protocol: JSON protocol version 1, implemented by `r/oracle.R`

## Versioned parity contract

Every file under `cases/` validates against
`../schemas/oracle-case.schema.json`. A case declares a stable ID, description,
expected-output file, named comparison profile, and one allowlisted data-only
oracle operation. It also labels whether the case is environment evidence,
independent Python parity, or a frozen oracle baseline for a deferred model
family. Every committed fixture under `expected/` validates against
`../schemas/oracle-output.schema.json` and records the pinned `rms` version,
commit, and protocol version that produced it. Cross-document validation also
requires case IDs, operations, protocol versions, filenames, vector lengths,
and comparison profiles to agree.

Named field-aware policies live in `tolerances.json` and phase-specific policy
files such as `phase-3-tolerances.json`; all validate against
`../schemas/tolerance-policy.schema.json`. Structure, metadata, names, indices,
and unlisted values compare exactly. Approximate comparison is enabled only for
explicit JSON Pointer-like paths, where `*` matches one object key or array
index. The profiles distinguish deterministic design values, model coefficients
and predictions, covariance matrices, survival estimates, and exact oracle
identity. ADR-009 accepts the deterministic-transform and well-conditioned OLS
profiles within its exact Python/NumPy/platform/BLAS envelope. Profiles for
model families that remain oracle baselines are provisional until their
independent Python implementations receive equivalent cross-platform
calibration.

`contracts.py` is the shared implementation used by both the independent Python
fixture tests and the live R oracle check. A comparison produces a structured
record conforming to `../schemas/parity-evidence.schema.json`, including source
revision and dirty-tree state, package/runtime versions, exact input and output
hashes, the named policy, error maxima, and any mismatches. The live check writes these records to
ignored `.work/oracle-evidence/` by default, including failed comparisons before
raising the gate failure.

The source snapshot is supplied as an external Docker build context and is not
vendored here. Other R dependency versions and the successful arm64 image
identity are recorded in `expected/oracle-environment.json`.
The complete environment contract, input hashes, and accepted image/platform
identity are recorded in `../environments/r-oracle-8.2-0-lock.json` and explained
in `../docs/reproducibility/FROZEN_ENVIRONMENTS.md`.

## Build and verification

```sh
make oracle-build RMS_SOURCE=/absolute/path/to/rms-master
make frozen-environments-live
make oracle-check
make tolerance-pilot
make phase-1-e2e
make reference-source-check RMS_SOURCE=/absolute/path/to/rms-master
```

`make oracle-check` discovers every committed case, validates its case and output
schemas, executes it through the live container, applies its named comparison
profile, and emits validated evidence. Normal Python tests independently compute
the 31 implemented data-distribution, formula-design, spline-design, OLS,
generalized-linear, and binary-logistic results and use the same profiles
against those outputs; they do not invoke Docker or R. The remaining nine
statistical cases are oracle baselines for deferred ordinal and survival
implementations. `make reference-metadata` validates every schema, policy,
fixture, and cross-document link without Docker and runs in ordinary CI.

`make frozen-environments` is the Docker-free CI gate for the committed Python
and R environment contracts. `make frozen-environments-live` additionally fails
unless the local oracle tag resolves to the accepted image ID and Linux/arm64
platform.

`make tolerance-pilot` independently recomputes all cases labeled
`python-parity`, records the local Python, NumPy, OS, architecture, and
BLAS/LAPACK identity, and validates a report against
`../schemas/tolerance-pilot.schema.json`. CI runs this gate on the two platforms
accepted by ADR-009.

`make phase-1-e2e` runs the accepted `ols-rcs-explicit` exit case through the
public design, fit, and prediction APIs; validates the Python output; compares it
with the pinned R output under `well-conditioned-ols-v1`; and writes validated,
hashed evidence to `.work/phase-1-evidence/`. CI uses
`make phase-1-exit-gate`, which additionally requires clean source provenance,
and retains the evidence artifact for 30 days.

The runtime container is non-root, offline, read-only, capability-free, and
resource-limited. The protocol accepts data-only operations rather than
arbitrary R expressions or formulas.

The committed inventory records 121 exports and 160 registered S3 methods. The
machine-readable compatibility disposition for all 281 entries is
`../compatibility/rms-8.2.0.yaml`.

To add a case:

1. add a uniquely named case document and declare an existing reviewed profile;
2. generate its output only from the pinned live oracle and add the immutable
   reference identity;
3. add an independent Python test that uses the shared comparator;
4. link the case and profile from the compatibility manifest; and
5. run `make check` and `make oracle-check` before review.

Candidate fixtures can be generated into `.work/candidate-expected/` with
`uv run --frozen python -m reference.generate_expected`. The explicit
`--accept` flag writes them to `reference/expected/`; all generated fixtures
still require review and the full live-oracle gate.
