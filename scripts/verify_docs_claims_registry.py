#!/usr/bin/env python
"""Verify docs claims registry integrity.

This script checks that:
1. Registry file exists and parses strictly as CSV
2. Required columns are present
3. No duplicate claim_id values
4. No duplicate (doc_path, anchor, claim_text) tuples
5. claim_id matches DOC-CLAIM-0001 pattern
6. Claim IDs are sorted ascending
7. doc_path exists in docs_inventory.csv
8. doc_path exists on disk (unless historical/superseded)
9. anchor is non-empty
10. claim_text is non-empty and reasonably bounded
11. claim_type is from allowed enum
12. claim_status is from allowed enum
13. evidence_required is strict boolean (true/false)
14. evidence_status is from allowed enum
15. freshness_policy is from allowed enum
16. owner_area is non-empty
17. current claims must not have evidence_status=unsupported
18. unsupported claims must not have claim_status=current
19. historical claims must use freshness_policy=historical_only or not_applicable
20. planned claims must not pretend to be implemented evidence
21. evidence_required=false must use evidence_status=not_required
22. evidence_ref must be non-empty if evidence_status=linked or manual_only

Usage:
    python scripts/verify_docs_claims_registry.py           # verify
    python scripts/verify_docs_claims_registry.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

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


def read_registry() -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the registry CSV. Returns (rows, error_msg)."""
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


def read_inventory_paths() -> tuple[set[str], str | None]:
    """Read inventory and return set of doc paths. Returns (paths, error_msg)."""
    if not INVENTORY_CSV.exists():
        return set(), f"Inventory file not found: {INVENTORY_CSV}"

    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            paths = {row.get("doc_path", "").strip() for row in reader}
            return paths, None
    except csv.Error as e:
        return set(), f"Inventory CSV parse error: {e}"
    except Exception as e:
        return set(), f"Error reading inventory: {e}"


def get_inventory_status(doc_path: str) -> str | None:
    """Get truth_status for a doc_path from inventory."""
    if not INVENTORY_CSV.exists():
        return None
    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("doc_path", "").strip() == doc_path:
                    return row.get("truth_status", "").strip()
        return None
    except Exception:
        return None


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
]


