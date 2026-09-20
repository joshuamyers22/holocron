"""Generate the installed migration catalog from reviewed repository metadata."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
COMPATIBILITY = ROOT / "compatibility/rms-8.2.0.yaml"
DEPRECATIONS = ROOT / "compatibility/deprecations.json"
OUTPUT = ROOT / "src/holocron/migration/_catalog.json"


def _object(path: Path) -> dict[str, object]:
    value: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain an object")
    return cast(dict[str, object], value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render() -> str:
    """Return the canonical installed catalog derived from owned metadata."""
    compatibility = _object(COMPATIBILITY)
    deprecations = _object(DEPRECATIONS)
    raw_capabilities = compatibility["capabilities"]
    if not isinstance(raw_capabilities, list):
        raise TypeError("compatibility capabilities must be an array")
    entries: list[dict[str, object]] = []
    for value in cast(list[object], raw_capabilities):
        if not isinstance(value, dict):
            raise TypeError("compatibility capability must be an object")
        capability = cast(dict[str, object], value)
        entries.append(
            {
                "identifier": capability["id"],
                "r_symbol": capability["r_symbol"],
                "kind": capability["kind"],
                "disposition": capability["status"],
                "python_entry_point": capability["python_entry_point"],
                "guidance": capability["known_differences"],
            }
        )
    document = {
        "schema_version": "holocron-migration-catalog/v1",
        "reference": compatibility["reference"],
        "source_sha256": {
            "compatibility_manifest": _sha256(COMPATIBILITY),
            "deprecation_policy": _sha256(DEPRECATIONS),
        },
        "entries": entries,
        "deprecation_policy": deprecations["policy"],
        "deprecation_notices": deprecations["notices"],
    }
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    rendered = render()
    if arguments.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != rendered:
            difference = "".join(
                difflib.unified_diff(
                    current.splitlines(keepends=True),
                    rendered.splitlines(keepends=True),
                    fromfile=str(OUTPUT),
                    tofile="generated",
                )
            )
            raise SystemExit(f"migration catalog is stale\n{difference}")
        print("migration catalog verified: 281 reviewed namespace entries")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
