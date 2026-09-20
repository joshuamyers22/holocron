# Phase 8 extended-model and exported-helper disposition

**Decision date:** 2026-09-19  
**Scope:** first Phase 8 deliverable  
**Decision:** complete within the bounded Python-native replacement envelope

## Accepted model replacements

`Gls`, `Rq`, `bj`, and `pphsm` are `mapped`, not parity-qualified. Their owned
Python contracts are respectively `fit_gls`, `fit_quantile_regression`,
`fit_buckley_james`, and `to_proportional_hazards`.

- GLS accepts a fixed, caller-supplied positive-definite relative observation
  covariance and estimates one ML or REML scale. It does not estimate `nlme`
  correlation or variance structures.
- Quantile regression fits one weighted quantile by deterministic ADMM. Its
  covariance is a kernel-density sandwich approximation, not `quantreg`
  inference parity.
- Buckley–James covers right censoring with identity or log time and
  Kaplan–Meier residual-tail imputation. It fails on nonconvergence and does not
  cycle-average; its covariance is an event-only working OLS approximation, not
  bootstrap or `rms` inference parity.
- The parametric PH adapter exactly transforms one-scale Weibull or exponential
  AFT coefficients and predictions. Its covariance is conditional on the
  fitted scale, and scale-stratified fits are rejected.

All four results are immutable, have strict canonical JSON, stable
fingerprints, bounded versioned schemas, and explicit prediction methods.

## Export disposition

This review covers all 42 Phase 8 entries whose manifest kind is `export`.
`Penalty.matrix` and `Penalty.setup` retain their existing experimental
contracts. `processMI` and `prmiInfo` remain intentionally deferred together to
the next Phase 8 deliverable; separating them would create a misleading partial
multiple-imputation contract.

That time-bounded deferral was subsequently resolved by
`PHASE_8_MULTIPLE_IMPUTATION.md`; the compatibility manifest now records both
exports as mapped.

| R export(s) | Decision | Approved Python path or rationale |
| --- | --- | --- |
| `Gls` | mapped | `holocron.models.fit_gls` |
| `Rq` | mapped | `holocron.models.fit_quantile_regression` |
| `bj` | mapped | `holocron.models.fit_buckley_james` |
| `pphsm` | mapped | `holocron.models.to_proportional_hazards` |
| `Penalty.matrix`, `Penalty.setup` | experimental | Existing explicit diagonal-penalty fit APIs |
| `Surv` | mapped | `holocron.models.SurvivalResponse` |
| `coxphFit` | mapped | `holocron.models.fit_cph` |
| `dxy.cens`, `groupkm` | mapped | `validate_survival_predictions` with explicit horizons |
| `gendata` | mapped | fitted `DesignSpec.transform` |
| `impactPO`, `poma` | mapped | `OrdinalResult.diagnostics` |
| `intCalibration` | mapped | `validate_probabilities` |
| `lm.pfit` | mapped | `fit_penalized_ols` |
| `lrtest` | mapped | typed `likelihood` operation |
| `pantext` | mapped | `TextAnnotation` in a `PlotSpec` |
| `prModFit`, `prModItem` | mapped | typed reporting adapters and `TableSpec` |
| `probabilityFamilies` | mapped | explicit supported family in `fit_glm` |
| `recode2integer` | mapped | explicit categorical/ordered `DesignSpec` terms |
| `rexVar` | mapped | bounded `fit_random_intercept_orm` result |
| `show.influence`, `which.influence` | mapped | typed `influence_diagnostics` result |
| `survreg.auxinfo` | mapped | explicit `ParametricSurvivalResult` fields |
| `LRupdate` | unsupported | use explicit calibration APIs; fit mutation is rejected |
| `combineRelatedPredictors`, `related.predictors` | unsupported | review externally and encode the selected design explicitly |
| `corFloorExp` | unsupported | construct/review a covariance and pass it to `fit_gls` |
| `cr.setup`, `ie.setup`, `infoMxop` | unsupported | internal mutable setup operations are not public contracts |
| `formatNP` | unsupported | use typed tables and application presentation formatting |
| `gIndex` | unsupported | select named metrics from validation results |
| `matinv` | unsupported | use `numpy.linalg.solve`; estimators own rank-failure translation |
| `perimeter` | unsupported | provide reviewed plot-domain bounds explicitly |
| `reListclean` | unsupported | use typed Python collections |
| `sensuc` | unsupported | no numerical substitute is approved |
| `setPb` | unsupported | progress reporting belongs to the calling application |
| `univarLR` | unsupported | fit prespecified models explicitly; implicit screening is rejected |
| `processMI`, `prmiInfo` | deferred | next Phase 8 multiple-imputation adapter deliverable |

The machine-readable authority is `compatibility/rms-8.2.0.yaml`; this table is
the review rationale, not a second manifest.

## Evidence and limitations

Focused tests cover deterministic fitting, fixed-covariance GLS, weighting,
convergence failure, censoring requirements, AFT/PH prediction equivalence,
strict reconstruction, schema validation, and invalid inputs. These are owned
Python tests. No new pinned-R oracle cases or tolerance profiles were added, so
the new model entries remain `mapped` and must not be described as
`experimental` parity capabilities.

This decision did not complete Phase 8. Multiple imputation was completed by
the next decision; full method-level namespace disposition, retained-profile
tuning, migration tooling, and the Phase 8 exit review remain open.
