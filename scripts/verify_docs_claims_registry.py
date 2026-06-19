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
import sys

from docs_claims_registry_loader import read_registry, read_inventory_paths
from docs_claims_registry_rules import get_all_checks
from docs_claims_registry_selftest import run_self_test as run_selftest


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
    checks_results = get_all_checks(rows, inventory_paths)

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
        success = run_selftest()
    else:
        success = run_verification()

    # Always print summary in verify mode
    if not args.self_test and success:
        rows, _ = read_registry()
        print_summary(rows)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())