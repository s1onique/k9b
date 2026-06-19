"""Contracts for docs_claim_traceability verifier.

Defines constants, enums, required columns, and result types.
"""

from __future__ import annotations

import re
from pathlib import Path

# File paths (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
MATRIX_CSV = REPO_ROOT / "docs" / "claims" / "docs_claim_traceability_matrix.csv"
REGISTRY_CSV = REPO_ROOT / "docs" / "claims" / "docs_claims_registry.csv"
CI_GATE_MAPPING = REPO_ROOT / "scripts" / "ci_gate_mapping.json"

# Allowed evidence_kind values
ALLOWED_EVIDENCE_KIND = {
    "unit_test",
    "integration_test",
    "frontend_test",
    "verifier",
    "ci_gate",
    "source_anchor",
    "manual_lab",
    "historical_record",
    "none",
}

# Allowed coverage_strength values
ALLOWED_COVERAGE_STRENGTH = {
    "direct",
    "indirect",
    "partial",
    "manual",
    "historical",
    "none",
}

# Allowed verification_status values
ALLOWED_VERIFICATION_STATUS = {
    "verified",
    "pending",
    "manual_only",
    "historical_only",
    "unsupported",
}

# Trace ID pattern: DOC-TRACE-0001
TRACE_ID_PATTERN = re.compile(r"^DOC-TRACE-\d{4}$")

# Evidence kinds that require evidence_path validation
PATH_VALIDATED_KINDS = {
    "unit_test",
    "integration_test",
    "frontend_test",
    "verifier",
    "source_anchor",
    "historical_record",
}

# Evidence kinds that require gate_name
GATE_REQUIRED_KINDS = {"ci_gate"}

# Required columns in exact order
REQUIRED_COLUMNS = [
    "trace_id",
    "claim_id",
    "evidence_kind",
    "evidence_ref",
    "evidence_path",
    "evidence_symbol",
    "gate_name",
    "coverage_strength",
    "verification_status",
    "last_verified",
    "notes",
]


class TraceabilityCheckResult:
    """Result of a single traceability check."""

    def __init__(self) -> None:
        self.passed = True
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, msg: str) -> None:
        self.passed = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def merge(self, other: TraceabilityCheckResult) -> None:
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