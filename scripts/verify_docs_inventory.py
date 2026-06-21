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
import sys

from docs_inventory_loader import get_scope_files, read_inventory
from docs_inventory_rules import get_all_checks
from docs_inventory_selftest import run_self_test as run_selftest


def print_summary() -> None:
    """Print inventory summary statistics."""
    rows, error = read_inventory()
    if error:
        return

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

    stale_or_unknown = [
        row.get("doc_path", "") for row in rows
        if row.get("truth_status", "").strip() in ("stale", "unknown")
    ]
    if stale_or_unknown:
        print(f"\nStale or unknown docs for follow-up ({len(stale_or_unknown)}):")
        for path in stale_or_unknown:
            print(f"  - {path}")


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Docs Inventory Verification ===\n")

    rows, error = read_inventory()
    if error:
        print(f"[FAIL] CSV parse: {error}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    print(f"[INFO] Inventory has {len(rows)} rows")

    scope_files = get_scope_files()
    print(f"[INFO] Scope includes {len(scope_files)} files\n")

    checks_results = get_all_checks(rows, scope_files)

    all_passed = True
    for name, result in checks_results:
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
        success = run_selftest()
    else:
        success = run_verification()

    if not args.self_test and success:
        print_summary()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())