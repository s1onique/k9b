"""Contracts for docs_inventory verifier.

Defines constants, enums, required columns, and result types.
"""

from __future__ import annotations

from pathlib import Path

# File paths (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
INVENTORY_CSV = REPO_ROOT / "docs" / "docs_inventory.csv"

# Allowed doc_class values
ALLOWED_DOC_CLASS = {
    "canonical",
    "reference",
    "runbook",
    "architecture",
    "design_proposal",
    "historical",
    "superseded",
    "generated",
    "epic_wal",
    "external_import",
    "doctrine",
}

# Allowed truth_status values
ALLOWED_TRUTH_STATUS = {
    "current",
    "historical",
    "superseded",
    "generated",
    "planned",
    "stale",
    "unknown",
}

# Valid archived/deleted statuses that exempt existence check
ARCHIVED_STATUSES = {"historical", "superseded"}

# Boolean-like values for claim_trace_required
BOOLEAN_VALUES = {"true", "false"}


class InventoryError(Exception):
    """Base exception for inventory errors."""
    pass


class InventoryCheckResult:
    """Result of a single inventory check."""

    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: InventoryCheckResult) -> None:
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)