# Independent-development and contribution provenance

Holocron implementation code must be original Python written from approved
mathematical/public behavioral specifications and observations from the
data-only R oracle. The GPL-licensed `rms` and Hmisc sources are reference inputs,
not code-generation inputs or Python architecture templates.

Contributors must:

1. identify statistical literature, public documentation, oracle cases, and any
   source files consulted;
2. affirm that submitted implementation and test code was not mechanically
   translated or copied from R, C, Fortran, documentation, or upstream tests;
3. identify adapted material explicitly and stop for license review before it is
   accepted;
4. use project-authored synthetic cases and descriptions unless reuse has been
   approved; and
5. add a `Signed-off-by` line certifying the repository's contribution terms.

Oracle fixtures may record observable outputs and environment identities. They
must not embed upstream source, documentation prose, datasets without compatible
terms, or arbitrary executable R expressions. The oracle remains outside the
Python wheel and source distribution.

Suspected provenance contamination blocks the affected capability and external
distribution. Preserve the evidence, notify the maintainer privately, and use
normal incident review before rewriting or removing material.

Release artifact provenance is separate from contribution authorship. An
authorized tag build records the exact source revision, workflow identity,
workflow run, distribution-approval record, policy materials, and SHA-256 of
the wheel, source distribution, and CycloneDX SBOM in
`release-manifest.json`. The manifest, checksum index, package artifacts, and
SBOM each receive a keyless Sigstore bundle bound to the release workflow's
GitHub Actions OIDC identity. A local build or unsigned file is not an official
release artifact.
