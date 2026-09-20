# Phase 8 complete namespace disposition

**Decision date:** 2026-09-19

**Scope:** third Phase 8 deliverable; all 281 pinned `rms` namespace entries

**Decision:** complete, with no unreviewed or deferred entries

## Decision rule

Every exported function and registered S3 method in the pinned `rms` 8.2-0
namespace now has one of three current dispositions:

- `experimental` means Holocron has an independently implemented, oracle-linked
  capability within a documented narrow envelope;
- `mapped` means an owned Python contract is the approved migration path, but
  the mapping itself is not an R-parity or production-readiness claim; and
- `unsupported` means the behavior is intentionally outside the current
  compatibility target. A future reviewed manifest revision may reconsider it.

The final inventory contains 50 experimental, 125 mapped, and 106 unsupported
entries. It contains zero `deferred` entries and zero generic "not yet
implemented" placeholders. `compatibility/rms-8.2.0.yaml` remains the
machine-readable authority and records this review explicitly.

## Approved migration families

The mapped entries reduce to owned contracts rather than one-for-one R syntax:

| R capability family | Approved Python contract | Boundary |
| --- | --- | --- |
| design assignment, model data, and specifications | immutable `DesignSpec`, `DesignMatrix`, and generated-column metadata | no R environments, mutable attributes, or arbitrary formula evaluation |
| prediction, effects, and contrasts | `models.predict`, family-specific ordinal/survival methods, and `models.contrast` | explicit realized rows; no automatic adjustment frames or broad S3 dispatch |
| OLS, binary lrm, orm, GLS, quantile, Buckley--James, and survival fitting | public typed estimator functions and immutable results | only each estimator's published bounded envelope |
| validation, calibration, and resampling | exact `ResamplePlan`, `validate_model`, `calibrate_model`, `validate_probabilities`, and `validate_survival_predictions` | no hidden resampling, generic model dispatch, or unsupported family refits |
| diagnostics and selection | typed influence, VIF, robustness, penalty-trace, and backward-selection results | OLS/binary boundaries and explicit selection groups remain |
| plots and nomograms | typed `PlotSpec`/`NomogramGeometry` adapters plus explicit SVG renderers | no graphics-device state, ggplot2/plotly objects, or R visual parity |
| tables and LaTeX | typed `TableSpec` adapters and escaped `render_latex` | no R console/HTML layout, global options, or raw-markup path |
| multiple imputation | explicit homogeneous pooling and typed information tables | no imputation generation, `fit.mult.impute`, or R S3 objects |

## Unsupported families and user-facing alternatives

The following entries are intentionally excluded. The alternatives are the
approved way to accomplish the supported part of the task; they are not claims
that the omitted behavior is equivalent.

