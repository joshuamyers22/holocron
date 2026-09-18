# Contributing

Keep changes bounded, test changed behavior, and run `make check`. Pull requests
must state outcome, risk, verification evidence, and rollback considerations.

Statistical implementation changes must also identify the mathematical/public
specification, R documentation and source files consulted, oracle case IDs, and
the applicable named profile from `reference/tolerances.json`. New or widened
approximate rules require numerical justification and review; unlisted fields
remain exact. Do not mechanically translate or copy `rms`
or Hmisc source, prose, or tests. Stop for license review before adapting any
upstream material.

Every commit contributed for inclusion must include a `Signed-off-by` line. By
signing off, the contributor affirms that they have the right to submit the
work under the repository's current terms and that the declared provenance is
complete. See `governance/PROVENANCE.md`.

Changes to Phase 3 estimators, inference, penalties, covariance, or numerical
failure behavior must also run `make phase-3-evidence`. Changes to its plan,
thresholds, corpus, or report schemas require an updated acceptance record and
a clean `make phase-3-evidence-clean` report from the committed implementation.
