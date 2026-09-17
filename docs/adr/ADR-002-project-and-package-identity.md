# ADR-002: Project, import, and distribution identity

- Status: accepted for private development
- Date: 2026-09-17
- Owner: joshuamyers22

## Context and options

The requested project and repository name is Holocron. Python distribution and
import names need not be identical. The `holocron` distribution name is already
occupied on PyPI by an unrelated static-site generator, and several unrelated
software projects also use the word. Package-index availability is not trademark
clearance.

Options considered were attempting to reuse `holocron`, changing the entire
project identity, or retaining Holocron while selecting a distinct distribution
name.

## Decision and consequences

- Project name: **Holocron**.
- Repository: `joshuamyers22/holocron`, private during the distribution gate.
- Python import package: `holocron`.
- Python distribution name: `holocron-rms`.
- Compatibility claims use “independent Python implementation of R `rms`” and
  must not imply affiliation with or endorsement by the `rms` authors.
- The project does not claim ownership of the names `rms` or Holocron outside
  this repository.

`holocron-rms` returned no PyPI project on 2026-09-17, but the name is not
reserved and must be checked again immediately before any publication. Formal
name/trademark clearance remains part of the external-distribution gate.

## Verification

- `pyproject.toml` uses `holocron-rms`; imports and repository paths use
  `holocron`.
- Release verification must reject the distribution name `holocron`.
- Reconsider this decision if `holocron-rms` becomes unavailable, counsel
  identifies a naming risk, or import-name coexistence becomes impractical.
