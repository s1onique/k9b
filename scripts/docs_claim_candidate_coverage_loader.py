"""Loader for docs_claim_candidate_coverage verifier.

Handles CSV reading for candidates and inventory.
"""

from __future__ import annotations

import csv
from pathlib import Path

# Import only what's needed


def read_csv(path: Path) -> tuple[list[dict[str, str]], str | None]:
    """Read and parse a CSV file. Returns (rows, error_msg)."""
    if not path.exists():
        return [], None

    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading CSV: {e}"


def load_candidates() -> tuple[list[dict[str, str]], str | None]:
    """Load candidates from generated CSV (shards or single file)."""
    # Import here to avoid circular imports
    from scripts.docs_claim_candidates_shard import read_all_shards
    return read_all_shards()