def check_csv_parse(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that CSV has required columns in exact order, no duplicates."""
    result = RegistryCheckResult()

    if not rows:
        result.add_error("Registry is empty (no data rows)")
        return result

    # Read raw header for strict validation
    header, error = read_csv_header(REGISTRY_CSV)
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


def check_no_duplicate_ids(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check for duplicate claim_id values."""
    result = RegistryCheckResult()

    ids = [row.get("claim_id", "").strip() for row in rows]
    seen: dict[str, int] = {}
    for i, claim_id in enumerate(ids):
        if claim_id in seen:
            result.add_error(
                f"Duplicate claim_id '{claim_id}' at row {i + 2} "
                f"(first seen at row {seen[claim_id] + 2})"
            )
        else:
            seen[claim_id] = i

    return result


def check_no_duplicate_tuples(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check for duplicate (doc_path, anchor, claim_text) tuples."""
    result = RegistryCheckResult()

    seen: dict[str, int] = {}
    for i, row in enumerate(rows):
        doc_path = row.get("doc_path", "").strip()
        anchor = row.get("anchor", "").strip()
        claim_text = row.get("claim_text", "").strip()

        key_str = f"{doc_path}|{anchor}|{claim_text}"

        if key_str in seen:
            result.add_error(
                f"Duplicate (doc_path, anchor, claim_text) tuple at row {i + 2} "
                f"(first seen at row {seen[key_str] + 2})"
            )
        else:
            seen[key_str] = i

    return result


def check_claim_id_format(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim_id matches DOC-CLAIM-0001 pattern."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_id = row.get("claim_id", "").strip()
        if not claim_id:
            result.add_error(f"Row {i + 2}: claim_id is empty")
            continue

        if not CLAIM_ID_PATTERN.match(claim_id):
            result.add_error(
                f"Row {i + 2}: claim_id '{claim_id}' does not match pattern DOC-CLAIM-0001 "
                f"(expected: prefix DOC-CLAIM-, 4-digit zero-padded suffix)"
            )

    return result


def check_claim_ids_sorted(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim IDs are sorted ascending."""
    result = RegistryCheckResult()

    ids = [row.get("claim_id", "").strip() for row in rows]
    sorted_ids = sorted(ids)

    if ids != sorted_ids:
        result.add_error(
            f"Claim IDs are not sorted ascending. "
            f"Current order: {', '.join(ids[:5])}{'...' if len(ids) > 5 else ''}"
        )

    return result


def check_doc_paths_in_inventory(rows: list[dict[str, str]], inventory_paths: set[str]) -> RegistryCheckResult:
    """Check that all doc_path values exist in the docs inventory."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        doc_path = row.get("doc_path", "").strip()
        if not doc_path:
            result.add_error(f"Row {i + 2}: doc_path is empty")
            continue

        if doc_path not in inventory_paths:
            result.add_error(
                f"Row {i + 2}: doc_path '{doc_path}' is not in docs_inventory.csv"
            )

    return result


def check_doc_paths_exist(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that all doc_path values exist on disk (unless historical/superseded)."""
    result = RegistryCheckResult()

    # Valid archived/deleted statuses that exempt existence check
    ARCHIVED_STATUSES = {"historical", "superseded"}

    for i, row in enumerate(rows):
        doc_path = row.get("doc_path", "").strip()
        claim_status = row.get("claim_status", "").strip()
        inventory_status = get_inventory_status(doc_path)

        if not doc_path:
            continue

        file_path = REPO_ROOT / doc_path

        if not file_path.exists():
            # Allow if archived/deleted status
            effective_status = inventory_status or claim_status
            if effective_status in ARCHIVED_STATUSES:
                result.add_warning(
                    f"Row {i + 2}: doc_path '{doc_path}' does not exist "
                    f"(status={effective_status}, OK if archived)"
                )
            else:
                result.add_error(
                    f"Row {i + 2}: doc_path '{doc_path}' does not exist "
                    f"(status={effective_status}, expected historical/superseded if intentionally removed)"
                )

    return result


def check_anchor_non_empty(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that anchor is non-empty."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        anchor = row.get("anchor", "").strip()
        if not anchor:
            result.add_error(f"Row {i + 2}: anchor is empty")

    return result


def check_claim_text_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim_text is non-empty and reasonably bounded."""
    result = RegistryCheckResult()
    MIN_LENGTH = 10
    MAX_LENGTH = 2000

    for i, row in enumerate(rows):
        claim_text = row.get("claim_text", "").strip()
        if not claim_text:
            result.add_error(f"Row {i + 2}: claim_text is empty")
            continue

        if len(claim_text) < MIN_LENGTH:
            result.add_error(
                f"Row {i + 2}: claim_text is too short ({len(claim_text)} chars, "
                f"minimum {MIN_LENGTH})"
            )

        if len(claim_text) > MAX_LENGTH:
            result.add_warning(
                f"Row {i + 2}: claim_text is very long ({len(claim_text)} chars, "
                f"consider splitting)"
            )

    return result


def check_claim_type_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim_type is from allowed enum."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_type = row.get("claim_type", "").strip()
        if claim_type not in ALLOWED_CLAIM_TYPE:
            result.add_error(
                f"Row {i + 2}: invalid claim_type '{claim_type}' "
                f"(allowed: {', '.join(sorted(ALLOWED_CLAIM_TYPE))})"
            )

    return result


def check_claim_status_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that claim_status is from allowed enum."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        if claim_status not in ALLOWED_CLAIM_STATUS:
            result.add_error(
                f"Row {i + 2}: invalid claim_status '{claim_status}' "
                f"(allowed: {', '.join(sorted(ALLOWED_CLAIM_STATUS))})"
            )

    return result


def check_evidence_required_boolean(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that evidence_required is a strict boolean."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        evidence_required = row.get("evidence_required", "").strip().lower()
        if evidence_required not in BOOLEAN_VALUES:
            result.add_error(
                f"Row {i + 2}: evidence_required='{evidence_required}' is not a valid boolean "
                f"(expected: true or false)"
            )

    return result


def check_evidence_status_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that evidence_status is from allowed enum."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        evidence_status = row.get("evidence_status", "").strip()
        if evidence_status not in ALLOWED_EVIDENCE_STATUS:
            result.add_error(
                f"Row {i + 2}: invalid evidence_status '{evidence_status}' "
                f"(allowed: {', '.join(sorted(ALLOWED_EVIDENCE_STATUS))})"
            )

    return result


def check_freshness_policy_valid(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that freshness_policy is from allowed enum."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        freshness_policy = row.get("freshness_policy", "").strip()
        if freshness_policy not in ALLOWED_FRESHNESS_POLICY:
            result.add_error(
                f"Row {i + 2}: invalid freshness_policy '{freshness_policy}' "
                f"(allowed: {', '.join(sorted(ALLOWED_FRESHNESS_POLICY))})"
            )

    return result


def check_owner_area_non_empty(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that owner_area is non-empty."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        owner_area = row.get("owner_area", "").strip()
        if not owner_area:
            result.add_error(f"Row {i + 2}: owner_area is empty")

    return result


def check_current_claims_not_unsupported(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that current claims do not have evidence_status=unsupported."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()

        if claim_status == "current" and evidence_status == "unsupported":
            result.add_error(
                f"Row {i + 2}: claim_status='current' but evidence_status='unsupported' "
                f"(current claims must have supported evidence)"
            )

    return result


def check_unsupported_claims_not_current(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that unsupported claims do not have claim_status=current."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()

        if evidence_status == "unsupported" and claim_status == "current":
            result.add_error(
                f"Row {i + 2}: evidence_status='unsupported' but claim_status='current' "
                f"(unsupported evidence cannot back current claims)"
            )

    return result


def check_historical_freshness_policy(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that historical claims use historical_only or not_applicable freshness_policy."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        freshness_policy = row.get("freshness_policy", "").strip()

        if claim_status == "historical":
            if freshness_policy not in {"historical_only", "not_applicable"}:
                result.add_error(
                    f"Row {i + 2}: claim_status='historical' but freshness_policy='{freshness_policy}' "
                    f"(expected: historical_only or not_applicable)"
                )

    return result


def check_planned_claims_evidence(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that planned claims use appropriate evidence_status."""
    result = RegistryCheckResult()
    VALID_FOR_PLANNED = {"pending", "manual_only", "not_required"}

    for i, row in enumerate(rows):
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()

        if claim_status == "planned":
            if evidence_status not in VALID_FOR_PLANNED:
                result.add_error(
                    f"Row {i + 2}: claim_status='planned' but evidence_status='{evidence_status}' "
                    f"(planned claims should use: {', '.join(sorted(VALID_FOR_PLANNED))})"
                )

    return result


def check_evidence_required_false(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that evidence_required=false uses evidence_status=not_required."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        evidence_required = row.get("evidence_required", "").strip().lower()
        evidence_status = row.get("evidence_status", "").strip()

        if evidence_required == "false" and evidence_status != "not_required":
            result.add_error(
                f"Row {i + 2}: evidence_required=false but evidence_status='{evidence_status}' "
                f"(expected: not_required)"
            )

    return result


def check_evidence_ref_for_linked(rows: list[dict[str, str]]) -> RegistryCheckResult:
    """Check that evidence_ref is non-empty if evidence_status is linked or manual_only."""
    result = RegistryCheckResult()

    for i, row in enumerate(rows):
        evidence_status = row.get("evidence_status", "").strip()
        evidence_ref = row.get("evidence_ref", "").strip()

        if evidence_status in {"linked", "manual_only"} and not evidence_ref:
            result.add_error(
                f"Row {i + 2}: evidence_status='{evidence_status}' but evidence_ref is empty "
                f"(evidence_ref required for linked/manual_only evidence)"
            )

    return result


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Docs Claims Registry Verification ===\n")

    # Read registry
    rows, error = read_registry()
    if error:
        print(f"[FAIL] CSV parse: {error}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    print(f"[INFO] Registry has {len(rows)} claims")

    # Read inventory paths
    inventory_paths, inv_error = read_inventory_paths()
    if inv_error:
        print(f"[WARNING] Could not read inventory: {inv_error}")
        inventory_paths = set()

    # Run checks
    checks: list[tuple[str, Callable[[], RegistryCheckResult]]] = [
        ("CSV structure", lambda: check_csv_parse(rows)),
        ("No duplicate claim_id", lambda: check_no_duplicate_ids(rows)),
        ("No duplicate tuples", lambda: check_no_duplicate_tuples(rows)),
        ("claim_id format", lambda: check_claim_id_format(rows)),
        ("claim_id sorted ascending", lambda: check_claim_ids_sorted(rows)),
        ("doc_path in inventory", lambda: check_doc_paths_in_inventory(rows, inventory_paths)),
        ("doc_path exists", lambda: check_doc_paths_exist(rows)),
        ("anchor non-empty", lambda: check_anchor_non_empty(rows)),
        ("claim_text valid", lambda: check_claim_text_valid(rows)),
        ("claim_type valid", lambda: check_claim_type_valid(rows)),
        ("claim_status valid", lambda: check_claim_status_valid(rows)),
        ("evidence_required boolean", lambda: check_evidence_required_boolean(rows)),
        ("evidence_status valid", lambda: check_evidence_status_valid(rows)),
        ("freshness_policy valid", lambda: check_freshness_policy_valid(rows)),
        ("owner_area non-empty", lambda: check_owner_area_non_empty(rows)),
        ("current claims not unsupported", lambda: check_current_claims_not_unsupported(rows)),
        ("unsupported claims not current", lambda: check_unsupported_claims_not_current(rows)),
        ("historical freshness policy", lambda: check_historical_freshness_policy(rows)),
        ("planned claims evidence", lambda: check_planned_claims_evidence(rows)),
        ("evidence_required=false", lambda: check_evidence_required_false(rows)),
        ("evidence_ref for linked", lambda: check_evidence_ref_for_linked(rows)),
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

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")

    return all_passed


# Self-test fixtures
SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "valid minimal registry passes",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,This is a test claim with enough length.,"
            "behavior,current,test,true,pending,,on_change,Test claim\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": False,
    },
    {
        "name": "duplicate claim ID fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,First claim with enough text here.,"
            "behavior,current,test,true,pending,,on_change,First\n"
            "DOC-CLAIM-0001,README.md,test-anchor-2,Second claim with enough text here.,"
            "behavior,current,test,true,pending,,on_change,Duplicate ID\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "Duplicate claim_id",
    },
    {
        "name": "malformed claim ID fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-1,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,pending,,on_change,Bad ID\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "does not match pattern",
    },
    {
        "name": "unsorted claim IDs fail",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0002,README.md,test-anchor-2,Second claim with enough text here.,"
            "behavior,current,test,true,pending,,on_change,Second\n"
            "DOC-CLAIM-0001,README.md,test-anchor-1,First claim with enough text here.,"
            "behavior,current,test,true,pending,,on_change,First\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "not sorted ascending",
    },
    {
        "name": "unknown doc path fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,docs/unknown.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,pending,,on_change,Unknown doc\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "not in docs_inventory",
    },
    {
        "name": "invalid claim_type fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "invalid_type,current,test,true,pending,,on_change,Bad type\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "invalid claim_type",
    },
    {
        "name": "invalid claim_status fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,invalid_status,test,true,pending,,on_change,Bad status\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "invalid claim_status",
    },
    {
        "name": "invalid boolean fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,maybe,pending,,on_change,Bad bool\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "not a valid boolean",
    },
    {
        "name": "current claim with unsupported evidence fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,unsupported,,on_change,Unsupported\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "current claims must have supported evidence",
    },
    {
        "name": "unsupported current claim combination fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,unsupported,,on_change,Combo fail\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "unsupported evidence cannot back current claims",
    },
    {
        "name": "historical claim with wrong freshness policy fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,historical,test,false,not_required,,per_release,Wrong freshness\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "historical_only or not_applicable",
    },
    {
        "name": "linked evidence without evidence_ref fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,true,linked,,on_change,Missing ref\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "evidence_ref required for linked",
    },
    {
        "name": "evidence_required=false with non-not_required status fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Claim text with enough length.,"
            "behavior,current,test,false,pending,,on_change,Bad combo\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "expected: not_required",
    },
    {
        "name": "duplicate (doc_path, anchor, claim_text) fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,test-anchor,Same claim text here.,"
            "behavior,current,test,true,pending,,on_change,First\n"
            "DOC-CLAIM-0002,README.md,test-anchor,Same claim text here.,"
            "behavior,current,test,true,pending,,on_change,Duplicate\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "Duplicate",
    },
    {
        "name": "empty anchor fails",
        "registry": (
            "claim_id,doc_path,anchor,claim_text,claim_type,claim_status,owner_area,"
            "evidence_required,evidence_status,evidence_ref,freshness_policy,notes\n"
            "DOC-CLAIM-0001,README.md,,Claim text with enough length.,"
            "behavior,current,test,true,pending,,on_change,No anchor\n"
        ),
        "inventory": "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\nREADME.md,canonical,current,test,,,false,Test\n",
        "should_fail": True,
        "expect_error_contains": "anchor is empty",
    },
]


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Docs Claims Registry Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_registry = tmp_path / "docs" / "claims" / "docs_claims_registry.csv"
            tmp_registry.parent.mkdir(parents=True, exist_ok=True)

            tmp_inventory = tmp_path / "docs" / "docs_inventory.csv"
            tmp_inventory.parent.mkdir(parents=True, exist_ok=True)

            # Write registry
            tmp_registry.write_text(str(case["registry"]))

            # Write inventory
            tmp_inventory.write_text(str(case["inventory"]))

            # Create all referenced files
            registry_text = str(case["registry"])
            inventory_text = str(case["inventory"])

            # Parse paths from inventory
            for line in inventory_text.strip().split("\n")[1:]:
                parts = line.split(",")
                if parts:
                    doc_path = parts[0].strip()
                    if doc_path:
                        f = tmp_path / doc_path
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_text("# Test file\n")

            # Parse paths from registry
            for line in registry_text.strip().split("\n")[1:]:
                parts = line.split(",")
                if parts:
                    doc_path = parts[1].strip()
                    if doc_path:
                        f = tmp_path / doc_path
                        f.parent.mkdir(parents=True, exist_ok=True)
                        f.write_text("# Test file\n")

            # Override paths for this test
            global REGISTRY_CSV, INVENTORY_CSV, REPO_ROOT
            old_registry = REGISTRY_CSV
            old_inventory = INVENTORY_CSV
            old_repo_root = REPO_ROOT
            REGISTRY_CSV = tmp_registry
            INVENTORY_CSV = tmp_inventory
            REPO_ROOT = tmp_path

            try:
                # Read and run checks
                rows, error = read_registry()

                if error and case["should_fail"]:
                    print(f"  [OK] Failed to parse as expected: {error}")
                    continue

                if error and not case["should_fail"]:
                    print(f"  [UNEXPECTED] Parse error: {error}")
                    all_passed = False
                    continue

                # Read inventory paths
                inventory_paths, _ = read_inventory_paths()

                # Run all checks
                checks_results: list[tuple[str, RegistryCheckResult]] = [
                    ("CSV structure", check_csv_parse(rows)),
                    ("No duplicate claim_id", check_no_duplicate_ids(rows)),
                    ("No duplicate tuples", check_no_duplicate_tuples(rows)),
                    ("claim_id format", check_claim_id_format(rows)),
                    ("claim_id sorted ascending", check_claim_ids_sorted(rows)),
                    ("doc_path in inventory", check_doc_paths_in_inventory(rows, inventory_paths)),
                    ("doc_path exists", check_doc_paths_exist(rows)),
                    ("anchor non-empty", check_anchor_non_empty(rows)),
                    ("claim_text valid", check_claim_text_valid(rows)),
                    ("claim_type valid", check_claim_type_valid(rows)),
                    ("claim_status valid", check_claim_status_valid(rows)),
                    ("evidence_required boolean", check_evidence_required_boolean(rows)),
                    ("evidence_status valid", check_evidence_status_valid(rows)),
                    ("freshness_policy valid", check_freshness_policy_valid(rows)),
                    ("owner_area non-empty", check_owner_area_non_empty(rows)),
                    ("current claims not unsupported", check_current_claims_not_unsupported(rows)),
                    ("unsupported claims not current", check_unsupported_claims_not_current(rows)),
                    ("historical freshness policy", check_historical_freshness_policy(rows)),
                    ("planned claims evidence", check_planned_claims_evidence(rows)),
                    ("evidence_required=false", check_evidence_required_false(rows)),
                    ("evidence_ref for linked", check_evidence_ref_for_linked(rows)),
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
                REGISTRY_CSV = old_registry
                INVENTORY_CSV = old_inventory
                REPO_ROOT = old_repo_root

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def print_summary(rows: list[dict[str, str]]) -> None:
    """Print registry summary statistics."""
    if not rows:
        return

    # Count by claim_type
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    evidence_status_counts: dict[str, int] = {}
    freshness_counts: dict[str, int] = {}
    evidence_required_count = 0
    current_pending_count = 0
    stale_unsupported_count = 0

    # Track docs by claim count
    doc_claim_counts: dict[str, int] = {}

    for row in rows:
        claim_type = row.get("claim_type", "").strip()
        claim_status = row.get("claim_status", "").strip()
        evidence_status = row.get("evidence_status", "").strip()
        freshness_policy = row.get("freshness_policy", "").strip()
        evidence_required = row.get("evidence_required", "").strip().lower()
        doc_path = row.get("doc_path", "").strip()

        type_counts[claim_type] = type_counts.get(claim_type, 0) + 1
        status_counts[claim_status] = status_counts.get(claim_status, 0) + 1
        evidence_status_counts[evidence_status] = evidence_status_counts.get(evidence_status, 0) + 1
        freshness_counts[freshness_policy] = freshness_counts.get(freshness_policy, 0) + 1

        if evidence_required == "true":
            evidence_required_count += 1

        if claim_status == "current" and evidence_status == "pending":
            current_pending_count += 1

        if claim_status in {"stale", "unsupported"}:
            stale_unsupported_count += 1

        doc_claim_counts[doc_path] = doc_claim_counts.get(doc_path, 0) + 1

    print("\n=== Registry Summary ===")
    print(f"Total claims registered: {len(rows)}")

    print("\nBy claim_type:")
    for ct, count in sorted(type_counts.items()):
        print(f"  {ct}: {count}")

    print("\nBy claim_status:")
    for cs, count in sorted(status_counts.items()):
        print(f"  {cs}: {count}")

    print("\nBy evidence_status:")
    for es, count in sorted(evidence_status_counts.items()):
        print(f"  {es}: {count}")

    print("\nBy freshness_policy:")
    for fp, count in sorted(freshness_counts.items()):
        print(f"  {fp}: {count}")

    print(f"\nClaims with evidence_required=true: {evidence_required_count}")
    print(f"Current claims with pending evidence: {current_pending_count}")
    print(f"Stale/unsupported claims: {stale_unsupported_count}")

    print("\nTop docs by claim count:")
    sorted_docs = sorted(doc_claim_counts.items(), key=lambda x: x[1], reverse=True)
    for doc, count in sorted_docs[:10]:
        print(f"  {doc}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify docs claims registry integrity")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode with inline fixture cases",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print registry summary statistics",
    )
    args = parser.parse_args()

    if args.summary:
        rows, error = read_registry()
        if error:
            print(f"Error reading registry: {error}")
            return 1
        print_summary(rows)
        return 0

    if args.self_test:
        success = run_self_test()
    else:
        success = run_verification()

    # Always print summary in verify mode
    if not args.self_test and success:
        rows, _ = read_registry()
        print_summary(rows)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())