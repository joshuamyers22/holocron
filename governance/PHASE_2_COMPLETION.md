# Phase 2 completion record

- Completion date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

| Required deliverable | Status | Evidence |
|---|---|---|
| Data-distribution metadata | Complete | `governance/PHASE_2_DATA_DISTRIBUTION.md` |
| Formula AST and core transformations | Complete | `governance/PHASE_2_FORMULA_DESIGN.md` |
| Categorical/ordered handling and restricted interactions | Complete | `governance/PHASE_2_CATEGORICAL_INTERACTIONS.md` |
| Stable design/result schemas and serialization draft | Complete | `governance/PHASE_2_SERIALIZATION.md` |
| Exhaustive transformation differential/property tests | Complete | `governance/PHASE_2_TRANSFORMATION_TESTS.md` |
| R migration guide for design specifications | Complete | `governance/PHASE_2_R_MIGRATION_GUIDE.md` |
| Tier A design parity gate | Passed: 18 cases | `tools/run_phase_2_exit_gate.py`; `schemas/phase-2-exit-evidence.schema.json`; `.github/workflows/ci.yml` |
| Adversarial naming and prediction reconstruction | Passed | `design-adversarial-names`; `tests/test_phase_2_exit_gate.py` |
| Estimator promotion boundary | Preserved | `compatibility/rms-8.2.0.yaml`; Phase 2 exit evidence |

## Exit-gate disposition

The Phase 2 exit gate passes for private experimental development. All 18
independently implemented Tier A design cases are discovered from the versioned
parity corpus rather than duplicated in a gate-specific list: four `datadist`,
six restricted-cubic-spline transformation, and eight formula-design cases.
Together they perform 472 exact and 456 numeric comparisons against committed
outputs from the pinned R `rms` 8.2-0 oracle. All comparisons pass the approved
`data-distribution-v1`, `deterministic-transform-v1`, and `formula-design-v1`
contracts. The largest observed absolute error is
`1.4210854715202004e-13`, within the accepted field-aware envelope.

The gate explicitly requires `design-adversarial-names`, whose quoted response
and predictor names contain formula syntax. It then uses that case to fit a
full-rank experimental OLS result, round-trips the design specification,
training matrix, and result through their strict JSON readers, transforms new
data, and proves that original and reconstructed predictions are exactly equal
while retaining the same design fingerprint.

`make phase-2-evidence` writes a single schema-valid aggregate record to
`.work/phase-2-evidence/phase-2-exit.json`. The acceptance form,
`make phase-2-exit-gate`, additionally rejects dirty source or an unknown Git
revision. CI runs the clean gate on every push and pull request and retains the
evidence for 30 days. The gated release workflow requires the same check.

## Promotion boundary and remaining blocks

Passing this gate stabilizes the Phase 2 experimental design contract; it does
not promote an estimator or authorize distribution. The compatibility manifest
still classifies `ols` as `experimental` and `Glm` and `lrm` as `deferred`, and
the gate fails if those dispositions change without a later-phase governance
update. External distribution, production use, and non-experimental statistical
claims remain blocked by the license/provenance and specialist-reviewer gates.
Phase 3 model, result-operation, simulation, and failure-mode work is next.
