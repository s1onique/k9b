#!/usr/bin/env python
"""Verify docs claim candidate coverage.

This script checks that:
1. Generated candidate output exists and parses correctly
2. No duplicate candidate IDs
3. Registration status values are valid
4. Severity values are valid
5. High-severity unregistered current claims with trace_required=true fail
6. High-severity unregistered current claims without trace_required warn but don't fail
7. Stale/historical candidates are reported separately without failing

Usage:
    python scripts/verify_docs_claim_candidate_coverage.py           # verify
    python scripts/verify_docs_claim_candidate_coverage.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from scripts.docs_claim_candidate_coverage_contract import CoverageCheckResult
from scripts.docs_claim_candidate_coverage_loader import load_candidates
from scripts.docs_claim_candidate_coverage_rules import (
    check_candidates_registered,
    check_generated_csv_exists,
    check_high_severity_unregistered_current_not_required,
    check_high_severity_unregistered_current_trace_required,
    check_no_duplicate_candidate_ids,
    check_registration_status_valid,
    check_severity_valid,
    check_stale_historical_candidates,
)
from scripts.docs_claim_candidate_coverage_selftest import run_self_test as run_selftest


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Docs Claim Candidate Coverage Verification ===\n")

    candidates, error = load_candidates()
    if error:
        print(f"[WARNING] Could not read generated CSV: {error}")
        print("[INFO] Run 'python scripts/scan_docs_claim_candidates.py --update' first")
        candidates = []

    if candidates:
        print(f"[INFO] Generated CSV has {len(candidates)} candidates")
    else:
        print("[INFO] No candidates in generated CSV")

    checks: list[tuple[str, Callable[[], CoverageCheckResult]]] = [
        ("Generated CSV exists", lambda: check_generated_csv_exists(candidates)),
        ("No duplicate candidate IDs", lambda: check_no_duplicate_candidate_ids(candidates)),
        ("Registration status valid", lambda: check_registration_status_valid(candidates)),
        ("Severity valid", lambda: check_severity_valid(candidates)),
        ("High-severity unregistered trace-required blocked",
         lambda: check_high_severity_unregistered_current_trace_required(candidates)),
        ("High-severity unregistered not-required warned",
         lambda: check_high_severity_unregistered_current_not_required(candidates)),
        ("Stale/historical candidates reported",
         lambda: check_stale_historical_candidates(candidates)),
        ("Registration statistics", lambda: check_candidates_registered(candidates)),
    ]

    all_passed = True
    for name, check_fn in checks:
        result = check_fn()
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {name}")
        for error_msg in result.errors:
            print(f"      ERROR: {error_msg}")
        for warning in result.warnings:
            print(f"      WARNING: {warning}")
        for info_msg in result.info:
            print(f"      INFO: {info_msg}")
        if not result.passed:
            all_passed = False

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")

    return all_passed


def print_summary(candidates: list[dict[str, str]]) -> None:
    """Print coverage summary statistics."""
    if not candidates:
        return

    reg_counts: dict[str, int] = {}
    for c in candidates:
        status = c.get("registration_status", "")
        reg_counts[status] = reg_counts.get(status, 0) + 1

    sev_counts: dict[str, int] = {}
    for c in candidates:
        sev = c.get("candidate_severity", "")
        sev_counts[sev] = sev_counts.get(sev, 0) + 1

    status_counts: dict[str, int] = {}
    for c in candidates:
        status = c.get("truth_status", "")
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\n=== Candidate Coverage Summary ===")
    print(f"Total candidates: {len(candidates)}")
    print("\nBy registration status:")
    for status, count in sorted(reg_counts.items()):
        print(f"  {status}: {count}")
    print("\nBy severity:")
    for sev, count in sorted(sev_counts.items()):
        print(f"  {sev}: {count}")
    print("\nBy truth_status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify docs claim candidate coverage")
    parser.add_argument("--self-test", action="store_true", help="Run self-test mode")
    parser.add_argument("--summary", action="store_true", help="Print coverage summary statistics")
    args = parser.parse_args()

    if args.summary:
        candidates, _ = load_candidates()
        print_summary(candidates)
        return 0

    if args.self_test:
        success = run_selftest()
        return 0 if success else 1

    success = run_verification()

    if success:
        candidates, _ = load_candidates()
        print_summary(candidates)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
