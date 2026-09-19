"""Structured result tables and safe dependency-free LaTeX output."""

from holocron.reporting.adapters import (
    anova_table,
    contrast_table,
    diagnostic_table,
    model_summary_table,
    resample_report_table,
    validation_table,
)
from holocron.reporting.latex import escape_latex, format_cell, render_latex
from holocron.reporting.specification import (
    TableColumn,
    TableMetadata,
    TableRow,
    TableSpec,
)

__all__ = [
    "TableColumn",
    "TableMetadata",
    "TableRow",
    "TableSpec",
    "anova_table",
    "contrast_table",
    "diagnostic_table",
    "escape_latex",
    "format_cell",
    "model_summary_table",
    "render_latex",
    "resample_report_table",
    "validation_table",
]
