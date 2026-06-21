"""Sharding utilities for generated_claim_candidates CSV.

Splits large CSV into multiple shard files for LLM-friendly gate compliance.
"""

from __future__ import annotations

import csv
from pathlib import Path

from scripts.docs_claim_candidates_contract import GENERATED_CSV, GENERATED_CSV_DIR
from scripts.docs_claim_candidates_rules import CSV_FIELDS

NUM_SHARDS = 30


def get_shard_pattern() -> str:
    """Get glob pattern for shard files."""
    return str(GENERATED_CSV_DIR / "generated_claim_candidates-shard-*.csv")


def get_shard_files() -> list[Path]:
    """Get all shard files in sorted order."""
    return sorted(GENERATED_CSV_DIR.glob("generated_claim_candidates-shard-*.csv"))


def shard_csv(input_path: Path, num_shards: int = NUM_SHARDS) -> list[Path]:
    """Split a CSV into multiple shard files.

    Returns list of created shard file paths.
    """
    if not input_path.exists():
        return []

    rows: list[dict[str, str]] = []
    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return []

    shard_size = (len(rows) + num_shards - 1) // num_shards
    shard_files: list[Path] = []

    for shard_idx in range(num_shards):
        start = shard_idx * shard_size
        end = min(start + shard_size, len(rows))
        shard_rows = rows[start:end]

        if not shard_rows:
            continue

        shard_path = GENERATED_CSV_DIR / f"generated_claim_candidates-shard-{shard_idx:02d}.csv"
        with open(shard_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(shard_rows)

        shard_files.append(shard_path)

    return shard_files


def read_all_shards() -> tuple[list[dict[str, str]], str | None]:
    """Read all shard files and combine rows.

    Returns (combined_rows, error_msg).
    """
    shard_files = get_shard_files()

    if not shard_files:
        # Fallback to main CSV if no shards exist
        if GENERATED_CSV.exists():
            rows: list[dict[str, str]] = []
            try:
                with open(GENERATED_CSV, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                return rows, None
            except Exception as e:
                return [], f"Error reading CSV: {e}"
        return [], None

    all_rows: list[dict[str, str]] = []
    for shard_path in shard_files:
        try:
            with open(shard_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                all_rows.extend(list(reader))
        except Exception as e:
            return [], f"Error reading shard {shard_path}: {e}"

    return all_rows, None
