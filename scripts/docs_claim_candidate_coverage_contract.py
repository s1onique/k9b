"""Contracts for docs_claim_candidate_coverage verifier.

Defines constants, result types, and validation enums.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
GENERATED_CSV_DIR = REPO_ROOT / "docs" / "claims"
GENERATED_CSV = GENERATED_CSV_DIR / "generated_claim_candidates.csv"
INVENTORY_CSV = REPO_ROOT / "docs" / "docs_inventory.csv"

# Registration status values
REGISTRATION_STATUS_VALUES = {
    "registered",
    "unregistered",
    "ignored_historical",
    "ignored_stale",
    "ignored_low_value",
    "ignored_by_policy",
}

# Severity values
SEVERITY_VALUES = {"high", "medium", "low"}


class CoverageError(Exception):
    """Base exception for coverage errors."""
    pass


class CoverageCheckResult:
    """Result of a single coverage check."""

    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def add_error(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_info(self, msg: str) -> None:
        self.info.append(msg)

    def merge(self, other: CoverageCheckResult) -> None:
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.info.extend(other.info)
