"""Loader for docs_claims_registry verifier.

Handles CSV reading, header validation, and row normalization.
"""

from __future__ import annotations

import csv
from pathlib import Path

from docs_claims_registry_contract import (
    REGISTRY_CSV,
    INVENTORY_CSV,
    read_csv_header,
)


def read_registry() -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the registry CSV. Returns (rows, error_msg)."""
    if not REGISTRY_CSV.exists():
        return [], f"Registry file not found: {REGISTRY_CSV}"

    try:
        with open(REGISTRY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading registry: {e}"


def read_inventory_paths() -> tuple[set[str], str | None]:
    """Read inventory and return set of doc paths. Returns (paths, error_msg)."""
    if not INVENTORY_CSV.exists():
        return set(), f"Inventory file not found: {INVENTORY_CSV}"

    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            paths = {row.get("doc_path", "").strip() for row in reader}
            return paths, None
    except csv.Error as e:
        return set(), f"Inventory CSV parse error: {e}"
    except Exception as e:
        return set(), f"Error reading inventory: {e}"


def get_inventory_status(doc_path: str) -> str | None:
    """Get truth_status for a doc_path from inventory."""
    if not INVENTORY_CSV.exists():
        return None
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("doc_path", "").strip() == doc_path:
                    return row.get("truth_status", "").strip()
        return None
    except Exception:
        return None


def read_candidates() -> dict[str, dict[str, str]]:
    """Read generated_claim_candidates shards and return dict keyed by candidate_id."""
    candidates: dict[str, dict[str, str]] = {}

    # Import from shard module (lazy to avoid circular imports)
    from docs_claim_candidates_shard import read_all_shards
    rows, _ = read_all_shards()

    for row in rows:
        cid = row.get("candidate_id", "").strip()
        if cid:
            candidates[cid] = row

    return candidates
