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
- allowlisted formulas with numeric, categorical, scored-ordered, spline, and
  restricted two-way interaction designs; and
- classical ordinary least squares, Gaussian/identity and binomial/logit
  generalized linear models, and binary logistic regression for a
  full-rank, caller-supplied design; and
- typed covariance, likelihood, residual, interval prediction, coefficient-
  summary, declared-term ANOVA, and single linear-contrast operations; and
- diagonal quadratic penalties for OLS and binary `lrm`, plus robust/clustered
  and iid bootstrap covariance for every currently supported estimator path.
- experimental cumulative-link ordinal regression, exact-grid mixed-censoring
  conversion, and single-cluster random-intercept models.

The core estimator envelope is also checked by seven seeded simulation
scenarios totaling 2,620 outer replications and a 16-case numerical edge corpus.
Phase 3 is complete for private experimental development following independent
statistical review of its alpha scope. The Phase 4 ordinal/censoring functional
surface and technical exit evidence are complete and passing; scoped independent
statistical review remains open. Capability promotion,
consequential use, and external distribution remain separately blocked.

The design, Phase 3, and ordinal APIs are checked against 43
cases from the pinned R `rms` 8.2-0 oracle. The remaining six frozen survival
cases are future baselines, not compatibility claims. Interval-censored and
clustered ordinal paths have registered oracle cases; one-sided censoring has a
documented parity exception.
See the generated [compatibility inventory](compatibility.md) for the exact
surface and evidence links.

## Start here

- [Install the private development checkout](installation.md).
- [Define predictor distributions and adjustment values](guides/data-distributions.md).
- [Build safe formulas and reconstructible numeric designs](guides/formulas-and-designs.md).
- [Run the complete Phase 3 getting-started workflow](getting-started.md).
- [Fit the supported generalized and logistic models](guides/generalized-models.md).
- [Fit ordinal and censored-response models](guides/ordinal-censoring.md).
- [Use the supported post-estimation operations](guides/post-estimation.md).
- [Use penalties and alternative covariance estimators](guides/regularization-and-covariance.md).
- [Inspect and reproduce simulation and numerical-edge evidence](guides/simulation-and-edge-evidence.md).
- [Understand the interpretation boundary](interpretation-and-limitations.md).
- [Compare Python and R concepts](guides/r-migration.md).
- [Contribute through the frozen development environment](development.md).

## Compatibility means evidence

Holocron does not claim drop-in or package-wide parity. Each claim must identify
a Python entry point, pinned R behavior, oracle cases, a named field-aware
tolerance policy, and known differences. `experimental` means the narrow
contract has parity evidence; it does not mean the broader R function is
implemented or production-ready.
