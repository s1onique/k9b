"""Loader for docs_claim_disposition ledger.

Handles sharded CSV reading, header validation, and row normalization.
Compatible with sharded generated candidates.
"""

from __future__ import annotations

import csv
from pathlib import Path

from docs_claim_disposition_contract import (
    DISPOSITION_SHARD_COUNT,
    REQUIRED_COLUMNS,
    get_all_disposition_shard_paths,
    read_csv_header,
)


def read_dispositions() -> tuple[list[dict[str, str]], str | None]:
    """Read and parse all disposition ledger shards. Returns (rows, error_msg)."""
    all_rows: list[dict[str, str]] = []
    shard_paths = get_all_disposition_shard_paths()
    
    # Check if any shards exist
    if not any(p.exists() for p in shard_paths):
        # Fallback: check for legacy monolithic file
        legacy_path = Path(__file__).parent.parent / "docs" / "claims" / "docs_claim_dispositions.csv"
        if legacy_path.exists():
            try:
                with open(legacy_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    return list(reader), None
            except csv.Error as e:
                return [], f"CSV parse error: {e}"
            except Exception as e:
                return [], f"Error reading disposition ledger: {e}"
        return [], f"No disposition shards found at {shard_paths[0]}"
    
    # Read all shards in order
    for i, shard_path in enumerate(shard_paths):
        if shard_path.exists():
            try:
                with open(shard_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                    all_rows.extend(rows)
            except csv.Error as e:
                return [], f"CSV parse error in shard {i}: {e}"
            except Exception as e:
                return [], f"Error reading disposition shard {i}: {e}"
    
    return all_rows, None


def validate_header(path: Path) -> tuple[bool, str | None]:
    """Validate that the CSV has the required header columns."""
    header, error = read_csv_header(path)
    if error:
        return False, f"Failed to read header: {error}"

    # Check all required columns are present
    missing = set(REQUIRED_COLUMNS) - set(header)
    if missing:
        return False, f"Missing required columns: {', '.join(sorted(missing))}"

    # Check for duplicate columns
    if len(header) != len(set(header)):
        return False, "Duplicate columns in header"

    return True, None


def validate_all_shards() -> tuple[bool, str | None]:
    """Validate all disposition shards have correct headers."""
    shard_paths = get_all_disposition_shard_paths()
    for i, shard_path in enumerate(shard_paths):
        if shard_path.exists():
            valid, error = validate_header(shard_path)
            if not valid:
                return False, f"Shard {i}: {error}"
    return True, None


def get_disposition_map() -> tuple[dict[str, dict[str, str]], str | None]:
    """Read dispositions and return dict keyed by candidate_id."""
    rows, error = read_dispositions()
    if error:
        return {}, error

    disposition_map: dict[str, dict[str, str]] = {}
    for row in rows:
        cid = row.get("candidate_id", "").strip()
        if cid:
            if cid in disposition_map:
                return {}, f"Duplicate disposition for candidate_id: {cid}"
            disposition_map[cid] = row

    return disposition_map, None
