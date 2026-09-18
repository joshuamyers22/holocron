# Threat model

- Scope: private Holocron repository, Python package, build/release automation,
  and test-only R oracle
- Version/date/owner: 1 / 2026-09-17 / joshuamyers22
- Review triggers: formula parser, serialization, external distribution, hosted
  service, untrusted data adapter, new oracle operation, or annual review
- Assets: statistical correctness, compatibility claims, source provenance,
  repository credentials, release artifacts, user data supplied at runtime
- Actors: ordinary users, mistaken contributors, malicious data/artifact
  producers, compromised dependencies or CI actions, and privileged maintainers
- Trust boundaries: caller data and formula text to Python; source
  snapshot and network dependencies to oracle build; JSON to offline oracle;
  GitHub events to CI; built artifacts to users

| Abuse case | Impact | Prevention/detection/response | Evidence | Residual risk owner |
|---|---|---|---|---|
| Formula or callback injection | Arbitrary code execution | Allowlisted additive AST, custom parser with no general evaluation, adversarial syntax tests | `src/holocron/formula/`; ADR-005; formula-design acceptance record | joshuamyers22 |
| Malicious serialized model | Code execution or silent model drift | No supported pickle interchange; versioned data-only schema with limits | ADR-008 required before persistence | joshuamyers22 |
| Huge interaction/design request | Memory/CPU exhaustion | Formula length/name/term/column/degree/knot limits; interaction cardinality gate remains required | Formula-design acceptance record; interactions remain deferred | joshuamyers22 |
| Pathological resampling request | Denial of service or partial evidence presented as complete | Bounded plans, explicit failures, retained completion counts | Phase 6 requirement | joshuamyers22 |
| Crafted dataframe producer | Type confusion, row mismatch, data leakage | Canonical validated boundary, retained row identity, copy/ownership policy | ADR-006 accepted; dataframe adapters remain gated | joshuamyers22 |
| Oracle JSON used as code channel | Build/runtime compromise | Fixed operation allowlist, no arbitrary formulas, non-root offline read-only runtime | `reference/r/oracle.R`; runner flags | joshuamyers22 |
| Compromised oracle dependency | False reference outputs | Base digest, dated repository, pinned commits, package manifest, source checksums | ADR-003; oracle health fixture | joshuamyers22 |
| Compromised Python dependency/action | Build or credential compromise | Lock, audits, full-SHA actions, least privileges, SBOM at release | CI workflows; `uv.lock` | joshuamyers22 |
| Secret or sensitive data committed/logged | Disclosure | Secret scanning, synthetic/public fixtures only, sanitized future evidence | Security workflow; project brief | joshuamyers22 |
| Unsupported fit reported as successful | Scientific harm | Fail-closed errors/statuses, compatibility manifest, simulation and review gates | ADR-004 | Statistical reviewer (vacant) |
| GPL material copied into proprietary implementation | Distribution injunction/rewrite | Provenance attestations, isolated reference tree, legal distribution gate | ADR-001; provenance policy | License reviewer (vacant) |
| Maintainer privilege misuse or account takeover | Malicious release or policy bypass | Private repo, least-privilege workflows; protected release approvals required before publishing | Release workflow review pending | joshuamyers22 |

No production service, telemetry collector, or user-data store exists. Their
authorization, retention, privacy, availability, and incident controls are out
of scope until introduced by an approved design change.
