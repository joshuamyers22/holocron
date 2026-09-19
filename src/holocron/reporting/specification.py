"""Immutable backend-neutral structured-table specifications."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from numbers import Integral, Real
from typing import Literal, TypeAlias, cast

from holocron._serialization import canonical_json, parse_json_object
from holocron.exceptions import InputValidationError

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
TableValue: TypeAlias = None | int | float | str
TableKind: TypeAlias = Literal[
    "model-summary",
    "contrast",
    "anova",
    "validation",
    "resampling",
    "diagnostic",
    "custom",
]
ColumnKind: TypeAlias = Literal["text", "integer", "number", "probability", "p-value"]
Alignment: TypeAlias = Literal["left", "center", "right"]

SCHEMA_VERSION = "holocron-table-spec/v1"
MAX_COLUMNS = 64
MAX_ROWS = 10_000
MAX_CELLS = 100_000
MAX_NOTES = 64
MAX_METADATA = 128
MAX_TEXT = 4_096
MAX_TOTAL_TEXT = 4_000_000
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _identifier(value: object, *, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise InputValidationError(
            f"{name} must contain 1-128 letters, digits, dots, underscores, or hyphens"
        )
    return value


def _text(value: object, *, name: str, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or (not allow_empty and not value)
        or len(value) > MAX_TEXT
    ):
        lower = 0 if allow_empty else 1
        raise InputValidationError(f"{name} must contain {lower}-{MAX_TEXT} characters")
    return value


def _optional_text(value: object, *, name: str) -> str | None:
    return None if value is None else _text(value, name=name)


def _exact_mapping(value: object, keys: set[str], *, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InputValidationError(f"{name} has invalid fields")
    mapping = cast(dict[object, object], value)
    if set(mapping) != keys:
        raise InputValidationError(f"{name} has invalid fields")
    return cast(dict[str, object], mapping)


def _sequence(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise InputValidationError(f"{name} must be an array")
    return cast(list[object], value)


@dataclass(frozen=True, slots=True)
class TableColumn:
    """One typed table column and its backend-neutral display policy."""

    key: str
    label: str
    kind: ColumnKind
    alignment: Alignment
    digits: int = 3
    unit: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _identifier(self.key, name="column key"))
        object.__setattr__(self, "label", _text(self.label, name="column label"))
        if self.kind not in ("text", "integer", "number", "probability", "p-value"):
            raise InputValidationError("unsupported table column kind")
        if self.alignment not in ("left", "center", "right"):
            raise InputValidationError("unsupported table column alignment")
        raw_digits = cast(object, self.digits)
        if (
            isinstance(raw_digits, bool)
            or not isinstance(raw_digits, Integral)
            or not 0 <= int(raw_digits) <= 15
        ):
            raise InputValidationError("column digits must be an integer from 0 to 15")
        object.__setattr__(self, "digits", int(raw_digits))
        object.__setattr__(self, "unit", _optional_text(self.unit, name="column unit"))
        if self.kind in {"text", "integer"} and self.digits != 0:
            raise InputValidationError("text and integer columns require digits=0")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return this column as data-only JSON values."""
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "alignment": self.alignment,
            "digits": self.digits,
            "unit": self.unit,
        }


def _normalize_value(value: object, column: TableColumn) -> TableValue:
    if value is None:
        return None
    if column.kind == "text":
        return _text(value, name=f"{column.key} cell", allow_empty=True)
    if column.kind == "integer":
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise InputValidationError(f"{column.key} cells must be integers or null")
        return int(value)
    if isinstance(value, bool) or not isinstance(value, Real):
        raise InputValidationError(f"{column.key} cells must be numbers or null")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise InputValidationError(f"{column.key} cells must be finite or null")
    if column.kind in {"probability", "p-value"} and not 0.0 <= normalized <= 1.0:
        raise InputValidationError(f"{column.key} cells must be between zero and one")
    return normalized


