"""Contracts for docs_claim_disposition ledger.

Defines constants, enums, required columns, and result types.
"""

from __future__ import annotations

import re
from pathlib import Path

# File paths (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
DISPOSITION_CLAIMS_DIR = REPO_ROOT / "docs" / "claims"
DISPOSITION_CSV_PATTERN = "docs_claim_dispositions-shard-%02d.csv"
DISPOSITION_SHARD_COUNT = 30  # Match candidate shards

def get_disposition_csv_path(shard_num: int) -> Path:
    """Get path for a specific disposition shard."""
    return DISPOSITION_CLAIMS_DIR / (DISPOSITION_CSV_PATTERN % shard_num)

def get_all_disposition_shard_paths() -> list[Path]:
    """Get all disposition shard paths in order."""
    return [get_disposition_csv_path(i) for i in range(DISPOSITION_SHARD_COUNT)]

# Allowed disposition values
ALLOWED_DISPOSITIONS = {
    "registered_existing_claim",
    "registered_new_claim",
    "covered_by_existing_claim",
    "duplicate_candidate",
    "false_positive",
    "heading_or_table_fragment",
    "too_granular",
    "historical",
    "stale",
    "docs_only_context",
    "implementation_detail_not_claim",
    "policy_statement_only",
    "backlog_future_claim",
    "needs_new_claim",
    "ignored_by_policy",
}

# Allowed reason_code values
ALLOWED_REASON_CODES = {
    "already_registered",
    "covered_by_broader_claim",
    "duplicate_same_doc",
    "duplicate_cross_doc",
    "generated_from_heading",
    "generated_from_table_fragment",
    "historical_doc",
    "stale_doc",
    "non_normative_description",
    "implementation_detail",
    "policy_statement",
    "low_value_context",
    "not_a_claim",
    "too_granular_for_registry",
    "requires_future_human_review",
    "promoted_to_registry",
}

# Claim ID pattern: DOC-CLAIM-0001
CLAIM_ID_PATTERN = re.compile(r"^DOC-CLAIM-\d{4}$")

# Candidate ID pattern: DOC-CAND-<12-char-hex>
CANDIDATE_ID_PATTERN = re.compile(r"^DOC-CAND-[a-f0-9]{12}$")

# Required columns in exact order
REQUIRED_COLUMNS = [
    "candidate_id",
    "disposition",
    "claim_id",
    "covered_by_claim_id",
    "reason_code",
    "reviewed_at",
    "reviewer_notes",
]

# Dispositions that require claim_id to be set
DISPOSITIONS_REQUIRING_CLAIM_ID = {
    "registered_existing_claim",
    "registered_new_claim",
}

# Dispositions that require covered_by_claim_id to be set
DISPOSITIONS_REQUIRING_COVERED_BY_CLAIM_ID = {
    "covered_by_existing_claim",
}

# Dispositions that allow empty reviewer_notes
DISPOSITIONS_ALLOWING_EMPTY_NOTES = {
    "registered_existing_claim",
}

# Dispositions that require meaningful reason_code
DISPOSITIONS_REQUIRING_REASON_CODE = {
    "ignored_by_policy",
    "false_positive",
    "heading_or_table_fragment",
    "too_granular",
    "historical",
    "stale",
    "docs_only_context",
    "implementation_detail_not_claim",
    "policy_statement_only",
    "backlog_future_claim",
    "needs_new_claim",
}


class DispositionError(Exception):
    """Base exception for disposition errors."""
    pass


class DispositionCheckResult:
    """Result of a single disposition check."""

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

    def merge(self, other: DispositionCheckResult) -> None:
        if not other.passed:
            self.passed = False
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.info.extend(other.info)


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
