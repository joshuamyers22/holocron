# Package structure and public API

Holocron is a scientific Python library, not an application or a runtime R
bridge. Its installed package contains only reusable statistical code and
package metadata.

## Supported namespaces

| Namespace | Responsibility | Current public objects |
|---|---|---|
| `holocron.design` | Immutable predictor metadata, compiled design specifications, and deterministic transformations | `DataDistribution`, `DesignSpec`, `DesignMatrix`, `GeneratedColumn`, `RestrictedCubicSplineSpec`, distribution records |
| `holocron.formula` | Allowlisted formula AST, bounded parsing, and canonical serialization | `Formula`, `Variable`, identity/polynomial/linear-spline/RCS term nodes |
| `holocron.graphics` | Backend-neutral plot/nomogram data, typed result adapters, strict serialization, and owned SVG rendering | `PlotSpec`, `NomogramGeometry`, `effect_plot_spec`, `build_nomogram`, SVG renderers |
| `holocron.migration` | Installed reviewed R namespace catalog, typed migration plans, and deprecation policy records | `MigrationEntry`, `MigrationPlan`, `plan_rms_migration`, `deprecation_policy` |
| `holocron.reporting` | Backend-neutral typed tables, statistical result adapters, strict serialization, and safe LaTeX output | `TableSpec`, `model_summary_table`, `validation_table`, `render_latex` |
| `holocron.models` | Estimators, immutable fitted-result contracts, post-fit operations, and bounded diagnostics/selection | `fit_ols`, `fit_cph`, `influence_diagnostics`, `trace_penalty`, `backward_select`, `OlsResult`, `CoxResult` |
| `holocron.validation` | Exact resampling and failure reporting, model-specific refit validation/calibration and optimism correction, and model-independent probability/survival metrics | `ResamplePlan`, `report_resample_execution`, `validate_model`, `calibrate_model`, `optimism_correct_validation`, `optimism_correct_calibration`, `validate_probabilities`, `validate_survival_predictions` |
| `holocron.exceptions` | Stable failure categories at public boundaries | `HolocronError` and specific subclasses |

The package root exports the eight namespaces and `__version__`. Statistical
objects are not duplicated at the root. A name is public only when it is listed
in the nearest package's `__all__`; implementation modules may change without
notice while the project is experimental.

New domains will receive a namespace only with a working vertical capability.
Models owns diagnostics that directly inspect or refit supported model
families, including influence, VIF, robustness, explicit penalty grids, and
declared-group selection. Validation owns exact resampling, current fixed-design OLS/binary refits and
optimism correction, and model-independent binary/right-censored survival
metrics. Graphics owns source-data specifications, typed result adapters,
additive OLS/logit nomogram geometry, and dependency-free SVG backends.
Reporting owns typed raw-value tables, result-to-table adapters, and the
dependency-free LaTeX backend. Migration owns data-only compatibility planning
and Python API lifecycle records; it does not translate or execute R code.

## Dependency direction

```text
holocron.formula -----> holocron.exceptions
       |                         ^
       v                         |
holocron.design -----------------+
       |                         ^
       +-----> NumPy <----- holocron.models
                  ^              |
                  |              v
                  +----- holocron.validation

holocron.graphics -----> holocron.models/validation -----> holocron.exceptions
holocron.reporting ----> holocron.models/validation -----> holocron.exceptions
holocron.migration ----> packaged reviewed catalog ------> holocron.exceptions
```

Public result and specification objects are owned by Holocron. Third-party
model-result objects and dataframe implementations must not leak through public
contracts. The current slice accepts named Python iterables and returns owned
objects or NumPy arrays. ADR-006 establishes the canonical data boundary; the
estimator backend remains a blocking decision in ADR-007. Unused dataframe and
modeling dependencies are therefore not installed preemptively.

## Runtime and test boundaries

- Importing `holocron` performs no file, process, network, or configuration I/O.
- R, Docker, and the oracle are development/test assets only.
- Oracle cases and expected outputs live under `reference/` and are excluded
  from wheels and source distributions.
- No installed CLI exists. The development-only parity laboratory validates
  versioned case, output, policy, and evidence schemas under `reference/` and
  `schemas/`; it is excluded from distributions and never called at runtime.
- The public data-only schemas and serialization manifest are deliberately
  copied into wheel package data at `holocron/schemas`; oracle and evidence
  schemas remain repository-only development assets.
- Unsupported statistical combinations raise a typed error; they do not select
  a different method silently.

## Adding a public capability

A change to the public API must update the compatibility manifest, add tests for
the supported and rejected envelopes, document numerical and missing-data
behavior, and provide the evidence required by ADR-004. New dependencies must
serve a supported implementation, pass license/audit checks, and respect the
backend and table-boundary ADRs.
