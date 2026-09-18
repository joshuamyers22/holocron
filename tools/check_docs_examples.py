"""Execute explicitly marked Python examples in the documentation."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
GETTING_STARTED = DOCS / "getting-started.md"
EXECUTABLE_BLOCK = re.compile(
    r"```python\n# holocron: execute\n(?P<source>.*?)```", re.DOTALL
)
GETTING_STARTED_OUTPUTS = {
    "binary_fit",
    "binary_probabilities",
    "bootstrap_estimate",
    "cluster_covariance",
    "coefficient_summary",
    "design",
    "distribution",
    "fit",
    "future_means",
    "group_contrast",
    "penalized_binary",
    "penalized_fit",
    "restored_binary",
    "restored_fit",
    "specification",
    "term_tests",
}


def main() -> None:
    executed = 0
    getting_started_blocks = 0
    for path in sorted(DOCS.rglob("*.md")):
        text = path.read_text()
        for index, match in enumerate(EXECUTABLE_BLOCK.finditer(text), start=1):
            source = match.group("source")
            code = compile(source, f"{path.relative_to(ROOT)}:example-{index}", "exec")
            namespace = {"__name__": "__holocron_docs_example__"}
            exec(code, namespace)  # noqa: S102
            executed += 1
            if path == GETTING_STARTED:
                getting_started_blocks += 1
                missing = sorted(GETTING_STARTED_OUTPUTS - namespace.keys())
                if missing:
                    raise ValueError(
                        "getting-started workflow outputs are incomplete: "
                        + ", ".join(missing)
                    )
    if executed == 0:
        raise ValueError("documentation contains no executable Python examples")
    if getting_started_blocks != 1:
        raise ValueError("getting-started must contain one coherent executable block")
    print(
        f"documentation examples verified: {executed} blocks; "
        "complete getting-started workflow passed"
    )


if __name__ == "__main__":
    main()
