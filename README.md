# Holocron

Holocron is an independent Python implementation of Frank Harrell's R
`rms` package. It aims to reproduce the integrated Regression Modeling
Strategies workflow—design metadata, estimation, inference, prediction,
validation, calibration, and graphics—with statistical fidelity and a
Python-native API.

The repository is in early implementation. The first qualified vertical slice
covers explicit-knot restricted cubic spline design and classical ordinary
least squares. Both are checked against committed outputs from a Dockerized R
oracle. These APIs remain experimental and are not yet production-ready. The
scope, milestones, and parity program are defined in
[PROJECT_PLAN.md](PROJECT_PLAN.md).

## Reference sources

- Local statistical source: `/Users/josh/Downloads/rms-master`, version 8.2-0
- Engineering source: `/Users/josh/Projects/production-project-template`

The R source is GPL-licensed reference material. It is not copied into this
repository. It enters a local, isolated Docker oracle as an external build
context. Holocron code is independently written in Python under
[ADR-001](docs/adr/ADR-001-independent-oracle.md). External distribution remains
blocked pending final license and provenance review.

## R oracle

Build the oracle from the local source snapshot and inspect its environment:

```sh
make oracle-build RMS_SOURCE=/Users/josh/Downloads/rms-master
make oracle-health
make oracle-check
```

At runtime the oracle has no network, capabilities, or writable root filesystem.
It accepts only versioned JSON operations; Holocron never calls R in production.
See [reference/README.md](reference/README.md) for pinned identities and the
two-stage oracle/independent-test workflow.

## Development

```sh
make setup
make check
make build
```

The generated quantitative examples remain as template validation fixtures for
the initial scaffold. Phase 1 will replace or relocate them as the public
Holocron API is established.

## Current maturity

Experimental and incomplete. Do not use this package for analysis, inference,
prediction, or clinical decisions.

<!-- The remaining generated-archetype documentation is retained temporarily. -->

## Generated archetype capabilities

The production scaffold includes the following example data and evidence tools;
they are not yet part of Holocron's intended public API.

Publish and verify an immutable, contract-checked Parquet dataset:

```sh
uv run holocron-dataset publish data/example.csv data/processed \
  --dataset-version 2026-01-02.1 \
  --source-id fixture/example.csv \
  --revision "$(git rev-parse HEAD)" \
  --created-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
uv run holocron-dataset verify data/processed/2026-01-02.1
```

The separate evidence command turns a pre-specified simple OLS run into a stable,
reviewable JSON artifact:

```sh
uv run holocron-regression data/regression-example.csv \
  --response return --predictor factor \
  --analysis-id factor-return-example \
  --analysis-plan templates/STATISTICAL_ANALYSIS_PLAN.md \
  --revision "$(git rev-parse HEAD)" \
  --evaluated-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --sample-filters "none; complete synthetic fixture" \
  --validation-design "illustrative in-sample inference only" \
  --leakage-controls "synthetic fixture; no future-derived features" \
  --output build/regression-evidence.json
```

For temporal prediction, run executable expanding-window validation with explicit
feature and target availability timestamps:

```sh
uv run holocron-validate data/walk-forward-example.csv \
  --response return --predictor factor \
  --prediction-time prediction_time \
  --feature-available-at feature_available_at \
  --target-available-at target_available_at \
  --initial-test-index 5 --test-size 2 --step-size 2 \
  --analysis-id factor-walk-forward-example \
  --analysis-plan templates/STATISTICAL_ANALYSIS_PLAN.md \
  --revision "$(git rev-parse HEAD)" \
  --evaluated-at-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --sample-filters "complete synthetic fixture" \
  --validation-design "non-overlapping expanding windows" \
  --leakage-controls "availability timestamps and strict label purging" \
  --output build/time-validation-evidence.json
```

Complete `PROJECT_BRIEF.md` before selecting architecture or adding dependencies.
Raw or restricted data is never committed. The included model uses explicit UTC
timestamps, units, decimal arithmetic, strict Polars CSV ingestion, and source
hashes. Schema inference is disabled at the trust boundary so numeric source text
cannot silently become binary floating point. Use Polars expressions and lazy
queries for tabular transformations; convert to domain values where precision or
business invariants require it.

Polars is the default dataframe library. Introduce pandas only behind a narrow
interop adapter when a required dependency or counterparty API demands it, and
record that exception in an ADR. Do not maintain parallel Polars and pandas
implementations of the same calculation.

Statsmodels is the default library for statistical inference, econometrics, time
series, and regression. `fit_simple_ols` demonstrates an explicit
Polars-to-NumPy-to-Statsmodels boundary, adds the intercept deliberately, rejects
missing/non-finite or degenerate samples, and defaults to HC3 robust covariance.
Choose the model, covariance estimator, diagnostics, multiple-testing policy,
and validation design from the research question—not from this example.
Complete `templates/STATISTICAL_ANALYSIS_PLAN.md` before consequential analysis.
Use `docs/STATISTICAL_LEARNING_POINT_OF_VIEW.md` to challenge the decision,
baseline, selection, leakage, stability, and serving design. It expresses
preferences, not deterministic rules; record sensible departures in the analysis
plan or an ADR.
For Bayesian regression implementation, use
`docs/BAYESIAN_REGRESSION_IMPLEMENTATION.md` and the applicable analysis-plan
fields. This guidance covers specification, priors, computation, and diagnostics;
the executable starter remains an OLS example and supplies no Bayesian estimator.
The evidence artifact binds the ordered design matrix and results to input and
analysis-plan hashes, code revision, evaluation time, and software versions. It
includes coefficient uncertainty, robust covariance choice, residual scale,
Durbin-Watson, condition number, and maximum Cook's distance. These diagnostics
surface review questions; they do not certify assumptions or replace time-aware
out-of-sample validation. See `docs/REGRESSION_EVIDENCE.md`.
The time-validation command rejects unordered timestamps, future features,
targets available at prediction time, overlapping test windows, and folds with
too few known labels. It purges labels unavailable before each test window,
refits both the model and training-mean baseline per fold, and retains every
out-of-sample prediction and aggregate comparison.

The Parquet publisher enforces exact Decimal/UTC schema, nullability, primary-key,
partition, sort, and domain invariants. Each immutable version has a deterministic
file layout and manifest covering source/revision/writer identity plus file hashes
and row counts. Verification precedes lazy scans. See
`docs/PARQUET_DATASETS.md` for compatibility and trust boundaries.

If this project develops a live or latency-sensitive path, complete
`templates/LATENCY_BUDGET.md`; keep offline research and production-path
correctness/replay evidence distinct.
