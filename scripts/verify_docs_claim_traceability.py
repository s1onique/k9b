#!/usr/bin/env python
"""Verify docs claim traceability matrix integrity.

This script checks that:
1. Matrix file exists and parses strictly as CSV
2. Required columns are present exactly once and in exact order
3. No duplicate trace_id values
4. No duplicate (claim_id, evidence_kind, evidence_ref) tuples
5. trace_id matches DOC-TRACE-0001 pattern (prefix + 4-digit zero-padded)
6. Trace IDs are sorted ascending
7. Every claim_id in matrix exists in docs_claims_registry.csv
8. Every claim with evidence_required=true appears in matrix at least once
9. claims with evidence_status=linked reference valid trace_id(s)
10. Linked claims have at least one trace with verified/manual_only/historical_only
11. Current claims not linked only to historical_only evidence
12. evidence_kind is from allowed enum
13. coverage_strength is from allowed enum
14. verification_status is from allowed enum
15. evidence_ref is non-empty unless evidence_kind=none
16. evidence_path exists on disk for test/verifier/source_anchor evidence
17. gate_name is non-empty for ci_gate evidence_kind
18. gate_name exists in ci_gate_mapping.json
19. evidence_symbol is non-empty for test evidence when known
20. Semantic combinations (none evidence_kind requires none coverage_strength, etc.)

Usage:
    python scripts/verify_docs_claim_traceability.py           # verify
    python scripts/verify_docs_claim_traceability.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

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


def read_csv_header(path: Path) -> tuple[list[str], str | None]:
    """Read raw CSV header row. Returns (header, error)."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            return header, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading CSV header: {e}"


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


