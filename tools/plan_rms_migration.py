"""Assess R rms symbols against Holocron's reviewed migration catalog."""

from __future__ import annotations

import argparse
from pathlib import Path

from holocron.migration import MigrationPlan, plan_rms_migration


def render_markdown(plan: MigrationPlan) -> str:
    """Render a compact human-readable migration assessment."""
    lines = [
        f"# rms {plan.reference_version} migration assessment",
        "",
        "| Query | R capability | Disposition | Python path | Guidance |",
        "| --- | --- | --- | --- | --- |",
    ]
    for match in plan.matches:
        entry = match.entry
        guidance = entry.guidance.replace("|", "\\|").replace("\n", " ")
        path = entry.python_entry_point or "— stop boundary —"
        lines.append(
            f"| `{match.query}` | `{entry.identifier}` | {entry.disposition} | "
            f"`{path}` | {guidance} |"
        )
    for symbol in plan.unknown_symbols:
        lines.append(f"| `{symbol}` | unknown | unknown | — | No catalog match. |")
    lines.extend(
        [
            "",
            f"Ready for direct Python migration: **{'yes' if plan.ready else 'no'}**",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+", help="R symbols or exact capability IDs")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="exit unsuccessfully for unknown or unsupported capabilities",
    )
    arguments = parser.parse_args()
    plan = plan_rms_migration(arguments.symbols)
    rendered = (
        plan.to_json() + "\n" if arguments.format == "json" else render_markdown(plan)
    )
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    return 2 if arguments.require_ready and not plan.ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
