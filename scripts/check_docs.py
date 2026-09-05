#!/usr/bin/env python3
"""Validate that the MkDocs navigation resolves to real pages."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def nav_paths(items: list[object]) -> list[str]:
    """Flatten file targets from nested MkDocs navigation."""
    paths: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for value in item.values():
                if isinstance(value, str):
                    paths.append(value)
                elif isinstance(value, list):
                    paths.extend(nav_paths(value))
    return paths


def main() -> int:
    """Fail when a configured documentation page is absent."""
    config = yaml.safe_load(Path("mkdocs.yml").read_text(encoding="utf-8"))
    missing = [path for path in nav_paths(config["nav"]) if not (Path("docs") / path).is_file()]
    if missing:
        raise SystemExit("missing MkDocs pages: " + ", ".join(sorted(missing)))
    sys.stdout.write("documentation contract passed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
