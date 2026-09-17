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
make reference-source-check RMS_SOURCE=/absolute/path/to/rms-master
```

`make oracle-check` executes the committed project-authored cases through the
live container and compares them to the committed oracle outputs. Normal Python
tests independently compute the same results and compare them to those outputs;
they do not invoke Docker or R.

`make frozen-environments` is the Docker-free CI gate for the committed Python
and R environment contracts. `make frozen-environments-live` additionally fails
unless the local oracle tag resolves to the accepted image ID and Linux/arm64
platform.

The runtime container is non-root, offline, read-only, capability-free, and
resource-limited. The protocol accepts data-only operations rather than
arbitrary R expressions or formulas.

The committed inventory records 121 exports and 160 registered S3 methods. The
machine-readable compatibility disposition for all 281 entries is
`../compatibility/rms-8.2.0.yaml`.
