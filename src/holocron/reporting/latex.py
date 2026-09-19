"""Safe deterministic LaTeX rendering for structured table specifications."""

from __future__ import annotations

from typing import cast

from holocron.exceptions import InputValidationError
from holocron.reporting.specification import (
    TableColumn,
    TableSpec,
    TableValue,
    _normalize_value,  # pyright: ignore[reportPrivateUsage]
)

_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "%": r"\%",
    "#": r"\#",
    "_": r"\_",
    "^": r"\textasciicircum{}",
    "~": r"\textasciitilde{}",
    "\n": " ",
    "\r": " ",
    "\t": " ",
}


def escape_latex(value: str) -> str:
    """Escape caller-controlled text for ordinary LaTeX text contexts."""
    if not isinstance(cast(object, value), str):
        raise InputValidationError("LaTeX text must be a string")
    return "".join(_LATEX_ESCAPES.get(character, character) for character in value)


def _format_number(value: float, *, digits: int) -> str:
    rounded = round(value, digits)
    if rounded == 0.0:
        rounded = 0.0
    return f"{rounded:.{digits}f}"


def format_cell(value: TableValue, column: TableColumn) -> str:
    """Format one raw cell according to its declared column policy."""
    if not isinstance(cast(object, column), TableColumn):
        raise InputValidationError("column must be a TableColumn")
    value = _normalize_value(value, column)
    if value is None:
        return r"\textemdash{}"
    if column.kind == "text":
        return escape_latex(cast(str, value))
    if column.kind == "integer":
        return str(cast(int, value))
    number = cast(float, value)
    if column.kind == "p-value" and number < 10.0 ** (-column.digits):
        return f"$<{10.0 ** (-column.digits):.{column.digits}f}$"
    return _format_number(number, digits=column.digits)


def _tabular(spec: TableSpec) -> list[str]:
    alignments = {"left": "l", "center": "c", "right": "r"}
    layout = "".join(alignments[column.alignment] for column in spec.columns)
    labels = [
        escape_latex(
            column.label if column.unit is None else f"{column.label} ({column.unit})"
        )
        for column in spec.columns
    ]
    lines = [f"\\begin{{tabular}}{{{layout}}}", r"\hline"]
    lines.append(" & ".join(labels) + r" \\")
    lines.append(r"\hline")
    for row in spec.rows:
        lines.append(
            " & ".join(
                format_cell(value, column)
                for value, column in zip(row.values, spec.columns, strict=True)
            )
            + r" \\"
        )
    lines.extend([r"\hline", r"\end{tabular}"])
    return lines


def render_latex(spec: TableSpec, *, include_table_environment: bool = True) -> str:
    """Render a dependency-free LaTeX fragment from only a :class:`TableSpec`.

    Caller-controlled text is always escaped. When ``include_table_environment``
    is false, the result is only the ``tabular`` environment for embedding in a
    caller-owned float or document.
    """
    if not isinstance(cast(object, spec), TableSpec):
        raise InputValidationError("spec must be a TableSpec")
    if not isinstance(cast(object, include_table_environment), bool):
        raise InputValidationError("include_table_environment must be boolean")
    tabular = _tabular(spec)
    if not include_table_environment:
        return "\n".join(tabular) + "\n"
    lines = [r"\begin{table}[htbp]", r"\centering"]
    lines.append(f"\\caption{{{escape_latex(spec.title)}}}")
    lines.append(f"\\label{{tab:{spec.table_id}}}")
    lines.extend(tabular)
    if spec.caption is not None:
        lines.append(r"\par\smallskip")
        lines.append(f"\\small {escape_latex(spec.caption)}")
    if spec.notes:
        lines.append(r"\par\smallskip")
        prefix = r"\textit{Note:} " if len(spec.notes) == 1 else r"\textit{Notes:} "
        lines.append(
            r"\small " + prefix + r" \quad ".join(map(escape_latex, spec.notes))
        )
    lines.append(r"\end{table}")
    return "\n".join(lines) + "\n"


__all__ = ["escape_latex", "format_cell", "render_latex"]
