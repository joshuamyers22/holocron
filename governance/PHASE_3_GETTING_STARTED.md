# Phase 3 complete getting-started workflow acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The fifth and final Phase 3 deliverable is complete. `docs/getting-started.md`
now presents one coherent, executable workflow from declared synthetic analysis
rows through predictor-distribution metadata, immutable formula/design policy,
continuous and binary fitting, named post-estimation operations, new-data
transformation and prediction, covariance sensitivity checks, penalization, and
strict JSON reconstruction.

The guide is deliberately workflow-complete only for the accepted Phase 3
surface. It does not imply that the broader `rms` workflow or a defensible
applied analysis is complete.

## Acceptance evidence

- The single marked program executes offline through the documentation gate. It
  constructs 24 synthetic rows and explicitly declares continuous summaries,
  categorical order/reference, labels, units, spline knots, cluster identity,
  and seeded resampling.
- The OLS path verifies design identity, likelihood metadata, coefficient
  summary, formula-term ANOVA, a named group-coefficient contrast, standardized
  residuals, mean prediction intervals on transformed future rows, clustered
  covariance, 40-replicate bootstrap covariance, and diagonal penalization.
- The binary path verifies design identity, binary `lrm` fitting, coefficient
  summary, response-scale prediction, deviance residuals, penalized `lrm`, and
  finite probabilities.
- Distribution metadata, design specification, realized design, OLS result, and
  binary result all complete strict canonical JSON round trips. Prediction from
  the restored OLS result reproduces the typed prediction record.
- `tools/check_docs_examples.py` requires exactly one coherent executable block
  on the getting-started page and rejects the page if any accepted workflow
  output disappears. `make docs-check` also rejects broken links, stale
  generated pages, failed assertions, and strict MkDocs warnings.
- The separate artifact gate exercises the same public Phase 3 namespaces from
  independently installed wheel and source distributions, outside the checkout.

## Interpretation and boundaries

The example is synthetic and correctly specified. It is not evidence for
causality, model adequacy, transportability, real-world calibration, subgroup
performance, or clinical utility. Automatic knot/level selection, model-level
missingness, weights, offsets, internal validation, calibration correction,
model selection, bootstrap confidence intervals, and external validation remain
unsupported or future work and are stated beside the workflow.

All planned Phase 3 deliverables are complete. The Phase 3 exit gate
subsequently passed with independent statistical approval, as recorded in the
[completion record](PHASE_3_COMPLETION.md). Capability promotion beyond
experimental, numerical and independent verification, consequential use, and
external distribution remain separate open gates.
