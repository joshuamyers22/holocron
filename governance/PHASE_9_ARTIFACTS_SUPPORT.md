# Phase 9 signed artifacts and support decision

**Decision date:** 2026-09-20  
**Implementation decision:** complete  
**First signed release set:** pending an approved tag

## Decision

The fifth Phase 9 deliverable is complete as a release supply-chain and support
contract. An authorized tag build now produces one wheel, one source
distribution, a CycloneDX JSON SBOM, an exact-commit release manifest, and a
SHA-256 index. GitHub Actions obtains a short-lived identity through OIDC and
uses keyless Sigstore signing to create a bundle for each of those five assets.
The signing action verifies the workflow identity and issuer before the release
action publishes any file.

The manifest binds artifact bytes to the package version, tag, full source
revision, workflow identity, workflow run, distribution-approval record,
changelog, support policy, contribution-provenance policy, and artifact policy.
The checksum index covers the wheel, source distribution, SBOM, and manifest;
it is then itself signed. This avoids a circular self-hash while protecting the
complete index with a transparency-log-backed signature.

`SUPPORT.md` owns the planned stable-release lifecycle, supported Python
versions, support owner and channels, triage targets, compatibility boundary,
deprecation window, and end-of-support behavior. It explicitly provides no
support or service-level claim for the current private 0.1.0 package.

## Enforcement

The authoritative contract is `governance/phase-9-artifact-policy.json`.
`tools.check_phase_9_supply_chain` validates that policy, all referenced files,
and the fail-closed workflow topology. The release workflow additionally
requires an exact versioned changelog heading before it can create metadata.

```sh
make phase-9-supply-chain-check
make phase-9-supply-chain-evidence ARTIFACT_DIRECTORY=/path/to/release-assets
```

The evidence form validates the built wheel and source distribution, SBOM
format, manifest schema and artifact hashes, exact checksum membership, and the
presence and JSON structure of all five Sigstore bundles. Cryptographic bundle
verification occurs in the identity-bearing release job; consumers must also
verify downloaded bundles against the declared GitHub workflow identity and
OIDC issuer.

## Remaining release boundary

No signed release artifact set is fabricated or claimed by this decision.
Creation requires a real approved tag, a repository-relative written approval
record, completed upstream release gates, and the protected release workflow.
Consequently the readiness control for an exact-tag artifact/SBOM/signature set
remains blocked until that first authorized workflow completes. The support
policy control passes, but stable release remains blocked by the other recorded
controls and the separate response-procedure deliverable.

This decision does not authorize external distribution, PyPI publication,
stable capability claims, or consequential use.
