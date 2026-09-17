# ADR-011: Adapt the production scaffold as a scientific library

- Status: accepted
- Date: 2026-09-17
- Owner: joshuamyers22
- Supersedes / superseded by: none

## Context and forces

Holocron was generated from the production template's `python-data-quant`
archetype. That supplied useful repository, reproducibility, verification,
supply-chain, and statistical-review controls, but it also included example
market-data publication, generic Statsmodels analysis, walk-forward validation,
and four command-line applications. Those examples were not `rms` capabilities
and could be mistaken for supported Holocron APIs.

ADRs 005–010 are reserved for the blocking statistical and release decisions in
the project plan, so this repository-shape decision uses ADR-011.

## Decision

- Preserve the template's repository controls, locked environment, CI, release
  gate, documentation templates, strict typing, audit, and artifact inspection.
- Remove the example application CLIs, market-data publisher, generic regression
  evidence flow, walk-forward validation flow, their fixtures, and their tests.
- Ship Holocron as a PEP 561 typed library with no console entry points.
- Organize public statistical APIs by domain. The package root exposes only the
  domain namespaces and version; each namespace owns its explicit `__all__`.
- Add namespaces only with an implemented vertical capability rather than
  creating speculative placeholder packages.
- Expose Holocron-owned results and exception categories. Do not expose a
  third-party fitted object as a public contract.
- Keep only dependencies exercised by supported package code. Table adapters
  and statistical backends will be added after ADR-006 and ADR-007 respectively.

## Consequences

The installed distribution has a smaller and less ambiguous surface, and users
cannot invoke template demonstrations as if they were `rms` parity features.
The repository still retains general engineering and review material where it
governs future work. Removing the demonstrations reduces generic functionality,
but no compatibility entry depended on it and Git history preserves it.

Future evidence and comparison tooling must be designed around Holocron's
versioned Phase 1 schemas rather than reviving the removed generic contracts.
Dataframe and backend convenience is deferred until the relevant ADRs establish
ownership, dtype, missingness, and numerical behavior.

## Verification

- Unit tests assert the public namespace and typed exception hierarchy.
- Packaging checks require `py.typed` and reject retired template modules.
- The manifest has no console entry points or unused Polars/Statsmodels runtime
  dependencies.
- `make check`, `make build`, and `make audit` remain the repository gates.
