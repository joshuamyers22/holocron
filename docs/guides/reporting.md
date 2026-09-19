# Structured tables and LaTeX output

Holocron reporting separates statistical values from presentation. A
`TableSpec` stores typed raw cells, column semantics, notes, and provenance.
Renderers consume that contract; they do not inspect a fitted model or
recompute statistics.

## Adapt a model result

Typed adapters cover supported model summaries, contrasts, ANOVA results,
probability/survival/optimism validation, resample reports, and diagnostics.

```python
# holocron: execute
from holocron.design import DesignSpec
from holocron.models import fit_ols, summarize
from holocron.reporting import TableSpec, model_summary_table, render_latex

x = tuple(float(value) for value in range(8))
y = tuple(1.0 + 0.5 * value + 0.1 * ((index % 3) - 1) for index, value in enumerate(x))
design = DesignSpec.from_formula("y ~ x").transform({"x": x})
model = fit_ols(y, design)

table = model_summary_table(summarize(model))
restored = TableSpec.from_json(table.to_json())
latex = render_latex(restored)

assert restored == table
assert isinstance(table.rows[1].values[1], float)
assert "\\begin{table}" in latex
assert "Estimate" in latex
```

Numeric values remain numbers in canonical `holocron-table-spec/v1` JSON.
Formatting is declared by each column: ordinary numbers use fixed decimal
digits, probability columns enforce the unit interval, p-value columns show a
strict threshold below the smallest displayed positive value, and null cells
render as an em dash. The original p-value is still present in the table
source.

## Build a custom table

```python
# holocron: execute
from holocron.reporting import TableColumn, TableRow, TableSpec, render_latex

table = TableSpec(
    table_id="custom-results",
    kind="custom",
    title="Custom results",
    columns=(
        TableColumn("term", "Term", "text", "left", 0),
        TableColumn("estimate", "Estimate", "number", "right", 2),
        TableColumn("p", "p", "p-value", "right", 3),
    ),
    rows=(
        TableRow("treatment", ("Treatment_A", 0.42, 0.0002)),
        TableRow("missing", ("Unavailable", None, None)),
    ),
)

fragment = render_latex(table, include_table_environment=False)
assert "Treatment\\_A" in fragment
assert "$<0.001$" in fragment
assert "\\textemdash{}" in fragment
```

`render_latex` emits only standard `table` and `tabular` markup and requires no
LaTeX package. All titles, labels, cells, captions, and notes are escaped; there
is no raw-LaTeX bypass. Use tabular-only mode when another document owns the
float and caption.

## Boundaries

Tables are bounded to 64 columns, 10,000 rows, 100,000 cells, and four million
text characters. Constructors reject duplicate identities, non-finite numbers,
wrong cell types, out-of-range probability/p-value cells, unknown JSON fields,
and duplicate JSON keys.

This backend is an owned experimental output format. It does not claim layout
or macro parity with R `latex.*` methods, compile LaTeX, write files, provide
multi-level headers, paginate long tables, or accept executable markup.
