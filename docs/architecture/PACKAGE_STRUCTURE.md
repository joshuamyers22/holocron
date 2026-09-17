# Package structure and public API

Holocron is a scientific Python library, not an application or a runtime R
bridge. Its installed package contains only reusable statistical code and
package metadata.

## Supported namespaces

| Namespace | Responsibility | Current public objects |
|---|---|---|
| `holocron.design` | Immutable design specifications and deterministic transformations | `RestrictedCubicSplineSpec` |
| `holocron.models` | Estimators and immutable fitted-result contracts | `fit_ols`, `OlsResult` |
| `holocron.exceptions` | Stable failure categories at public boundaries | `HolocronError` and specific subclasses |

The package root exports the three namespaces and `__version__`. Statistical
objects are not duplicated at the root. A name is public only when it is listed
in the nearest package's `__all__`; implementation modules may change without
notice while the project is experimental.

New domains will receive a namespace only with a working vertical capability.
Planned areas such as formulas, data-distribution metadata, inference,
survival, validation, graphics, reporting, and serialization are not represented
by empty placeholder packages.

## Dependency direction

```text
holocron.design -----> holocron.exceptions
holocron.models -----> holocron.exceptions
        |                    |
        +------> NumPy <-----+
```

Public result and specification objects are owned by Holocron. Third-party
model-result objects and dataframe implementations must not leak through public
contracts. The current slice accepts Python iterables and returns owned objects
or NumPy arrays. The canonical table boundary and estimator backend remain
blocking decisions in ADR-006 and ADR-007; unused dataframe and modeling
dependencies are therefore not installed preemptively.

## Runtime and test boundaries

- Importing `holocron` performs no file, process, network, or configuration I/O.
- R, Docker, and the oracle are development/test assets only.
- Oracle cases and expected outputs live under `reference/` and are excluded
  from wheels and source distributions.
- No supported CLI exists. Reproducible evidence and comparison commands will
  be added only with their Phase 1 schemas and end-to-end contract.
- Unsupported statistical combinations raise a typed error; they do not select
  a different method silently.

## Adding a public capability

A change to the public API must update the compatibility manifest, add tests for
the supported and rejected envelopes, document numerical and missing-data
behavior, and provide the evidence required by ADR-004. New dependencies must
serve a supported implementation, pass license/audit checks, and respect the
backend and table-boundary ADRs.
