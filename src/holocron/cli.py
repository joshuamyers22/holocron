"""Thin command-line delivery adapter."""

from __future__ import annotations

import argparse
from pathlib import Path

from .ingest import load_csv


def main() -> int:
    parser = argparse.ArgumentParser(prog="holocron")
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    dataset = load_csv(args.input)
    print(f"rows={len(dataset.observations)} sha256={dataset.source_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
