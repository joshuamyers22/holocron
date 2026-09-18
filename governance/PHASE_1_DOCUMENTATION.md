# Phase 1 Documentation Acceptance Record

**Status:** Accepted for private experimental development

**Accepted:** 2026-09-17

**Owner:** joshuamyers22

## Scope

This record accepts the initial MkDocs site and generated compatibility page as
the Phase 1 documentation deliverable. It does not approve external publication
or promote an experimental statistical capability.

## Acceptance evidence

- `mkdocs.yml` defines a complete navigation tree and strict validation.
- `tools/generate_docs.py` derives public API pages from module exports and the
  compatibility page from the authoritative 281-entry manifest.
- `tools/generate_docs.py --check` fails when a committed generated page differs
  from its source.
- `tools/check_docs_examples.py` executes explicitly marked examples without
  network access.
- `mkdocs build --strict --clean` treats local link, anchor, navigation, and build
  warnings as failures.
- `make check` includes every documentation check above.
- The site identifies the two experimental capabilities, separates 13 future
  oracle baselines from parity claims, and states the distribution and numerical
  boundaries.
- Package build configuration continues to exclude documentation from runtime
  wheel and source-distribution contents.

## Regeneration contract

Changes to public exports or `compatibility/rms-8.2.0.yaml` must run
`make docs-generate` and commit the result. Generated files are identified in
their first line. Authored examples remain deterministic, synthetic, and offline.

## Subsequent disposition

The separate end-to-end slice subsequently passed. Its evidence and remaining
boundaries are recorded in `governance/PHASE_1_COMPLETION.md`.
