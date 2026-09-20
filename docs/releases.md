# Releases

Holocron is at version 0.1.0 for private development. No public release,
release candidate, external beta artifact, or package-index publication is
authorized.

## Phase 9 candidate program

The locked candidate plan targets `1.0.0rcN`, but candidate creation is blocked
until ADR-010 defines the exact stable core. A valid series requires at least
two distinct candidates. Every candidate must retain a clean source revision,
wheel and source-distribution SHA-256 values, and passing `make check`,
`make audit`, and clean artifact-installation evidence.

The clean artifact gate is a four-cell installability matrix: Ubuntu 24.04 and
macOS 15, each on CPython 3.11 and 3.12. Every cell retains wheel and sdist
bytes plus a plan- and revision-bound JSON report for 90 days. Run
`make phase-9-build-matrix-check` to check its repository topology, then run
`make phase-9-build-matrix-evidence EVIDENCE_DIRECTORY=/path/to/reports` after
downloading all four reports from one CI revision. A partial or mixed-revision
set cannot qualify a candidate. This does not expand ADR-009 numerical parity.

External distribution has a separate fail-closed prerequisite. A qualified
license/provenance reviewer must approve each candidate's exact source commit,
license, provenance process, package name, and notices in writing. The
tag-triggered workflow also requires the repository variable
`EXTERNAL_DISTRIBUTION_APPROVED` to equal `true`, requires
`EXTERNAL_DISTRIBUTION_APPROVED_SHA` to equal the tag commit, and requires a
nonempty `EXTERNAL_DISTRIBUTION_APPROVAL_RECORD`. Neither CI nor a local build
satisfies this authorization.

Run the structural program check with:

```sh
make phase-9-rc-check
```

The completion gate intentionally fails until real candidate and external-beta
evidence meets every criterion:

```sh
make phase-9-rc-exit-gate
```

## Candidate sequence

For each candidate:

1. Resolve ADR-010 and obtain written distribution approval for the exact clean
   candidate commit.
2. Set the PEP 440 package version to the next `1.0.0rcN`, run the complete
   checks, audit dependencies, and build/install-test both artifacts from a
   clean checkout.
3. Record the immutable tag, commit, artifact hashes, checks, and approval in
   `governance/phase-9-beta-program.json`.
4. Only after authorization, publish the prerelease artifact to the approved
   private beta channel. Do not publish it to PyPI or make it public merely
   because the release workflow can build it.
5. Collect structured feedback, resolve findings, and supersede the candidate
   with a new commit and ordinal when behavior or documentation changes.

The final candidate may be accepted only after all earlier candidates are
marked superseded and every completion criterion passes.

## External beta feedback

At least three independent external reviewers must submit retained feedback.
Together their work must cover design/core modeling, survival, validation and
calibration, graphics/reporting, and migration. Every reviewer attests
independence and retention consent; records use pseudonymous reviewer IDs and
must not contain names, email addresses, organizations, datasets, or other
personal or restricted information.

Feedback records identify the exact candidate, installation source, Python and
operating-system environment, exercised workflows, bounded ratings, outcome,
summary, and findings. Every blocker or high-severity finding must be resolved.
The accepted final candidate must itself receive external feedback. Synthetic
test fixtures demonstrate the validator only and never count as beta evidence.

The authoritative contracts are
[`phase-9-release-candidate-plan.json`](https://github.com/joshuamyers22/holocron/blob/main/governance/phase-9-release-candidate-plan.json),
[`phase-9-beta-program.json`](https://github.com/joshuamyers22/holocron/blob/main/governance/phase-9-beta-program.json),
and the
[`Phase 9 program decision`](https://github.com/joshuamyers22/holocron/blob/main/governance/PHASE_9_RELEASE_CANDIDATES.md).

Changes planned for the next version remain recorded in the
[changelog](https://github.com/joshuamyers22/holocron/blob/main/CHANGELOG.md).
