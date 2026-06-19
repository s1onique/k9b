"""Loader for docs_claim_traceability verifier.

Handles CSV reading, header validation, and row normalization.
"""

from __future__ import annotations

import csv
import json

from docs_claim_traceability_contract import (
    MATRIX_CSV,
    REGISTRY_CSV,
    CI_GATE_MAPPING,
)


def read_matrix() -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the traceability matrix CSV. Returns (rows, error_msg)."""
    if not MATRIX_CSV.exists():
        return [], f"Matrix file not found: {MATRIX_CSV}"

    try:
        with open(MATRIX_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading matrix: {e}"


def read_registry() -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the claims registry CSV. Returns (rows, error_msg)."""
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


def read_ci_gate_mapping() -> tuple[dict[str, object], str | None]:
    """Read CI gate mapping JSON. Returns (mapping, error_msg)."""
    if not CI_GATE_MAPPING.exists():
        return {}, f"CI gate mapping not found: {CI_GATE_MAPPING}"

    try:
        with open(CI_GATE_MAPPING, encoding="utf-8") as f:
            mapping = json.load(f)
        return mapping, None
    except json.JSONDecodeError as e:
        return {}, f"JSON parse error: {e}"
    except Exception as e:
        return {}, f"Error reading CI gate mapping: {e}"