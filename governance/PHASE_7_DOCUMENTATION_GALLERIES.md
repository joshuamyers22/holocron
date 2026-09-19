# Phase 7 documentation-gallery acceptance record

- Acceptance date: 2026-09-19
- Scope: private experimental development
- Accountable owner: joshuamyers22
- Phase 7 deliverable: task-oriented documentation and tested galleries
- Disposition: complete within the declared executable-gallery envelope

## Accepted contract

Five task-oriented galleries now connect supported statistical results to the
Phase 7 presentation surfaces:

1. adjusted effects, contrasts, ANOVA, SVG, and model-summary LaTeX;
2. exact-plan validation, optimism-corrected calibration, SVG, metric tables,
   and resample-coverage reporting;
3. stratified Kaplan–Meier curves, fixed-horizon survival validation,
   calibration, SVG, and LaTeX;
4. influence, clustered robustness, VIF, and declared penalty-path diagnostics;
5. additive nomogram geometry/SVG and identity-bound coefficient reporting.

Every page states a goal, supplies one coherent executable workflow, explains
interpretation, and names its boundaries. Examples are deterministic, offline,
synthetic, and make no filesystem or network writes.

`governance/phase-7-gallery-manifest.json` is the complete machine-readable
inventory. It binds each task ID to one page and the model, result, plot, SVG,
table, or LaTeX objects that the workflow must produce. The documentation gate
rejects missing/extra gallery pages, duplicate IDs or paths, unsafe paths,
unknown manifest fields, absent navigation entries, missing required sections,
more or fewer than one executable block per gallery, or absent named outputs.

## Evidence

`tools/check_docs_examples.py` executes the five galleries alongside the full
offline documentation corpus. The accepted focused run executes 39 blocks and
confirms the complete getting-started workflow plus all five registered gallery
contracts. Each gallery additionally asserts semantic source/result identities,
renderer accessibility markers, and expected table/LaTeX content. Strict
MkDocs validates navigation and links; Ruff and Pyright validate the checker.

## Boundaries and next step

The galleries demonstrate API composition and interpretation boundaries; they
do not add statistical parity, validate an applied analysis, or establish
publication quality. Executing generated SVG strings is not browser or
assistive-technology certification. These pages deliberately do not freeze
pixel baselines or visual styling, because those controls belong to the final
Phase 7 deliverable.

The subsequent accessibility and visual-regression deliverable is now recorded
in `governance/PHASE_7_SVG_ASSURANCE.md`. The Phase 7 completion review and exit
gate remain open.
