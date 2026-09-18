"""Execute explicitly marked Python examples in the documentation."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
EXECUTABLE_BLOCK = re.compile(
    r"```python\n# holocron: execute\n(?P<source>.*?)```", re.DOTALL
)


def main() -> None:
    executed = 0
    for path in sorted(DOCS.rglob("*.md")):
        text = path.read_text()
        for index, match in enumerate(EXECUTABLE_BLOCK.finditer(text), start=1):
            source = match.group("source")
            code = compile(source, f"{path.relative_to(ROOT)}:example-{index}", "exec")
            namespace = {"__name__": "__holocron_docs_example__"}
            exec(code, namespace)  # noqa: S102
            executed += 1
    if executed == 0:
        raise ValueError("documentation contains no executable Python examples")
    print(f"documentation examples verified: {executed} blocks")


if __name__ == "__main__":
    main()
