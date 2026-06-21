"""Loader for docs_claim_candidates scanner.

Handles file discovery and inventory reading.
"""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.docs_claim_candidates_contract import (
    DOCS_DIR,
    INVENTORY_CSV,
    REPO_ROOT,
)


def get_inventory_cache() -> dict[str, dict[str, str]]:
    """Read inventory CSV and return a cache keyed by doc_path."""
    cache: dict[str, dict[str, str]] = {}
    if not INVENTORY_CSV.exists():
        return cache
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                doc_path = row.get("doc_path", "").strip()
                if doc_path:
                    cache[doc_path] = row
    except Exception:
        pass
    return cache


def get_doc_class(doc_path: str, cache: dict[str, dict[str, str]] | None = None) -> str:
    """Get doc_class from inventory."""
    if cache is not None:
        if doc_path in cache:
            return cache[doc_path].get("doc_class", "").strip()
        return "unknown"
    if not INVENTORY_CSV.exists():
        return "unknown"
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("doc_path", "").strip() == doc_path:
                    return row.get("doc_class", "").strip()
        return "unknown"
    except Exception:
        return "unknown"


def get_truth_status(doc_path: str, cache: dict[str, dict[str, str]] | None = None) -> str:
    """Get truth_status from inventory."""
    if cache is not None:
        if doc_path in cache:
            return cache[doc_path].get("truth_status", "").strip()
        return "unknown"
    if not INVENTORY_CSV.exists():
        return "unknown"
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("doc_path", "").strip() == doc_path:
                    return row.get("truth_status", "").strip()
        return "unknown"
    except Exception:
        return "unknown"


def get_claim_trace_required(doc_path: str, cache: dict[str, dict[str, str]] | None = None) -> bool:
    """Get claim_trace_required from inventory."""
    if cache is not None:
        if doc_path in cache:
            return cache[doc_path].get("claim_trace_required", "").strip().lower() == "true"
        return False
    if not INVENTORY_CSV.exists():
        return False
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("doc_path", "").strip() == doc_path:
                    return row.get("claim_trace_required", "").strip().lower() == "true"
        return False
    except Exception:
        return False


def get_scope_files() -> list[Path]:
    """Get list of files in scanner scope."""
    files: list[Path] = []
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        files.append(readme)
    if DOCS_DIR.exists():
        for md_file in DOCS_DIR.rglob("*.md"):
            files.append(md_file)
    return sorted(files)