| Unsupported entries | Rationale and approved alternative |
| --- | --- |
| `Newlabels`, `Newlevels`, `Newlabels.rms`, `Newlevels.rms`, `[.Ocens`, `[.rms`, `as.data.frame.Ocens`, `as.data.frame.rms`, `is.na.Ocens`, `rbind.Predict` | Holocron objects are immutable and are not data frames. Rebuild `DataDistribution`, `DesignSpec`, or `CensoredResponse` explicitly; combine caller-owned prediction data before creating typed results. |
| `adapt_orm`, `gTrans`, `matrx`, `Function.cph`, `Function.rms`, `makepredictcall.rms` | Internal adaptation, arbitrary executable transforms, R expression generation, and callable factories are excluded. Use allowlisted formulas, explicit numeric designs, and typed prediction methods. |
| `Initialize.corFloorExp`, `coef.corFloorExp`, `coef<-.corFloorExp`, `corMatrix.corFloorExp`, `print.corFloorExp` | The mutable `nlme` correlation structure is not implemented. Construct and review a positive-definite covariance explicitly, then pass it to `fit_gls`. |
| `bootBCa`, `bootplot` | BCa intervals and stored bootstrap-distribution plotting are absent. Use exact resample plans or the supported iid bootstrap covariance, retaining caller-owned replicate estimates when a custom interval is scientifically approved. |
| `oos.loglik`, `oos.loglik.Glm`, `oos.loglik.cph`, `oos.loglik.lrm`, `oos.loglik.ols`, `oos.loglik.psm` | No generic out-of-sample log-likelihood contract is approved. Use declared held-out predictions and a model-appropriate, explicitly defined scoring rule. |
| `calibrate.cph`, `calibrate.orm`, `calibrate.psm` | Whole-model resampled calibration for these families is absent. Use fixed-horizon survival validation where applicable; otherwise implement and review the full resampled procedure outside Holocron. |
| `validate.Rq`, `validate.bj`, `validate.orm`, `validate.rpart` | Whole-model refitting and family-specific indices are absent. Use `run_resample_plan` with a caller-owned complete procedure and retain its typed failure report without labeling it rms validation. |
| `ordESS` | No effective-sample-size statistic for ordinal intercepts is approved. Report observed category counts and an analysis-specific information assessment instead. |
| `residuals.orm`, `lines.residuals.psm.censored.normalized`, `survplot.residuals.psm.censored.normalized` | These residual definitions or presentation paths are absent. Use published typed residuals only; do not substitute a different residual under the same name. |
| `bjplot`, `bplot`, `hazard.ratio.plot`, `histdensity`, `plot.lrm.partial`, `plot.xmean.ordinaly`, `plotIntercepts`, `survdiffplot`, `plot.ExProb`, `plot.gIndex`, `plot.rexVar`, `plot.sensuc`, `plot.validate.rpart`, `survplot.orm` | No owned adapter exists for these semantics. Build an explicit reviewed `PlotSpec` from caller-computed values, or keep the analysis outside Holocron. |
| `legend.nomabbrev` | Abbreviation lookup tied to R nomogram device state is excluded. Put full reviewed labels and legend order directly in `NomogramGeometry` or `PlotSpec`. |
| `perlcode`, `sascode` | Cross-language code generation is excluded because it would create a second unverified execution contract. Exchange versioned design/result JSON and revalidate in the target system instead. |
| `html.anova.rms`, `html.naprint.delete`, `html.summary.rms`, `html.validate` | Holocron has no HTML renderer. Use typed tables with the safe LaTeX renderer or let an application render escaped table values. |
| `latex.Gls`, `latex.Rq`, `latex.bj`, `latex.cph`, `latex.naprint.delete`, `latex.orm`, `latex.pphsm`, `latex.psm` | No typed table adapter exists for these result families. Construct an explicit `TableSpec` from reviewed fields before calling `render_latex`. |
| `print.Gls`, `print.Ocens`, `print.Predict`, `print.Rq`, `print.bj`, `print.calibrate`, `print.cph`, `print.datadist`, `print.fastbw`, `print.gIndex`, `print.impactPO`, `print.lrtest`, `print.orm`, `print.pphsm`, `print.psm`, `print.rexVar`, `print.specs.rms`, `print.summary.survreg2`, `print.survest.psm`, `print.validate.rpart` | R console methods are not statistical contracts. Inspect typed fields directly or use an available `TableSpec`; applications own any additional presentation. |

Other entries already classified `unsupported` retain their symbol-specific
rationale in the manifest, including internal setup helpers, implicit screening,
unmeasured-confounding analysis, device mutation, and public matrix inversion.

## Verification and consequence

The reference-metadata gate now rejects any deferred entry, generic placeholder,
mapped entry without a resolvable public Python path, or unsupported entry with
an attached Python entry point. A focused namespace test locks the reviewed
status counts and all 281 identifiers. Generated compatibility documentation
shows the final inventory.

This decision completes namespace disposition only. It does not implement the
106 unsupported behaviors, add oracle evidence, promote experimental
capabilities, authorize consequential use, or approve external distribution.
Retained-profile performance tuning and migration/deprecation policy were
completed by subsequent Phase 8 decisions. The accountable completion review
in `PHASE_8_COMPLETION.md` subsequently passed the private-development exit
gate.
