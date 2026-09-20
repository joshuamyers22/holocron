# Phase 0 risk register

| Risk | Likelihood | Impact | Current control | Owner | Trigger / response |
|---|---|---|---|---|---|
| GPL or provenance boundary is invalid for intended distribution | Medium | Critical | Private repository, isolated oracle, contribution attestations, distribution gate | joshuamyers22 | Stop distribution and obtain qualified legal review |
| Plausible but statistically non-equivalent results | High | Critical | Layered parity cases, named tolerances, simulation requirement, experimental labels | Ron Mexico (Phase 3 scope) | Block capability promotion outside the reviewed scope |
| Hidden Hmisc or dependency behavior changes | Medium | High | Pinned Hmisc commit, dated R repository, full environment manifest | joshuamyers22 | Create a reference migration and rerun differential suite |
| Numerical instability or platform drift | High | High | Stable factorizations, condition/rank cases, required Linux/macOS tolerance-pilot matrix under ADR-009 | Ron Mexico (Phase 9 reviewed scope) | Quarantine affected case and investigate; do not widen tolerance silently |
| Formula or serialization code execution | Medium | Critical | Future allowlisted AST, no `eval`, non-executable serialization requirement | joshuamyers22 | Security incident process; disable entry point |
| Resource exhaustion from design expansion/resampling | Medium | High | Design limits plus resampling observation/split/total-index preflight bounds and explicit partial status | joshuamyers22 | Reject request with structured status |
| Project/package name conflict | High | Medium | `holocron-rms` distribution name; recheck before publishing | joshuamyers22 | Rename distribution before first public artifact |
| Single-maintainer review and continuity risk | High | High | Stable artifacts, CI, explicit vacant roles and promotion gate | joshuamyers22 | Recruit qualified reviewers before non-experimental claims |
| Multi-year scope exceeds resources | High | High | Tiered capability manifest and phase gates | joshuamyers22 | Narrow advertised scope and re-estimate after each phase |
