"""Loader for docs_inventory verifier.

Handles CSV reading and scope file discovery.
"""

from __future__ import annotations

import csv
from pathlib import Path

from docs_inventory_contract import REPO_ROOT, INVENTORY_CSV


def read_inventory() -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the inventory CSV. Returns (rows, error_msg)."""
    if not INVENTORY_CSV.exists():
        return [], f"Inventory file not found: {INVENTORY_CSV}"

    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading inventory: {e}"


def get_scope_files(repo_root: Path | None = None) -> set[Path]:
    """Get all files in scope for inventory check."""
    root = repo_root if repo_root is not None else REPO_ROOT
    files: set[Path] = set()

    # Root README.md
    readme = root / "README.md"
    if readme.exists():
        files.add(readme)

    # docs/**/*.md
    docs_dir = root / "docs"
    if docs_dir.exists():
        for md_file in docs_dir.rglob("*.md"):
            files.add(md_file)

    return files
