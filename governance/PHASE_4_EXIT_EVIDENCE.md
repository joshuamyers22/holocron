# Phase 4 exit-gate evidence package

- Evidence date: 2026-09-18
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Technical evidence: passed
- Independent statistical review: pending
- Phase 4 exit gate: awaiting independent review

## Reproducible package

`make phase-4-evidence` validates the locked plan and produces
`.work/phase-4-evidence/phase-4-exit.json`. `make phase-4-evidence-clean` also
requires a clean source tree. The report records source hashes, revision,
platform, every threshold and result, and validates against
`schemas/phase-4-evidence-report.schema.json`.

The package contains:

- six Python-to-pinned-R cases: three exact-response ORM fits, one
  interval-censored ORM fit, one random-intercept fit, and one dual-scale
  `mix_re` fit;
- 232 seeded operating-characteristic replications for fixed, censored, and
  random-intercept ordinal recovery;
- declared adaptive-quadrature stabilization checks for the plain and
  dual-scale clustered fits;
- 16-, 32-, and 64-level timing, covariance-memory, conditioning, and
  probability-simplex measurements; and
- nine data-driven failure/stability cases, including one-sided exact-grid
  mappings and explicit rejections for unsupported or invalid structures.

The plan is immutable input at `governance/phase-4-evidence-plan.json`; failure
cases are declared in `reference/phase-4-edge-cases.json`. Ubuntu 24.04 x86_64
and macOS 15 arm64 workflow jobs run the identical package and retain reports
named `phase-4-platform-evidence-${runner.os}-${runner.arch}-${github.sha}`.

## Local result

The 2026-09-18 run passed 202 exact and 660 numeric oracle comparisons. The
fixed, censored, and clustered simulations completed all 120, 100, and 12
replications without fit failures and stayed inside every registered bias,
RMSE, and failure-rate limit. Both random-effect fixtures stabilized at 11
quadrature points. The 64-level case used 32,768 covariance bytes, had condition
number 3,296.7, and retained a maximum probability-simplex error of machine
precision.

## Published limits and parity exception

Exact-response Newton steps exploit bordered-tridiagonal structure, but the
public covariance remains quadratic in the number of parameters and arbitrary
interval censoring uses dense information. The public 1,024-parameter cap and
unsupported random structures remain unchanged.

The pinned `rms` snapshot applies an additional category shift to an interior
right-censored observation after its documented open-endpoint grid conversion.
Holocron retains the documented `(a, +Inf)` support and tests it explicitly;
one-sided fitting is therefore evidence-backed behavior but is not labeled
cross-language parity. Interval-censored fitting is the censored oracle-parity
claim. This is a parity exception requiring statistical review, not a loosened
tolerance.

## Gate disposition

The technical evidence package is complete and passing. The repository cannot
self-approve the required independent statistical review. Phase 4 closes only
after a qualified reviewer approves the scope above and the approval is added
to this record and the governance ledger. Capability promotion, consequential
use, license review, external verification, and external distribution remain
separate gates.
