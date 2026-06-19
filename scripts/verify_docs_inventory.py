#!/usr/bin/env python
"""Verify docs inventory integrity.

This script checks that:
1. Every in-scope doc exists in the inventory
2. Every inventory path exists (unless explicitly archived/deleted with valid status)
3. doc_class is from the allowed enum
4. truth_status is from the allowed enum
5. Generated docs have generated_by
6. Superseded docs have replacement_doc or a clear note
7. Historical docs are not marked current
8. claim_trace_required is a strict boolean
9. No duplicate doc_path rows
10. CSV parses strictly

Usage:
    python scripts/verify_docs_inventory.py           # verify
    python scripts/verify_docs_inventory.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).parent.parent
INVENTORY_CSV = REPO_ROOT / "docs" / "docs_inventory.csv"

# Scope: docs/**/*.md and root README.md
DOC_SCOPE_PATTERNS = [
    REPO_ROOT / "README.md",
]

# Add all docs/**/*.md files
docs_dir = REPO_ROOT / "docs"
if docs_dir.exists():
    for md_file in docs_dir.rglob("*.md"):
        DOC_SCOPE_PATTERNS.append(md_file)

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


def read_inventory() -> tuple[list[dict[str, str]], str | None]:
    """Read and parse the inventory CSV. Returns (rows, error_msg)."""
    if not INVENTORY_CSV.exists():
        return [], f"Inventory file not found: {INVENTORY_CSV}"

    try:
        with open(INVENTORY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows, None
    except csv.Error as e:
        return [], f"CSV parse error: {e}"
    except Exception as e:
        return [], f"Error reading inventory: {e}"


def get_scope_files() -> set[Path]:
    """Get all files in scope for inventory check."""
    files: set[Path] = set()

    # Root README.md
    readme = REPO_ROOT / "README.md"
    if readme.exists():
        files.add(readme)

    # docs/**/*.md
    docs_dir = REPO_ROOT / "docs"
    if docs_dir.exists():
        for md_file in docs_dir.rglob("*.md"):
            files.add(md_file)

    return files


def check_csv_parse(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that CSV has required columns and parses correctly."""
    result = InventoryCheckResult()

    if not rows:
        result.add_error("Inventory is empty (no data rows)")
        return result

    # Required columns
    required_columns = {
        "doc_path",
        "doc_class",
        "truth_status",
        "owner_area",
        "generated_by",
        "replacement_doc",
        "claim_trace_required",
        "notes",
    }

    actual_columns = set(rows[0].keys())
    missing_columns = required_columns - actual_columns
    if missing_columns:
        result.add_error(f"Missing required columns: {', '.join(sorted(missing_columns))}")

    return result


