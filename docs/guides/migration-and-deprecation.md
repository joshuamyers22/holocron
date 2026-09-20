# Migration planning and deprecation

Holocron ships the reviewed disposition of every export and registered S3
method in the pinned R `rms` 8.2-0 namespace. Use the catalog to assess a
workflow before translating code:

```python
# holocron: execute
from holocron.migration import plan_rms_migration

plan = plan_rms_migration(("ols", "Gls", "Newlabels"))
assert plan.disposition_counts == {
    "implemented": 0,
    "experimental": 1,
    "mapped": 1,
    "unsupported": 1,
}
assert not plan.ready
assert plan.matches[0].entry.python_entry_point == "holocron.models.fit_ols"
```

Pass an exact identifier such as `export:ols` when namespace identity matters.
A raw R symbol is convenient for inventory work and may produce both export and
S3-method matches. Unknown names remain in `unknown_symbols`; unsupported names
retain a null Python path and their reviewed stop guidance. `ready` is true only
when every query is known and every match has a reviewed Python path. It is not
a parity or production-readiness signal.

For a repository checkout, the reporting tool emits Markdown or canonical
JSON:

```sh
uv run --frozen python -m tools.plan_rms_migration \
  ols Gls Newlabels --format markdown
```

Add `--require-ready` when an automated inventory should fail for unknown or
unsupported capabilities. `MigrationPlan.to_json()` produces a strict,
versioned record bound to the exact installed catalog digest.

## Deprecation lifecycle

Mappings from R names are not deprecated Python aliases. Holocron currently has
no registered deprecated public API. Any future intentional removal or rename
of a documented Python name must first add a machine-readable notice to
`compatibility/deprecations.json` with:

- the old public path and a resolvable replacement;
- the release and date on which deprecation begins;
- a removal version at least two minor releases later;
- a removal date at least 90 days later;
- a visible `HolocronDeprecationWarning`, changelog entry, rationale, tests, and
  migration documentation.

Removal may occur only after both the release and date windows have elapsed.
Removed notices remain registered as history. Before 1.0, experimental APIs may
still change, but documented removals follow this policy. A security, legal, or
statistically invalid behavior may be disabled sooner only with an explicit
governance record and release note; it must fail clearly rather than silently
substitute different behavior.

Run `make migration-check` after changing the compatibility manifest,
deprecation registry, generated installed catalog, or public paths. The gate
validates schemas, source hashes, all 281 dispositions, replacement paths, and
warning windows.