@dataclass(frozen=True, slots=True)
class TableRow:
    """One identified row whose raw values align with the table columns."""

    row_id: str
    values: tuple[TableValue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "row_id", _identifier(self.row_id, name="row_id"))
        if not isinstance(cast(object, self.values), tuple):
            raise InputValidationError("row values must be a tuple")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return this row without converting raw values to display strings."""
        return {"row_id": self.row_id, "values": list(self.values)}


@dataclass(frozen=True, slots=True)
class TableMetadata:
    """One bounded string-valued table provenance or interpretation field."""

    key: str
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _identifier(self.key, name="metadata key"))
        object.__setattr__(self, "value", _text(self.value, name="metadata value"))


@dataclass(frozen=True, slots=True)
class TableSpec:
    """A bounded renderer-independent table with typed raw cell values."""

    table_id: str
    kind: TableKind
    title: str
    columns: tuple[TableColumn, ...]
    rows: tuple[TableRow, ...]
    caption: str | None = None
    notes: tuple[str, ...] = ()
    metadata: tuple[TableMetadata, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "table_id", _identifier(self.table_id, name="table_id")
        )
        if self.kind not in (
            "model-summary",
            "contrast",
            "anova",
            "validation",
            "resampling",
            "diagnostic",
            "custom",
        ):
            raise InputValidationError("unsupported table kind")
        object.__setattr__(self, "title", _text(self.title, name="table title"))
        object.__setattr__(
            self, "caption", _optional_text(self.caption, name="table caption")
        )
        if (
            not isinstance(cast(object, self.columns), tuple)
            or not 1 <= len(self.columns) <= MAX_COLUMNS
            or any(
                not isinstance(cast(object, column), TableColumn)
                for column in self.columns
            )
            or len({column.key for column in self.columns}) != len(self.columns)
        ):
            raise InputValidationError(
                f"columns must contain 1-{MAX_COLUMNS} unique columns"
            )
        if (
            not isinstance(cast(object, self.rows), tuple)
            or not 1 <= len(self.rows) <= MAX_ROWS
            or len(self.rows) * len(self.columns) > MAX_CELLS
            or any(not isinstance(cast(object, row), TableRow) for row in self.rows)
            or len({row.row_id for row in self.rows}) != len(self.rows)
        ):
            raise InputValidationError(
                "table rows are empty, duplicate, or exceed limits"
            )
        normalized_rows: list[TableRow] = []
        for row in self.rows:
            if len(row.values) != len(self.columns):
                raise InputValidationError("each row must contain one value per column")
            normalized_rows.append(
                TableRow(
                    row.row_id,
                    tuple(
                        _normalize_value(value, column)
                        for value, column in zip(row.values, self.columns, strict=True)
                    ),
                )
            )
        object.__setattr__(self, "rows", tuple(normalized_rows))
        if (
            not isinstance(cast(object, self.notes), tuple)
            or len(self.notes) > MAX_NOTES
        ):
            raise InputValidationError("table notes are invalid")
        notes = tuple(_text(note, name="table note") for note in self.notes)
        object.__setattr__(self, "notes", notes)
        if (
            not isinstance(cast(object, self.metadata), tuple)
            or len(self.metadata) > MAX_METADATA
            or any(
                not isinstance(cast(object, item), TableMetadata)
                for item in self.metadata
            )
            or len({item.key for item in self.metadata}) != len(self.metadata)
        ):
            raise InputValidationError("table metadata keys must be unique and bounded")
        text_size = len(self.title) + len(self.caption or "") + sum(map(len, notes))
        text_size += sum(
            len(column.label) + len(column.unit or "") for column in self.columns
        )
        text_size += sum(
            len(value)
            for row in self.rows
            for value in row.values
            if isinstance(value, str)
        )
        text_size += sum(len(item.value) for item in self.metadata)
        if text_size > MAX_TOTAL_TEXT:
            raise InputValidationError("table text exceeds the supported total size")

    def to_dict(self) -> dict[str, JsonValue]:
        """Return the strict table document while preserving raw numeric cells."""
        return {
            "schema_version": SCHEMA_VERSION,
            "table_id": self.table_id,
            "kind": self.kind,
            "title": self.title,
            "caption": self.caption,
            "columns": [column.to_dict() for column in self.columns],
            "rows": [row.to_dict() for row in self.rows],
            "notes": list(self.notes),
            "metadata": [
                {"key": item.key, "value": item.value} for item in self.metadata
            ],
        }

    def to_json(self) -> str:
        """Return canonical, non-executable JSON."""
        return canonical_json(self.to_dict())

    @property
    def fingerprint(self) -> str:
        """Return a stable SHA-256 identity for the canonical table document."""
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, document: object) -> TableSpec:
        """Restore one strict table document and reject unknown fields."""
        root = _exact_mapping(
            document,
            {
                "schema_version",
                "table_id",
                "kind",
                "title",
                "caption",
                "columns",
                "rows",
                "notes",
                "metadata",
            },
            name="table specification",
        )
        if root["schema_version"] != SCHEMA_VERSION:
            raise InputValidationError("unsupported table specification version")
        columns: list[TableColumn] = []
        for raw in _sequence(root["columns"], name="columns"):
            item = _exact_mapping(
                raw,
                {"key", "label", "kind", "alignment", "digits", "unit"},
                name="column",
            )
            columns.append(
                TableColumn(
                    key=cast(str, item["key"]),
                    label=cast(str, item["label"]),
                    kind=cast(ColumnKind, item["kind"]),
                    alignment=cast(Alignment, item["alignment"]),
                    digits=cast(int, item["digits"]),
                    unit=cast(str | None, item["unit"]),
                )
            )
        rows: list[TableRow] = []
        for raw in _sequence(root["rows"], name="rows"):
            item = _exact_mapping(raw, {"row_id", "values"}, name="row")
            values = _sequence(item["values"], name="row values")
            rows.append(
                TableRow(
                    cast(str, item["row_id"]),
                    tuple(cast(TableValue, value) for value in values),
                )
            )
        notes = tuple(
            cast(str, value) for value in _sequence(root["notes"], name="notes")
        )
        metadata: list[TableMetadata] = []
        for raw in _sequence(root["metadata"], name="metadata"):
            item = _exact_mapping(raw, {"key", "value"}, name="metadata item")
            metadata.append(
                TableMetadata(cast(str, item["key"]), cast(str, item["value"]))
            )
        return cls(
            table_id=cast(str, root["table_id"]),
            kind=cast(TableKind, root["kind"]),
            title=cast(str, root["title"]),
            caption=cast(str | None, root["caption"]),
            columns=tuple(columns),
            rows=tuple(rows),
            notes=notes,
            metadata=tuple(metadata),
        )

    @classmethod
    def from_json(cls, value: str) -> TableSpec:
        """Restore one bounded strict-JSON table specification."""
        return cls.from_dict(parse_json_object(value, role="table specification"))


__all__ = ["TableColumn", "TableMetadata", "TableRow", "TableSpec"]
