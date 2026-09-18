# Holocron

Holocron is an independent Python implementation of Frank Harrell's R `rms`
package. It is building a Python-native Regression Modeling Strategies workflow
with explicit design metadata, statistical evidence, and capability-level parity
claims.

!!! warning "Experimental and incomplete"
    Do not use Holocron for consequential analysis, inference, prediction, or
    clinical decisions. No external package has been published.

The current experimental surface supports only:

- immutable predictor-distribution metadata;
- explicit-knot restricted cubic spline design matrices; and
- classical ordinary least squares for a full-rank, caller-supplied design.

These APIs are checked against 16 cases from the pinned R `rms` 8.2-0 oracle.
The remaining frozen oracle cases are future baselines, not compatibility claims.
See the generated [compatibility inventory](compatibility.md) for the exact
surface and evidence links.

## Start here

- [Install the private development checkout](installation.md).
- [Define predictor distributions and adjustment values](guides/data-distributions.md).
- [Run the first spline-and-OLS model](getting-started.md).
- [Understand the interpretation boundary](interpretation-and-limitations.md).
- [Compare Python and R concepts](guides/r-migration.md).
- [Contribute through the frozen development environment](development.md).

## Compatibility means evidence

Holocron does not claim drop-in or package-wide parity. Each claim must identify
a Python entry point, pinned R behavior, oracle cases, a named field-aware
tolerance policy, and known differences. `experimental` means the narrow
contract has parity evidence; it does not mean the broader R function is
implemented or production-ready.
