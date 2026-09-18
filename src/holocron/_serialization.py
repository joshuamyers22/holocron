"""Internal helpers for Holocron's non-executable JSON interchange."""

from __future__ import annotations

import json
import re
from typing import NoReturn, cast

from holocron.exceptions import InputValidationError

MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class _DuplicateKeyError(ValueError):
    pass


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"non-standard numeric constant {value!r}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate object key {key!r}")
        result[key] = value
    return result


def canonical_json(document: object) -> str:
    """Encode a document with Holocron's canonical JSON settings."""
    try:
        encoded = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        encoded.encode("utf-8")
        return encoded
    except (TypeError, UnicodeEncodeError, ValueError) as error:
        raise InputValidationError("document is not canonical JSON data") from error


def parse_json_object(value: str, *, role: str) -> dict[str, object]:
    """Decode one bounded strict-JSON object without executing payload content."""
    raw_value = cast(object, value)
    if not isinstance(raw_value, str):
        raise InputValidationError(f"{role} JSON must be text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise InputValidationError(f"invalid {role} JSON") from error
    if len(encoded) > MAX_DOCUMENT_BYTES:
        raise InputValidationError(
            f"{role} JSON exceeds the {MAX_DOCUMENT_BYTES}-byte limit"
        )
    try:
        document: object = json.loads(
            value,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as error:
        raise InputValidationError(f"invalid {role} JSON") from error
    if not isinstance(document, dict):
        raise InputValidationError(f"{role} JSON must contain an object")
    return cast(dict[str, object], document)


def validate_sha256(value: object, *, role: str, nullable: bool = False) -> str | None:
    """Validate a lowercase SHA-256 identity."""
    if value is None and nullable:
        return None
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        suffix = " or null" if nullable else ""
        raise InputValidationError(f"{role} must be a lowercase SHA-256 digest{suffix}")
    return value


__all__: tuple[str, ...] = ()
