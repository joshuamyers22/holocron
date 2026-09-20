# Phase 8 migration tooling and deprecation policy

**Decision date:** 2026-09-19

**Scope:** fifth Phase 8 deliverable; reviewed namespace migration and Python API retirement

**Decision:** complete for private experimental development

## Migration contract

The installed `holocron.migration` namespace exposes immutable entries for all
281 reviewed R `rms` 8.2-0 exports and S3 methods. The generated catalog is
derived from `compatibility/rms-8.2.0.yaml`, embeds source digests, and is
included in wheel and source artifacts.

`lookup_rms_capability` requires an exact `export:` or `s3_method:` identifier.
`plan_rms_migration` also accepts raw R symbols, preserves every match when a
symbol appears in both namespace inventories, and records unknown names
explicitly. Its versioned `MigrationPlan` retains:

- the pinned package version and source commit;
- the exact installed catalog SHA-256;
- caller-requested names in order;
- matched disposition, Python path, and reviewed guidance;
- unknown names, disposition counts, and a conservative readiness flag.

Experimental and mapped entries can be migration paths only within their
documented boundaries. Unsupported entries have no Python path. Readiness means
only that all requested names have reviewed paths; it does not mean R parity,
statistical approval, or production readiness. The repository reporting tool
emits canonical JSON or a Markdown assessment and can fail closed with
`--require-ready`.

## Deprecation contract

The authoritative registry is `compatibility/deprecations.json`. There are no
deprecated public Holocron APIs as of this decision. R-to-Python migration
mappings are not aliases and are not entered as deprecations.

An ordinary documented Python API removal or rename requires all of the
following before removal:

1. a unique registry notice naming the old API and a resolvable replacement;
2. a visible `HolocronDeprecationWarning` beginning in the declared release;
3. at least two intervening minor releases and at least 90 elapsed days;
4. changelog, migration documentation, and tests in the introducing change;
5. retention of the notice with `removed` status after removal.

Both the version and time windows must pass. The gate verifies versions, dates,
public paths, registry uniqueness, package-version alignment, generated-catalog
freshness, source hashes, and exact disposition counts. A security, legal, or
statistically invalid behavior may be disabled earlier only through an explicit
reviewed governance decision and release note. Such an exception must fail
clearly and cannot silently substitute a different statistical operation.

## Evidence and enforcement

Focused tests cover exact lookup, raw-symbol ambiguity, unsupported and unknown
boundaries, readiness, strict round trips, schema validation, tamper rejection,
catalog counts, policy values, and Markdown reporting. Artifact smoke tests
load the packaged catalog and reconstruct a serialized migration plan outside
the checkout. `make migration-check` is part of the ordinary gate.

This decision adds migration assessment and Python API lifecycle governance; it
does not translate R code, load R objects, execute R, implement unsupported
capabilities, or promote any compatibility disposition. All five Phase 8
deliverables are now implemented. The accountable completion review in
`PHASE_8_COMPLETION.md` subsequently passed the private-development exit gate.
