# Phase 6 completion record

- Completion date: 2026-09-19
- Scope: private experimental development
- Accountable review authority: joshuamyers22
- Independent Phase 6 review: not claimed
- Review disposition: Phase 6 technical exit gate passed on 2026-09-19

| Required deliverable or gate | Status | Evidence |
|---|---|---|
| Common resampling engine with exact plans | Complete | `PHASE_6_RESAMPLING.md` |
| Model-specific validation and calibration | Complete | `PHASE_6_MODEL_VALIDATION.md` |
| Probability and survival validation metrics | Complete | `PHASE_6_VALIDATION_METRICS.md` |
| Optimism-corrected performance and calibration | Complete | `PHASE_6_OPTIMISM_CORRECTION.md` |
| Influence, robustness, VIF, penalty tracing, and selection | Complete | `PHASE_6_DIAGNOSTICS_SELECTION.md` |
| Failure-rate and partial-resample reporting | Complete | `PHASE_6_FAILURE_REPORTING.md` |
| Whole-procedure refitting | Passed | `tests/test_resampling.py`; `tests/test_model_validation.py` |
| Exact stochastic-plan replay | Passed | `tests/test_resampling.py`; `schemas/resample-plan.schema.json` |
| Complete, partial, failed, and strict failure policies | Passed | `tests/test_resampling.py`; `tests/test_optimism_correction.py`; `tests/test_resample_reporting.py` |
| Leakage and apparent-calibration warnings | Passed | `docs/guides/resampling.md`; `docs/interpretation-and-limitations.md`; `tools/check_docs_examples.py` |
| Focused Phase 6 suite | Passed: 38 tests | Phase 6 test modules listed below |
| Full repository and artifact gates | Passed: 156 tests plus wheel/sdist smoke | `make check`; `make build` |

## Exit-gate review

The Phase 6 exit gate passes for private experimental development.

Whole-procedure execution is demonstrated by a callback invocation for every
declared split and by distinct fresh OLS/binary model fits inside the
model-specific validation and calibration paths. The engine passes indices,
not a fitted model, so caller-owned transformations, selection, fitting, and
assessment can be repeated inside the callback. Convenience APIs explicitly
retain their narrower fixed-realized-design boundary.

The stochastic-equivalence criterion is satisfied within the owned exact-plan
contract: seeded constructors fully materialize every split, repeated
construction produces the same plan and fingerprint, strict JSON reconstruction
preserves that identity, and replay uses the stored schedule rather than a later
random-number implementation. This is not a claim that NumPy and R seeds
generate identical streams or that deferred R `predab.resample`, `validate.*`,
or `calibrate.*` methods have parity.

Failure-policy tests exercise strict first-failure rejection and retained
complete, partial, and all-failed executions. Optimism correction rejects
partial execution unless explicitly allowed. Typed reports preserve exact
outcome IDs, grouped bounded failure reasons, failure rates, metric-specific
coverage, and the aggregation disposition; partial execution is never relabeled
complete and all-failed execution is never aggregatable.

Executable documentation states that every learned step belongs inside the
resample callback, that model-specific convenience APIs receive an already
realized fixed design, that apparent and corrected estimates differ, and that
allowing partial aggregation does not make failures ignorable. The focused
suite runs 38 tests across resampling, model validation/calibration, probability
and survival metrics, optimism correction, diagnostics/selection, and failure
reporting. The full gate passes 156 tests, static analysis, strict documentation,
all retained Phase 1–5 evidence suites, and independent wheel/sdist installation
smoke tests. CI now repeats the focused Phase 6 suite on the accepted Ubuntu and
macOS platform matrix.

## Decision and boundaries

Phase 6 is complete for private experimental development. Phase 7 is the next
planned phase.

This decision is an accountable-maintainer technical review under the current
governance contract; it is not represented as independent statistical or
numerical approval. It does not promote any capability beyond `experimental`,
authorize consequential use, authorize external distribution, or advance the
deferred compatibility dispositions for R validation, calibration, diagnostic,
or selection methods. Independent verification and legal/license review remain
mandatory for their separate promotion and distribution gates.
