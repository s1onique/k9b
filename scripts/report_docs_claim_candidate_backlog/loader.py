"""Data loading for documentation claim candidate backlog reporter."""

from __future__ import annotations

import csv
from pathlib import Path


def get_repo_root() -> Path:
    """Get repository root path.
    
    From scripts/report_docs_claim_candidate_backlog/loader.py:
    - __file__ = scripts/report_docs_claim_candidate_backlog/loader.py
    - .parent = scripts/report_docs_claim_candidate_backlog
    - .parent = scripts
    - .parent = repo root
    """
    return Path(__file__).resolve().parents[2]


def get_disposition_shard_paths() -> list[Path]:
    """Get all disposition shard file paths."""
    claims_dir = get_repo_root() / "docs" / "claims"
    return sorted(claims_dir.glob("docs_claim_dispositions-shard-*.csv"))


def get_candidate_shard_paths() -> list[Path]:
    """Get all candidate shard file paths."""
    claims_dir = get_repo_root() / "docs" / "claims"
    return sorted(claims_dir.glob("generated_claim_candidates-shard-*.csv"))


def read_dispositions() -> tuple[list[dict[str, str]], str | None]:
    """Read all disposition shards. Returns (rows, error)."""
    shard_paths = get_disposition_shard_paths()
    if not shard_paths:
        return [], "No disposition shards found"

    all_rows: list[dict[str, str]] = []
    for shard_path in shard_paths:
        try:
            with open(shard_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                all_rows.extend(list(reader))
        except Exception as e:
            return [], f"Error reading {shard_path}: {e}"

    return all_rows, None


def read_candidates() -> tuple[list[dict[str, str]], str | None]:
    """Read all candidate shards. Returns (rows, error)."""
    shard_paths = get_candidate_shard_paths()
    if not shard_paths:
        return [], "No candidate shards found"

    all_rows: list[dict[str, str]] = []
    for shard_path in shard_paths:
        try:
            with open(shard_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                all_rows.extend(list(reader))
        except Exception as e:
            return [], f"Error reading {shard_path}: {e}"

    return all_rows, None


def read_inventory() -> tuple[dict[str, str], str | None]:
    """Read inventory and return dict of doc_path -> truth_status."""
    repo_root = get_repo_root()
    inventory_path = repo_root / "docs" / "docs_inventory.csv"

    if not inventory_path.exists():
        return {}, "Inventory file not found"

    inventory: dict[str, str] = {}
    try:
        with open(inventory_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                doc_path = row.get("doc_path", "").strip()
                truth_status = row.get("truth_status", "").strip()
                if doc_path:
                    inventory[doc_path] = truth_status
        return inventory, None
    except Exception as e:
        return {}, f"Error reading inventory: {e}"