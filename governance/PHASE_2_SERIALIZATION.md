# Phase 2 design/result serialization acceptance record

- Acceptance date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22

## Accepted contract

The fourth Phase 2 deliverable is complete. `DataDistribution`, `Formula`,
`DesignSpec`, `DesignMatrix`, and `OlsResult` have explicit versioned JSON
documents and deterministic canonical writers. The design specification remains
the reconstructible transformation contract; a realized matrix retains its
specification fingerprint and intercept policy, and an OLS result fitted from
that matrix retains and checks the same identity during prediction.

The repository and installed package contain JSON Schema Draft 2020-12 contracts
plus a serialization manifest. Readers accept only exact current versions and
reject unknown fields, duplicate keys, non-finite values, malformed Unicode,
oversized documents, invalid hashes, inconsistent dimensions, and violated
statistical invariants. No executable object format is supported.

## Acceptance evidence

- Schema validation covers design specifications, realized matrices, and OLS
  result documents alongside the existing formula and distribution contracts.
- Unit tests cover canonical round trips, fingerprints, future/unknown fields,
  duplicate-key and non-finite JSON, tampered design identity, inconsistent
  arrays, and prediction with a mismatched design.
- Strict type checking and the complete existing parity corpus continue to pass.
- Wheel and source-distribution inspection requires all public schemas; fresh
  installation smoke tests round-trip the design matrix and fitted result.
- ADR-008 fixes non-executable JSON, version evolution, migration, identity, and
  sensitive-result handling rules.

## Deliberate boundaries

This record stabilizes the meaning of the named schema versions, not the entire
pre-alpha Python API. Current readers do not migrate older versions, and a
support window is deferred until beta. OLS is the only serializable fitted-result
family. Fingerprints are deterministic identities, not authentication or access
control. Result documents can contain sensitive input-derived values and are not
parity-evidence artifacts by default.
