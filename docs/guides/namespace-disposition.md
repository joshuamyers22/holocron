# Namespace disposition and migration choices

Holocron accounts for every export and registered S3 method in the pinned
`rms` 8.2-0 namespace. A name appearing in the inventory does not by itself
mean that Holocron implements or reproduces it.

## Read the status first

- **Experimental** identifies an implemented, oracle-linked capability inside a
  narrow documented envelope. It is still not production-ready.
- **Mapped** points to the approved Python-native workflow. Mapped behavior may
  intentionally differ from R and does not imply numerical parity.
- **Unsupported** is an explicit stop boundary for the current compatibility
  target, not an invitation to silently substitute another method.

There are no deferred or unreviewed namespace entries. The generated
[compatibility inventory](../compatibility.md) is the symbol-level authority.
Use the typed planner described in the
[migration and deprecation guide](migration-and-deprecation.md) to query this
inventory from an installed artifact and retain a digest-bound assessment.

## Common migrations

| If the R workflow relies on... | Use... |
| --- | --- |
| formula environments or mutable `Design` attributes | immutable `DesignSpec`, `DesignMatrix`, and explicit source data |
| generic `Predict`/`predictrms` dispatch | explicit design rows with `models.predict`, or the fitted family's typed methods |
| `validate`/`calibrate` method strings | an exact `ResamplePlan` and the supported typed validation/calibration function |
| implicit print, HTML, or LaTeX methods | typed `TableSpec`; call `render_latex` explicitly where an adapter exists |
| R graphics or ggplot dispatch | build a typed `PlotSpec` and select `render_svg` explicitly |
| `nomogram`/`plot.nomogram` | bounded additive `build_nomogram` and `render_nomogram_svg` |
| `processMI`/`prmiInfo` | explicit homogeneous pooling and `imputation_information_table` |

## Stop instead of substituting

Stop and redesign or perform a separately reviewed external analysis when the
workflow requires an unsupported residual definition, whole-model validation
family, correlation-structure estimation, BCa inference, arbitrary executable
transformation, R object mutation, cross-language code generation, interactive
plotting, or a presentation adapter that does not exist. A generic plot or
table built from caller-computed values must be labeled as that caller-owned
analysis, not as the corresponding `rms` method.

The complete grouped rationale is recorded in the
[Phase 8 namespace decision](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_8_NAMESPACE_DISPOSITION.md).
