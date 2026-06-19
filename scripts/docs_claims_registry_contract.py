"""Contracts for docs_claims_registry verifier.

Defines constants, enums, required columns, and result types.
"""

from __future__ import annotations

import re
from pathlib import Path

# File paths (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
REGISTRY_CSV = REPO_ROOT / "docs" / "claims" / "docs_claims_registry.csv"
INVENTORY_CSV = REPO_ROOT / "docs" / "docs_inventory.csv"

# Allowed claim_type values
ALLOWED_CLAIM_TYPE = {
    "behavior",
    "security",
    "operator",
    "data_model",
    "api_contract",
    "ui_contract",
    "ci_gate",
    "architecture",
    "performance",
    "historical",
    "planned",
}

# Allowed claim_status values
ALLOWED_CLAIM_STATUS = {
    "current",
    "planned",
    "historical",
    "stale",
    "unsupported",
    "superseded",
}

# Allowed evidence_status values
ALLOWED_EVIDENCE_STATUS = {
    "pending",
    "linked",
    "not_required",
    "manual_only",
    "unsupported",
}

# Allowed freshness_policy values
ALLOWED_FRESHNESS_POLICY = {
    "on_change",
    "per_release",
    "manual_review",
    "historical_only",
    "not_applicable",
}

# Boolean-like values for evidence_required
BOOLEAN_VALUES = {"true", "false"}

# Claim ID pattern: DOC-CLAIM-0001
CLAIM_ID_PATTERN = re.compile(r"^DOC-CLAIM-\d{4}$")

# Candidate ID pattern: DOC-CAND-<12-char-hex>
CANDIDATE_ID_PATTERN = re.compile(r"^DOC-CAND-[a-f0-9]{12}$")

# Required columns in exact order
REQUIRED_COLUMNS = [
    "claim_id",
    "doc_path",
    "anchor",
    "claim_text",
    "claim_type",
    "claim_status",
    "owner_area",
    "evidence_required",
    "evidence_status",
    "evidence_ref",
    "freshness_policy",
    "notes",
    "candidate_ids",
]


class RegistryError(Exception):
    """Base exception for registry errors."""
    pass


class RegistryCheckResult:
    """Result of a single registry check."""

    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: RegistryCheckResult) -> None:
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def read_csv_header(path: Path) -> tuple[list[str], str | None]:
    """Read raw CSV header row. Returns (header, error)."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            import csv as _csv
            reader = _csv.reader(f)
            header = next(reader, [])
            return header, None
    except Exception as e:
        return [], f"CSV parse error: {e}"
