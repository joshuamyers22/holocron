# Phase 8 retained-profile performance tuning

**Decision date:** 2026-09-19

**Scope:** fourth Phase 8 deliverable; representative fixed workloads

**Decision:** complete for private experimental development

## Performance contract

The locked plan in `governance/phase-8-performance-plan.json` covers five
deterministic workloads:

| Workload | Rows | Contract exercised |
| --- | ---: | --- |
| OLS repeated validation | 320 | fit, 10 exact K-fold refits, prediction, and validation indices |
| binary repeated validation | 240 | logistic fit, 10 exact K-fold refits, calibration, and discrimination |
| standard Cox risk sets | 400 | Efron fit and baseline estimation without delayed entry |
| delayed-entry Cox | 180 | general counting-process risk-set path |
| mixed-censoring PSM | 180 | exact, left-, right-, and interval-censored Weibull fitting |

Each run warms the workload, records the median of repeated uninstrumented
executions, measures peak Python-tracked memory, captures one raw `cProfile`
file, and writes its leading Holocron hotspots to a schema-valid JSON report.
Result-summary hashes detect nondeterministic workload behavior. Fixed
primitive-call and one-mebibyte peak-memory ceilings are acceptance gates for
the declared sizes.

Wall-clock measurements are deliberately diagnostic, not pass/fail criteria.
Absolute timing differs across CI hosts, BLAS implementations, power states,
and shared-runner load. Primitive-call and memory ceilings catch structural
regressions without pretending that unlike hosts provide a latency SLA.

## Profile-driven change

The standard 400-row Cox profile identified repeated construction of full
Boolean risk masks in `_cox_terms` as the dominant cost. The original local
profile used 132,481 function calls and 0.101 seconds under `cProfile`; the
first profile after tuning used 56,839 calls and 0.031 seconds. These timing
figures are local diagnostic observations, not portable acceptance limits.

For the ordinary zero-entry-time case, risk sets are nested. The tuned path
uses vectorized suffix aggregates under a fixed 2,048-element risk-moment
workspace limit. Larger row/predictor combinations switch to a descending
sweep with predictor-squared working memory. Both aggregate tied deaths once
per event time and preserve Breslow/Efron handling. Fits with delayed entry
continue through the general mask-based counting-process implementation.

A public-API regression test fits the same data through both paths by using
zero and the smallest positive entry times, then compares coefficients,
baseline cumulative hazards, and iteration counts. Existing survival oracle,
simulation, tie, weight, offset, stratum, and delayed-entry tests remain the
statistical guardrails.

## Retention and enforcement

`make phase-8-profiles` writes the JSON report and five raw `.prof` files under
`.work/phase-8-performance/`. The ordinary quality gate runs the suite. CI also
runs it on Ubuntu 24.04 and macOS 15 and retains each platform's report and raw
profiles for 30 days. `make phase-8-profiles-clean` rejects a dirty source tree
when producing review evidence.

Changing a workload, sample size, seed, call ceiling, or memory ceiling changes
the governed plan and requires review. A slower wall-clock observation calls
for comparison of retained profiles; it does not justify silently raising a
structural budget.

## Boundaries and consequence

This decision establishes regression protection for representative batch
workloads. It is not a latency or throughput SLA, a guarantee for maximum
accepted input sizes, a claim that every exported helper was profiled, or a
substitute for statistical parity. Native allocations made entirely below the
Python allocator may not be fully visible to `tracemalloc`; the fixed-shape
call ceiling and cross-platform runs complement that measurement.

The retained profiles pass their declared technical gates. This completes the
fourth Phase 8 deliverable. Migration tooling and deprecation policy were
completed by the subsequent decision. The accountable completion review in
`PHASE_8_COMPLETION.md` subsequently passed the private-development exit gate.