def check_no_duplicate_paths(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check for duplicate doc_path entries."""
    result = InventoryCheckResult()

    paths = [row.get("doc_path", "").strip() for row in rows]
    seen: dict[str, int] = {}
    for i, path in enumerate(paths):
        if path in seen:
            result.add_error(f"Duplicate doc_path '{path}' at row {i + 2} (first seen at row {seen[path] + 2})")
        else:
            seen[path] = i

    return result


def check_doc_class_valid(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that all doc_class values are from allowed enum."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        doc_class = row.get("doc_class", "").strip()
        if doc_class not in ALLOWED_DOC_CLASS:
            result.add_error(
                f"Row {i + 2}: invalid doc_class '{doc_class}' "
                f"(allowed: {', '.join(sorted(ALLOWED_DOC_CLASS))})"
            )

    return result


def check_truth_status_valid(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that all truth_status values are from allowed enum."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        truth_status = row.get("truth_status", "").strip()
        if truth_status not in ALLOWED_TRUTH_STATUS:
            result.add_error(
                f"Row {i + 2}: invalid truth_status '{truth_status}' "
                f"(allowed: {', '.join(sorted(ALLOWED_TRUTH_STATUS))})"
            )

    return result


def check_generated_docs_have_generator(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that generated docs have generated_by set."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        doc_class = row.get("doc_class", "").strip()
        generated_by = row.get("generated_by", "").strip()

        if doc_class == "generated" and not generated_by:
            result.add_error(
                f"Row {i + 2}: doc_class='generated' but generated_by is empty"
            )

    return result


def check_superseded_docs_have_replacement(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that superseded docs have replacement_doc or clear notes."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        truth_status = (row.get("truth_status") or "").strip()
        replacement_doc = (row.get("replacement_doc") or "").strip()
        notes = (row.get("notes") or "").strip()

        if truth_status == "superseded" and not replacement_doc and not notes:
            result.add_error(
                f"Row {i + 2}: truth_status='superseded' but both replacement_doc and notes are empty"
            )

    return result


def check_historical_not_current(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that historical docs don't have truth_status='current'."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        doc_class = row.get("doc_class", "").strip()
        truth_status = row.get("truth_status", "").strip()

        if doc_class == "historical" and truth_status == "current":
            result.add_error(
                f"Row {i + 2}: doc_class='historical' but truth_status='current' (conflicting)"
            )

    return result


def check_claim_trace_boolean(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that claim_trace_required is a strict boolean."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        claim_trace = row.get("claim_trace_required", "").strip().lower()
        if claim_trace not in BOOLEAN_VALUES:
            result.add_error(
                f"Row {i + 2}: claim_trace_required='{claim_trace}' is not a valid boolean "
                f"(expected: true or false)"
            )

    return result


def check_all_docs_in_inventory(rows: list[dict[str, str]], scope_files: set[Path]) -> InventoryCheckResult:
    """Check that every in-scope doc exists in the inventory."""
    result = InventoryCheckResult()

    # Build set of paths in inventory
    inventory_paths: set[str] = set()
    for row in rows:
        inventory_paths.add(row.get("doc_path", "").strip())

    # Check each scope file
    for file_path in sorted(scope_files):
        # Convert to relative path from repo root
        rel_path = file_path.relative_to(REPO_ROOT)
        rel_path_str = str(rel_path).replace("\\", "/")  # Normalize for Windows

        if rel_path_str not in inventory_paths:
            result.add_error(f"Scope file '{rel_path_str}' is not in inventory")

    return result


def check_inventory_paths_exist(rows: list[dict[str, str]]) -> InventoryCheckResult:
    """Check that every inventory path exists (unless archived/deleted with valid status)."""
    result = InventoryCheckResult()

    for i, row in enumerate(rows):
        doc_path = row.get("doc_path", "").strip()
        truth_status = row.get("truth_status", "").strip()

        if not doc_path:
            result.add_error(f"Row {i + 2}: doc_path is empty")
            continue

        # Check if file exists
        file_path = REPO_ROOT / doc_path

        if not file_path.exists():
            # Allow if archived/deleted status
            if truth_status in ARCHIVED_STATUSES:
                result.add_warning(
                    f"Row {i + 2}: inventory path '{doc_path}' does not exist (status={truth_status}, OK if archived)"
                )
            else:
                result.add_error(
                    f"Row {i + 2}: inventory path '{doc_path}' does not exist "
                    f"(status={truth_status}, expected historical/superseded if intentionally removed)"
                )

    return result


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Docs Inventory Verification ===\n")

    # Read inventory
    rows, error = read_inventory()
    if error:
        print(f"[FAIL] CSV parse: {error}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    print(f"[INFO] Inventory has {len(rows)} rows")

    # Get scope files
    scope_files = get_scope_files()
    print(f"[INFO] Scope includes {len(scope_files)} files\n")

    # Run checks
    checks: list[tuple[str, Callable[[], InventoryCheckResult]]] = [
        ("CSV structure", lambda: check_csv_parse(rows)),
        ("No duplicate paths", lambda: check_no_duplicate_paths(rows)),
        ("Valid doc_class", lambda: check_doc_class_valid(rows)),
        ("Valid truth_status", lambda: check_truth_status_valid(rows)),
        ("Generated docs have generator", lambda: check_generated_docs_have_generator(rows)),
        ("Superseded docs have replacement", lambda: check_superseded_docs_have_replacement(rows)),
        ("Historical not marked current", lambda: check_historical_not_current(rows)),
        ("claim_trace_required is boolean", lambda: check_claim_trace_boolean(rows)),
        ("All scope docs in inventory", lambda: check_all_docs_in_inventory(rows, scope_files)),
        ("Inventory paths exist", lambda: check_inventory_paths_exist(rows)),
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
        "name": "missing inventory row",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,"
            "replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,current,general,,,false,Root README\n"
        ),
        "scope": {"README.md": True, "docs/missing.md": True},
        "should_fail": True,
        "expect_error_contains": "is not in inventory",
    },
    {
        "name": "duplicate doc row",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,current,general,,,false,First\n"
            "README.md,canonical,current,general,,,false,Duplicate\n"
        ),
        "should_fail": True,
        "expect_error_contains": "Duplicate",
    },
    {
        "name": "invalid class",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,bad_class,current,general,,,false,Bad class\n"
        ),
        "should_fail": True,
        "expect_error_contains": "invalid doc_class",
    },
    {
        "name": "invalid status",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,bad_status,general,,,false,Bad status\n"
        ),
        "should_fail": True,
        "expect_error_contains": "invalid truth_status",
    },
    {
        "name": "generated doc without generator",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "docs/generated.md,generated,current,tooling,,,Missing generator\n"
        ),
        "should_fail": True,
        "expect_error_contains": "generated_by is empty",
    },
    {
        "name": "superseded doc without replacement/note",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "docs/old.md,reference,superseded,artifacts,,,\n"
        ),
        "should_fail": True,
        "expect_error_contains": "replacement_doc and notes are empty",
    },
    {
        "name": "invalid boolean",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,current,general,,,maybe,Invalid boolean\n"
        ),
        "should_fail": True,
        "expect_error_contains": "not a valid boolean",
    },
    {
        "name": "historical marked current",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,historical,current,general,,,false,Conflicting\n"
        ),
        "should_fail": True,
        "expect_error_contains": "conflicting",
    },
    {
        "name": "valid inventory passes",
        "inventory": (
            "doc_path,doc_class,truth_status,owner_area,generated_by,replacement_doc,claim_trace_required,notes\n"
            "README.md,canonical,current,general,,,false,Root README\n"
        ),
        "should_fail": False,
    },
]


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== Docs Inventory Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tmp_inventory = tmp_path / "docs" / "docs_inventory.csv"
            tmp_inventory.parent.mkdir(parents=True, exist_ok=True)

            # Write inventory
            tmp_inventory.write_text(str(case["inventory"]))

            # Create all files referenced in inventory
            # Parse inventory to get all referenced paths
            inventory_text = str(case["inventory"])
            referenced_files: set[str] = set()
            for line in inventory_text.strip().split("\n")[1:]:  # Skip header
                parts = line.split(",")
                if parts:
                    doc_path = parts[0].strip()
                    if doc_path:
                        referenced_files.add(doc_path)

            # Create scope files (default includes all referenced files)
            scope_files: set[Path] = set()
            scope_data = case.get("scope", {})
            skip_scope_check = case.get("skip_scope_check", False)
            
            if isinstance(scope_data, dict) and scope_data:
                for rel_path in scope_data:
                    f = tmp_path / rel_path
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text("# Test file\n")
                    scope_files.add(f)
            elif not skip_scope_check:
                # Create all files referenced in inventory
                for rel_path in referenced_files:
                    f = tmp_path / rel_path
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text("# Test file\n")
                    scope_files.add(f)

            # Override paths for this test
            global INVENTORY_CSV, REPO_ROOT
            old_inventory = INVENTORY_CSV
            old_repo_root = REPO_ROOT
            INVENTORY_CSV = tmp_inventory
            REPO_ROOT = tmp_path

            try:
                # Run checks
                rows, error = read_inventory()

                if error and case["should_fail"]:
                    print(f"  [OK] Failed to parse as expected: {error}")
                    continue

                if error and not case["should_fail"]:
                    print(f"  [UNEXPECTED] Parse error: {error}")
                    all_passed = False
                    continue

                # Build checks list based on flags - using direct function calls instead of lambdas to capture current values
                checks_results: list[tuple[str, InventoryCheckResult]] = [
                    ("CSV structure", check_csv_parse(rows)),
                    ("No duplicate paths", check_no_duplicate_paths(rows)),
                    ("Valid doc_class", check_doc_class_valid(rows)),
                    ("Valid truth_status", check_truth_status_valid(rows)),
                    ("Generated docs have generator", check_generated_docs_have_generator(rows)),
                    ("Superseded docs have replacement", check_superseded_docs_have_replacement(rows)),
                    ("Historical not marked current", check_historical_not_current(rows)),
                    ("claim_trace_required is boolean", check_claim_trace_boolean(rows)),
                    ("Inventory paths exist", check_inventory_paths_exist(rows)),
                ]
                
                # Add scope check unless explicitly skipped
                if not skip_scope_check:
                    checks_results.insert(8, ("All scope docs in inventory", check_all_docs_in_inventory(rows, scope_files)))

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
                INVENTORY_CSV = old_inventory
                REPO_ROOT = old_repo_root

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def print_summary() -> None:
    """Print inventory summary statistics."""
    rows, error = read_inventory()
    if error:
        return

    # Count by doc_class
    class_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    trace_required_count = 0

    for row in rows:
        doc_class = row.get("doc_class", "").strip()
        truth_status = row.get("truth_status", "").strip()
        claim_trace = row.get("claim_trace_required", "").strip().lower()

        class_counts[doc_class] = class_counts.get(doc_class, 0) + 1
        status_counts[truth_status] = status_counts.get(truth_status, 0) + 1

        if claim_trace == "true":
            trace_required_count += 1

    print("\n=== Inventory Summary ===")
    print(f"Total docs inventoried: {len(rows)}")
    print("\nBy doc_class:")
    for cls, count in sorted(class_counts.items()):
        print(f"  {cls}: {count}")
    print("\nBy truth_status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    print(f"\nWith claim_trace_required=true: {trace_required_count}")

    # List stale/unknown for follow-up
    stale_or_unknown = [
        row.get("doc_path", "") for row in rows
        if row.get("truth_status", "").strip() in ("stale", "unknown")
    ]
    if stale_or_unknown:
        print(f"\nStale or unknown docs for follow-up ({len(stale_or_unknown)}):")
        for path in stale_or_unknown:
            print(f"  - {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify docs inventory integrity")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode with inline fixture cases",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print inventory summary statistics",
    )
    args = parser.parse_args()

    if args.summary:
        print_summary()
        return 0

    if args.self_test:
        success = run_self_test()
    else:
        success = run_verification()

    # Always print summary in verify mode
    if not args.self_test and success:
        print_summary()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