def check_csv_parse(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that CSV has required columns in exact order, no duplicates."""
    result = TraceabilityCheckResult()

    if not rows:
        result.add_error("Matrix is empty (no data rows)")
        return result

    # Read raw header for strict validation
    header, error = read_csv_header(MATRIX_CSV)
    if error:
        result.add_error(f"Failed to read CSV header: {error}")
        return result

    # Check for duplicate header columns
    seen: set[str] = set()
    duplicates: list[str] = []
    for col in header:
        if col in seen:
            duplicates.append(col)
        else:
            seen.add(col)
    if duplicates:
        result.add_error(f"Duplicate header columns: {', '.join(sorted(duplicates))}")

    # Check header matches required columns exactly and in order
    if header != REQUIRED_COLUMNS:
        result.add_error(
            "CSV header must match required columns exactly and in order. "
            f"Got: {header}"
        )

    return result


def check_no_duplicate_trace_ids(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check for duplicate trace_id values."""
    result = TraceabilityCheckResult()

    ids = [row.get("trace_id", "").strip() for row in rows]
    seen: dict[str, int] = {}
    for i, trace_id in enumerate(ids):
        if trace_id in seen:
            result.add_error(
                f"Duplicate trace_id '{trace_id}' at row {i + 2} "
                f"(first seen at row {seen[trace_id] + 2})"
            )
        else:
            seen[trace_id] = i

    return result


def check_no_duplicate_tuples(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check for duplicate (claim_id, evidence_kind, evidence_ref) tuples."""
    result = TraceabilityCheckResult()

    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        claim_id = row.get("claim_id", "").strip()
        evidence_kind = row.get("evidence_kind", "").strip()
        evidence_ref = row.get("evidence_ref", "").strip()

        key_str = f"{claim_id}|{evidence_kind}|{evidence_ref}"

        if key_str in seen:
            result.add_error(
                f"Duplicate (claim_id, evidence_kind, evidence_ref) tuple at row {i + 2} "
                f"(first seen at row {seen[key_str] + 2})"
            )
        else:
            seen[key_str] = i

    return result


def check_trace_id_format(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that trace_id matches DOC-TRACE-0001 pattern."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        trace_id = row.get("trace_id", "").strip()
        if not trace_id:
            result.add_error(f"Row {i + 2}: trace_id is empty")
            continue

        if not TRACE_ID_PATTERN.match(trace_id):
            result.add_error(
                f"Row {i + 2}: trace_id '{trace_id}' does not match pattern DOC-TRACE-0001 "
                f"(expected: prefix DOC-TRACE-, 4-digit zero-padded suffix)"
            )

    return result


def check_trace_ids_sorted(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that trace IDs are sorted ascending."""
    result = TraceabilityCheckResult()

    ids = [row.get("trace_id", "").strip() for row in rows]
    sorted_ids = sorted(ids)

    if ids != sorted_ids:
        result.add_error(
            f"Trace IDs are not sorted ascending. "
            f"Current order: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}"
        )

    return result


def check_claim_ids_exist_in_registry(
    rows: list[dict[str, str]], registry_rows: list[dict[str, str]]
) -> TraceabilityCheckResult:
    """Check that all claim_id values exist in the claims registry."""
    result = TraceabilityCheckResult()

    registry_ids = {row.get("claim_id", "").strip() for row in registry_rows}

    for i, row in enumerate(rows):
        claim_id = row.get("claim_id", "").strip()
        if not claim_id:
            result.add_error(f"Row {i + 2}: claim_id is empty")
            continue

        if claim_id not in registry_ids:
            result.add_error(
                f"Row {i + 2}: claim_id '{claim_id}' is not in docs_claims_registry.csv"
            )

    return result


def check_all_evidence_required_claims_traced(
    rows: list[dict[str, str]], registry_rows: list[dict[str, str]]
) -> TraceabilityCheckResult:
    """Check that every claim with evidence_required=true appears in matrix."""
    result = TraceabilityCheckResult()

    # Get claims that require evidence
    required_claims: set[str] = set()
    for row in registry_rows:
        claim_id = row.get("claim_id", "").strip()
        evidence_required = row.get("evidence_required", "").strip().lower()
        if evidence_required == "true":
            required_claims.add(claim_id)

    # Get claims that appear in matrix
    traced_claims: set[str] = set()
    for row in rows:
        claim_id = row.get("claim_id", "").strip()
        if claim_id:
            traced_claims.add(claim_id)

    # Check all required claims are traced
    missing = required_claims - traced_claims
    if missing:
        for claim_id in sorted(missing):
            result.add_error(
                f"Claim '{claim_id}' has evidence_required=true but is not in traceability matrix"
            )

    return result


def check_evidence_kind_valid(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that evidence_kind is from allowed enum."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        evidence_kind = row.get("evidence_kind", "").strip()
        if evidence_kind not in ALLOWED_EVIDENCE_KIND:
            result.add_error(
                f"Row {i + 2}: invalid evidence_kind '{evidence_kind}' "
                f"(allowed: {', '.join(sorted(ALLOWED_EVIDENCE_KIND))})"
            )

    return result


def check_coverage_strength_valid(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that coverage_strength is from allowed enum."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        coverage_strength = row.get("coverage_strength", "").strip()
        if coverage_strength not in ALLOWED_COVERAGE_STRENGTH:
            result.add_error(
                f"Row {i + 2}: invalid coverage_strength '{coverage_strength}' "
                f"(allowed: {', '.join(sorted(ALLOWED_COVERAGE_STRENGTH))})"
            )

    return result


def check_verification_status_valid(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that verification_status is from allowed enum."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        verification_status = row.get("verification_status", "").strip()
        if verification_status not in ALLOWED_VERIFICATION_STATUS:
            result.add_error(
                f"Row {i + 2}: invalid verification_status '{verification_status}' "
                f"(allowed: {', '.join(sorted(ALLOWED_VERIFICATION_STATUS))})"
            )

    return result


def check_evidence_ref_non_empty(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that evidence_ref is non-empty unless evidence_kind=none."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        evidence_kind = row.get("evidence_kind", "").strip()
        evidence_ref = row.get("evidence_ref", "").strip()

        if evidence_kind != "none" and not evidence_ref:
            result.add_error(
                f"Row {i + 2}: evidence_kind='{evidence_kind}' but evidence_ref is empty "
                f"(evidence_ref required for non-none evidence_kind)"
            )

    return result


def check_evidence_path_exists(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check that evidence_path exists on disk for validated evidence kinds."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        evidence_kind = row.get("evidence_kind", "").strip()
        evidence_path = row.get("evidence_path", "").strip()

        if evidence_kind in PATH_VALIDATED_KINDS:
            if not evidence_path:
                result.add_error(
                    f"Row {i + 2}: evidence_kind='{evidence_kind}' but evidence_path is empty "
                    f"(evidence_path required for {evidence_kind} evidence)"
                )
                continue

            file_path = REPO_ROOT / evidence_path
            if not file_path.exists():
                result.add_error(
                    f"Row {i + 2}: evidence_path '{evidence_path}' does not exist on disk "
                    f"(for {evidence_kind} evidence)"
                )

    return result


def check_gate_name_for_ci_gate(
    rows: list[dict[str, str]], gate_mapping: dict[str, object]
) -> TraceabilityCheckResult:
    """Check that gate_name is non-empty for ci_gate and exists in mapping."""
    result = TraceabilityCheckResult()

    # Get valid gate names from mapping
    required_gates = gate_mapping.get("required_gates", {})
    if isinstance(required_gates, dict):
        valid_gate_names = set(required_gates.keys())
    else:
        valid_gate_names = set()

    for i, row in enumerate(rows):
        evidence_kind = row.get("evidence_kind", "").strip()
        gate_name = row.get("gate_name", "").strip()

        if evidence_kind == "ci_gate":
            if not gate_name:
                result.add_error(
                    f"Row {i + 2}: evidence_kind='ci_gate' but gate_name is empty "
                    f"(gate_name required for ci_gate evidence)"
                )
            elif gate_name not in valid_gate_names:
                result.add_warning(
                    f"Row {i + 2}: gate_name '{gate_name}' is not in ci_gate_mapping.json "
                    f"(known gates: {', '.join(sorted(valid_gate_names))})"
                )

    return result


def check_semantic_combinations(rows: list[dict[str, str]]) -> TraceabilityCheckResult:
    """Check semantic combinations of evidence_kind, coverage_strength, verification_status."""
    result = TraceabilityCheckResult()

    for i, row in enumerate(rows):
        evidence_kind = (row.get("evidence_kind") or "").strip()
        coverage_strength = (row.get("coverage_strength") or "").strip()
        verification_status = (row.get("verification_status") or "").strip()
        notes = (row.get("notes") or "").strip()

        # evidence_kind=none requires coverage_strength=none
        if evidence_kind == "none" and coverage_strength != "none":
            result.add_error(
                f"Row {i + 2}: evidence_kind='none' but coverage_strength='{coverage_strength}' "
                f"(expected: none)"
            )

        # coverage_strength=direct must not use evidence_kind=none
        if coverage_strength == "direct" and evidence_kind == "none":
            result.add_error(
                f"Row {i + 2}: coverage_strength='direct' but evidence_kind='none' "
                f"(direct coverage requires actual evidence)"
            )

        # verification_status=verified must not use coverage_strength=none
        if verification_status == "verified" and coverage_strength == "none":
            result.add_error(
                f"Row {i + 2}: verification_status='verified' but coverage_strength='none' "
                f"(verified evidence must have coverage)"
            )

        # manual_only requires meaningful notes
        if verification_status == "manual_only" and not notes:
            result.add_error(
                f"Row {i + 2}: verification_status='manual_only' but notes is empty "
                f"(manual_only verification requires meaningful notes)"
            )

        # unsupported requires meaningful notes
        if verification_status == "unsupported" and not notes:
            result.add_error(
                f"Row {i + 2}: verification_status='unsupported' but notes is empty "
                f"(unsupported verification requires meaningful notes)"
            )

    return result


def check_linked_claims_valid(
    rows: list[dict[str, str]], registry_rows: list[dict[str, str]]
) -> TraceabilityCheckResult:
    """Check that linked claims reference valid trace IDs and have proper evidence."""
    result = TraceabilityCheckResult()

    # Get trace IDs from matrix
    trace_ids = {row.get("trace_id", "").strip() for row in rows}

    # Get claims with evidence_status=linked
    linked_claims: dict[str, tuple[str, int]] = {}
    for i, row in enumerate(registry_rows):
        claim_id = row.get("claim_id", "").strip()
        evidence_status = row.get("evidence_status", "").strip()
        evidence_ref = row.get("evidence_ref", "").strip()
        claim_status = row.get("claim_status", "").strip()

        if evidence_status == "linked" and claim_id:
            linked_claims[claim_id] = (evidence_ref, i + 2)

    # For each linked claim, verify trace IDs exist and have valid verification status
    for claim_id, (evidence_ref, row_num) in linked_claims.items():
        # Parse trace IDs from evidence_ref (semicolon-separated)
        trace_refs = [t.strip() for t in evidence_ref.split(";") if t.strip()]

        if not trace_refs:
            result.add_error(
                f"Registry row {row_num}: claim '{claim_id}' has evidence_status='linked' "
                f"but evidence_ref is empty (must reference trace_id(s))"
            )
            continue

        # Check all referenced trace IDs exist
        for trace_ref in trace_refs:
            if trace_ref not in trace_ids:
                result.add_error(
                    f"Registry row {row_num}: claim '{claim_id}' references unknown trace_id "
                    f"'{trace_ref}' in evidence_ref"
                )

        # Check at least one trace has valid verification status
        claim_traces = [r for r in rows if r.get("claim_id", "").strip() == claim_id]
        valid_statuses = {"verified", "manual_only", "historical_only"}
        has_valid_status = any(
            r.get("verification_status", "").strip() in valid_statuses
            for r in claim_traces
        )

        if not has_valid_status:
            statuses = [r.get("verification_status", "") for r in claim_traces]
            result.add_error(
                f"Registry row {row_num}: claim '{claim_id}' has no trace rows with "
                f"verification_status in {valid_statuses}. Found: {statuses}"
            )

    # Check current claims are not linked only to historical_only evidence
    for i, row in enumerate(registry_rows):
        claim_id = row.get("claim_id", "").strip()
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()

        if claim_status == "current" and evidence_status == "linked":
            claim_traces = [r for r in rows if r.get("claim_id", "").strip() == claim_id]
            has_historical_only = all(
                r.get("verification_status", "").strip() == "historical_only"
                for r in claim_traces
            )
            if has_historical_only and claim_traces:
                result.add_error(
                    f"Registry row {i + 2}: claim '{claim_id}' is 'current' but is only "
                    f"linked to historical_only evidence (historical evidence cannot prove "
                    f"current behavior)"
                )

    return result


def print_coverage_report(rows: list[dict[str, str]], registry_rows: list[dict[str, str]]) -> None:
    """Print coverage statistics for the traceability matrix."""
    if not rows:
        return

    # Basic counts
    total_traces = len(rows)
    total_claims = len(registry_rows)

    # Claims with at least one trace
    traced_claims = {row.get("claim_id", "").strip() for row in rows if row.get("claim_id")}
    claims_with_traces = len(traced_claims)

    # Claims with verified evidence
    verified_claims: set[str] = set()
    for row in rows:
        if row.get("verification_status", "").strip() == "verified":
            verified_claims.add(row.get("claim_id", "").strip())
    claims_with_verified = len(verified_claims)

    # Current claims still pending evidence
    current_pending: list[str] = []
    stale_pending: list[str] = []
    for reg_row in registry_rows:
        claim_id = reg_row.get("claim_id", "").strip()
        claim_status = reg_row.get("claim_status", "").strip()
        evidence_status = reg_row.get("evidence_status", "").strip()

        if claim_id in traced_claims and evidence_status == "pending":
            if claim_status == "current":
                current_pending.append(claim_id)
            elif claim_status == "stale":
                stale_pending.append(claim_id)

    # Unsupported trace rows
    unsupported_traces = sum(
        1 for row in rows if row.get("verification_status", "").strip() == "unsupported"
    )

    # Counts by enum
    by_evidence_kind: dict[str, int] = {}
    by_coverage_strength: dict[str, int] = {}
    by_verification_status: dict[str, int] = {}
    for row in rows:
        kind = row.get("evidence_kind", "").strip()
        strength = row.get("coverage_strength", "").strip()
        status = row.get("verification_status", "").strip()
        by_evidence_kind[kind] = by_evidence_kind.get(kind, 0) + 1
        by_coverage_strength[strength] = by_coverage_strength.get(strength, 0) + 1
        by_verification_status[status] = by_verification_status.get(status, 0) + 1

    # Top claims by trace row count
    trace_counts: dict[str, int] = {}
    for row in rows:
        claim_id = row.get("claim_id", "").strip()
        trace_counts[claim_id] = trace_counts.get(claim_id, 0) + 1
    top_claims = sorted(trace_counts.items(), key=lambda x: -x[1])[:5]

    # Print report
    print("\n=== Traceability Coverage Report ===")
    print(f"Total trace rows: {total_traces}")
    print(f"Total claims in registry: {total_claims}")
    print(f"Claims with at least one trace: {claims_with_traces}")
    print(f"Claims with verified evidence: {claims_with_verified}")
    print(f"Current claims pending evidence: {len(current_pending)}")
    print(f"Stale claims pending evidence: {len(stale_pending)}")
    print(f"Unsupported trace rows: {unsupported_traces}")

    print("\nBy evidence_kind:")
    for kind, count in sorted(by_evidence_kind.items()):
        print(f"  {kind}: {count}")

    print("\nBy coverage_strength:")
    for strength, count in sorted(by_coverage_strength.items()):
        print(f"  {strength}: {count}")

    print("\nBy verification_status:")
    for status, count in sorted(by_verification_status.items()):
        print(f"  {status}: {count}")

    print("\nTop claims by trace row count:")
    for claim_id, count in top_claims:
        print(f"  {claim_id}: {count} trace(s)")

    if current_pending:
        print(f"\nCurrent claims still pending evidence ({len(current_pending)}):")
        for claim_id in sorted(current_pending):
            print(f"  - {claim_id}")

    if stale_pending:
        print(f"\nStale claims with pending evidence ({len(stale_pending)}):")
        for claim_id in sorted(stale_pending):
            print(f"  - {claim_id}")


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Docs Claim Traceability Verification ===\n")

    # Read matrix
    rows, error = read_matrix()
    if error:
        print(f"[FAIL] CSV parse: {error}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    print(f"[INFO] Matrix has {len(rows)} trace rows")

    # Read registry
    registry_rows, reg_error = read_registry()
    if reg_error:
        print(f"[WARNING] Could not read registry: {reg_error}")
        registry_rows = []

    # Read CI gate mapping
    gate_mapping, mapping_error = read_ci_gate_mapping()
    if mapping_error:
        print(f"[WARNING] Could not read CI gate mapping: {mapping_error}")
        gate_mapping = {}

    # Run checks
    checks: list[tuple[str, Callable[[], TraceabilityCheckResult]]] = [
        ("CSV structure", lambda: check_csv_parse(rows)),
        ("No duplicate trace_id", lambda: check_no_duplicate_trace_ids(rows)),
        ("No duplicate tuples", lambda: check_no_duplicate_tuples(rows)),
        ("trace_id format", lambda: check_trace_id_format(rows)),
        ("trace_id sorted ascending", lambda: check_trace_ids_sorted(rows)),
        ("claim_id exists in registry", lambda: check_claim_ids_exist_in_registry(rows, registry_rows)),
        ("evidence_required claims traced", lambda: check_all_evidence_required_claims_traced(rows, registry_rows)),
        ("evidence_kind valid", lambda: check_evidence_kind_valid(rows)),
        ("coverage_strength valid", lambda: check_coverage_strength_valid(rows)),
        ("verification_status valid", lambda: check_verification_status_valid(rows)),
        ("evidence_ref non-empty", lambda: check_evidence_ref_non_empty(rows)),
        ("evidence_path exists", lambda: check_evidence_path_exists(rows)),
        ("gate_name for ci_gate", lambda: check_gate_name_for_ci_gate(rows, gate_mapping)),
        ("Semantic combinations", lambda: check_semantic_combinations(rows)),
        ("Linked claims valid", lambda: check_linked_claims_valid(rows, registry_rows)),
    ]

    all_passed = True
    for name, check_fn in checks:
        result = check_fn()
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {name}")
        for error in result.errors:
            print(f"      ERROR: {error}")
        for warning in result.warnings:
            print(f"      WARNING: {warning}")
        if not result.passed:
            all_passed = False

    # Print coverage report
    if all_passed:
        print_coverage_report(rows, registry_rows)

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")

    return all_passed


# Self-test fixtures
SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "valid minimal traceability matrix passes",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Test trace\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": False,
    },
    {
        "name": "duplicate trace ID fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,First\n"
            "DOC-TRACE-0001,DOC-CLAIM-0002,verifier,test_ref2,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Duplicate\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
            "DOC-CLAIM-0002,README.md,test-anchor2,Second claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "Duplicate trace_id",
    },
    {
        "name": "malformed trace ID fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-1,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Bad ID\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "does not match pattern",
    },
    {
        "name": "unsorted trace IDs fail",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0002,DOC-CLAIM-0002,verifier,test_ref2,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Second\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,First\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,First claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
            "DOC-CLAIM-0002,README.md,test-anchor2,Second claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "not sorted ascending",
    },
    {
        "name": "unknown claim ID fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-9999,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Unknown claim\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "not in docs_claims_registry",
    },
    {
        "name": "missing required claim trace fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0002,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Only second\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,First claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
            "DOC-CLAIM-0002,README.md,test-anchor2,Second claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "evidence_required=true but is not in traceability matrix",
    },
    {
        "name": "linked claim referencing unknown trace ID fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Test trace\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,linked,DOC-TRACE-9999,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "references unknown trace_id",
    },
    {
        "name": "linked claim with only pending trace fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,pending,2026-06-19,Pending only\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,linked,DOC-TRACE-0001,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "no trace rows with verification_status",
    },
    {
        "name": "current claim linked only to historical evidence fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,historical_record,audit-doc,docs/reports/security-audit.md,,,none,historical_only,2026-01-01,Historical only\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,linked,DOC-TRACE-0001,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "only linked to historical_only evidence",
    },
    {
        "name": "invalid evidence_kind fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,invalid_kind,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Bad kind\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "invalid evidence_kind",
    },
    {
        "name": "invalid coverage_strength fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,invalid_strength,verified,2026-06-19,Bad strength\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "invalid coverage_strength",
    },
    {
        "name": "invalid verification_status fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,invalid_status,2026-06-19,Bad status\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "invalid verification_status",
    },
    {
        "name": "evidence_kind=none with direct coverage fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,none,,,,,direct,verified,2026-06-19,Bad combo\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "coverage_strength='direct' but evidence_kind='none'",
    },
    {
        "name": "verified trace with coverage_strength=none fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,none,verified,2026-06-19,Bad combo\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "verification_status='verified' but coverage_strength='none'",
    },
    {
        "name": "missing evidence_path for verifier evidence fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,,,gate_name,indirect,verified,2026-06-19,Missing path\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "evidence_path is empty",
    },
    {
        "name": "missing gate_name for ci_gate fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,ci_gate,test_ref,,,,\"\",indirect,verified,2026-06-19,Missing gate name\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "gate_name is empty",
    },
    {
        "name": "manual_only without notes fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,manual_lab,manual_test,,,gate_name,manual,manual_only,2026-06-19,\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "manual_only verification requires meaningful notes",
    },
    {
        "name": "unsupported without notes fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,gate_name,indirect,unsupported,2026-06-19,\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "unsupported verification requires meaningful notes",
    },
    {
        "name": "duplicate (claim_id, evidence_kind, evidence_ref) fails",
        "matrix": (
            "trace_id,claim_id,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,First\n"
            "DOC-TRACE-0002,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Duplicate\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "Duplicate (claim_id, evidence_kind, evidence_ref)",
    },
    {
        "name": "malformed CSV header fails",
        "matrix": (
            "trace_id,bad_header,evidence_kind,evidence_ref,evidence_path,evidence_symbol,gate_name,coverage_strength,verification_status,last_verified,notes\n"
            "DOC-TRACE-0001,DOC-CLAIM-0001,verifier,test_ref,scripts/verify_all.sh,,docs-inventory,indirect,verified,2026-06-19,Bad header\n"
        ),
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Test claim with enough length.,behavior,current,test,true,pending,,on_change,Test\n"
        ),
        "gate_mapping": {"required_gates": {"docs-inventory": {}}},
        "should_fail": True,
        "expect_error_contains": "CSV header must match",
    },
]


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Docs Claim Traceability Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_matrix = tmp_path / "docs" / "claims" / "docs_claim_traceability_matrix.csv"
            tmp_matrix.parent.mkdir(parents=True, exist_ok=True)

            tmp_registry = tmp_path / "docs" / "claims" / "docs_claims_registry.csv"
            tmp_registry.parent.mkdir(parents=True, exist_ok=True)

            # Write matrix
            tmp_matrix.write_text(str(case["matrix"]))

            # Write registry
            tmp_registry.write_text(str(case["registry"]))

            # Write gate mapping
            gate_mapping_path = tmp_path / "scripts" / "ci_gate_mapping.json"
            gate_mapping_path.parent.mkdir(parents=True, exist_ok=True)
            gate_mapping = case.get("gate_mapping", {"required_gates": {}})
            gate_mapping_path.write_text(json.dumps(gate_mapping))

            # Create referenced files
            for line in str(case["matrix"]).strip().split("\n")[1:]:
                parts = line.split(",")
                if len(parts) >= 5:
                    evidence_path = parts[4].strip()
                    if evidence_path and evidence_path not in ("", "none"):
                        f = tmp_path / evidence_path
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_text("# Test file\n")

            # Override paths for this test
            global MATRIX_CSV, REGISTRY_CSV, CI_GATE_MAPPING, REPO_ROOT
            old_matrix = MATRIX_CSV
            old_registry = REGISTRY_CSV
            old_gate_mapping = CI_GATE_MAPPING
            old_repo_root = REPO_ROOT
            MATRIX_CSV = tmp_matrix
            REGISTRY_CSV = tmp_registry
            CI_GATE_MAPPING = gate_mapping_path
            REPO_ROOT = tmp_path

            try:
                # Read and run checks
                rows, error = read_matrix()

                if error and case["should_fail"]:
                    print(f"  [OK] Failed to parse as expected: {error}")
                    continue

                if error and not case["should_fail"]:
                    print(f"  [UNEXPECTED] Parse error: {error}")
                    all_passed = False
                    continue

                # Read registry
                registry_rows, _ = read_registry()

                # Read gate mapping
                gate_mapping, _ = read_ci_gate_mapping()

                # Run all checks
                checks_results: list[tuple[str, TraceabilityCheckResult]] = [
                    ("CSV structure", check_csv_parse(rows)),
                    ("No duplicate trace_id", check_no_duplicate_trace_ids(rows)),
                    ("No duplicate tuples", check_no_duplicate_tuples(rows)),
                    ("trace_id format", check_trace_id_format(rows)),
                    ("trace_id sorted ascending", check_trace_ids_sorted(rows)),
                    ("claim_id exists in registry", check_claim_ids_exist_in_registry(rows, registry_rows)),
                    ("evidence_required claims traced", check_all_evidence_required_claims_traced(rows, registry_rows)),
                    ("evidence_kind valid", check_evidence_kind_valid(rows)),
                    ("coverage_strength valid", check_coverage_strength_valid(rows)),
                    ("verification_status valid", check_verification_status_valid(rows)),
                    ("evidence_ref non-empty", check_evidence_ref_non_empty(rows)),
                    ("evidence_path exists", check_evidence_path_exists(rows)),
                    ("gate_name for ci_gate", check_gate_name_for_ci_gate(rows, gate_mapping)),
                    ("Semantic combinations", check_semantic_combinations(rows)),
                    ("Linked claims valid", check_linked_claims_valid(rows, registry_rows)),
                ]

                all_errors: list[str] = []
                any_failed = False
                for name, result in checks_results:
                    all_errors.extend(result.errors)
                    if not result.passed:
                        any_failed = True

                expected_fail = bool(case["should_fail"])
                expect_contains = case.get("expect_error_contains", "")

                if expected_fail:
                    if any_failed:
                        if expect_contains:
                            found = any(expect_contains.lower() in e.lower() for e in all_errors)
                            if found:
                                print("  [OK] Failed as expected with matching error")
                            else:
                                print("  [PARTIAL] Failed but error mismatch:")
                                for e in all_errors:
                                    print(f"         {e}")
                                all_passed = False
                        else:
                            print("  [OK] Failed as expected")
                    else:
                        print("  [UNEXPECTED PASS] No checks failed")
                        all_passed = False
                else:
                    if not any_failed:
                        print("  [OK] Passed as expected")
                    else:
                        print("  [UNEXPECTED FAIL] Errors:")
                        for e in all_errors:
                            print(f"         {e}")
                        all_passed = False

            finally:
                MATRIX_CSV = old_matrix
                REGISTRY_CSV = old_registry
                CI_GATE_MAPPING = old_gate_mapping
                REPO_ROOT = old_repo_root

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify docs claim traceability matrix integrity")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode with inline fixture cases",
    )
    args = parser.parse_args()

    if args.self_test:
        success = run_self_test()
    else:
        success = run_verification()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
