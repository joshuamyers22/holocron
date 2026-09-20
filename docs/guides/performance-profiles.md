# Performance profiles

Holocron uses fixed, deterministic batch workloads to make performance changes
reviewable. Run the suite with:

```sh
make phase-8-profiles
```

The command writes a schema-valid summary and one raw `cProfile` file per
workload to `.work/phase-8-performance/`. Open a raw profile with Python's
standard tools, for example:

```sh
uv run --frozen python -m pstats .work/phase-8-performance/cox-standard-risk-sets.prof
```

The report includes median wall time, Python-tracked peak memory, primitive
call count, leading Holocron functions, and a deterministic result-summary
hash. Wall time is diagnostic because machines and BLAS libraries differ. The
portable gates are fixed-workload call ceilings and memory ceilings.

The current suite covers repeated OLS and binary-logistic validation, ordinary
and delayed-entry Cox fitting, and mixed-censoring parametric survival fitting.
Its standard Cox workload drove bounded vectorized suffix aggregates plus a
memory-bounded nested-risk-set sweep for the common case without delayed entry.
The general delayed-entry implementation remains a separate retained workload.

Treat a failed ceiling as a regression to investigate. Compare raw profiles,
confirm that the workload result is unchanged, and review any plan or budget
change explicitly. Do not raise a ceiling solely because a wall-clock run was
slow. These profiles protect representative development workloads; they do not
promise service latency, full-input-scale memory use, or statistical parity.
