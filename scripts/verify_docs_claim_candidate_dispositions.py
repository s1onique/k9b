#!/usr/bin/env python
"""Verify docs claim candidate disposition ledger.

This script checks that:
1. Disposition ledger CSV exists and parses correctly
2. No duplicate candidate IDs in disposition ledger
3. Disposition enum values are valid
4. Reason_code enum values are valid
5. claim_id is set for dispositions that require it
6. covered_by_claim_id is set for dispositions that require it
7. Every generated candidate has exactly one disposition
8. Claim IDs reference existing registry claims
9. Candidate IDs reference existing generated candidates
10. reviewed_at is populated
11. reviewer_notes is populated where required

Usage:
    python scripts/verify_docs_claim_candidate_dispositions.py           # verify
    python scripts/verify_docs_claim_candidate_dispositions.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

# Import candidates loader
from scripts.docs_claim_candidates_shard import read_all_shards
from scripts.docs_claim_disposition_contract import DispositionCheckResult
from scripts.docs_claim_disposition_loader import read_dispositions
from scripts.docs_claim_disposition_rules import (
    check_all_candidates_have_disposition,
    check_claim_id_valid_for_disposition,
    check_covered_by_claim_id_valid,
    check_disposition_csv_exists,
    check_disposition_enum_valid,
    check_disposition_statistics,
    check_high_risk_ignored_has_specific_notes,
    check_no_duplicate_dispositions,
    check_reason_code_enum_valid,
    check_reviewed_at_valid,
    check_reviewer_notes_required,
)
from scripts.docs_claim_disposition_selftest import run_self_test as run_selftest

# Import registry loader for valid claim IDs
from scripts.docs_claims_registry_loader import read_registry


def get_valid_candidate_ids() -> set[str]:
    """Get set of all valid candidate IDs from generated candidates."""
    candidates, _ = read_all_shards()
    return {row.get("candidate_id", "").strip() for row in candidates if row.get("candidate_id", "").strip()}


def get_valid_claim_ids() -> set[str]:
    """Get set of all valid claim IDs from registry."""
    registry, _ = read_registry()
    return {row.get("claim_id", "").strip() for row in registry if row.get("claim_id", "").strip()}


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Docs Claim Candidate Disposition Verification ===\n")

    # Load data
    dispositions, disp_error = read_dispositions()
    if disp_error:
        print(f"[WARNING] Could not read disposition ledger: {disp_error}")
        dispositions = []

    if dispositions:
        print(f"[INFO] Disposition ledger has {len(dispositions)} rows")
    else:
        print("[INFO] No dispositions in ledger")

    # Get valid IDs for cross-reference checks
    valid_candidate_ids = get_valid_candidate_ids()
    valid_claim_ids = get_valid_claim_ids()
    
    # Load candidates for high-risk check
    candidates, _ = read_all_shards()

    print(f"[INFO] Registry has {len(valid_claim_ids)} claims")
    print(f"[INFO] Candidates have {len(valid_candidate_ids)} candidate IDs")

    checks: list[tuple[str, Callable[[], DispositionCheckResult]]] = [
        ("Disposition CSV exists", lambda: check_disposition_csv_exists()),
        ("No duplicate dispositions", lambda: check_no_duplicate_dispositions(dispositions)),
        ("Disposition enum valid", lambda: check_disposition_enum_valid(dispositions)),
        ("Reason code enum valid", lambda: check_reason_code_enum_valid(dispositions)),
        ("Claim ID valid for disposition", lambda: check_claim_id_valid_for_disposition(dispositions, valid_claim_ids)),
        ("Covered-by claim ID valid", lambda: check_covered_by_claim_id_valid(dispositions, valid_claim_ids)),
        ("Candidate ID valid", lambda: check_candidate_id_valid_from_rules(dispositions, valid_candidate_ids)),
        ("Reviewed-at populated", lambda: check_reviewed_at_valid(dispositions)),
        ("Reviewer notes required", lambda: check_reviewer_notes_required(dispositions)),
        ("All candidates have disposition", lambda: check_all_candidates_have_disposition(dispositions, valid_candidate_ids)),
        ("High-risk ignored has specific notes", lambda: check_high_risk_ignored_has_specific_notes(dispositions, candidates)),
        ("Disposition statistics", lambda: check_disposition_statistics(dispositions)),
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


def check_candidate_id_valid_from_rules(
    dispositions: list[dict[str, str]],
    valid_candidate_ids: set[str],
) -> DispositionCheckResult:
    """Check candidate IDs are valid (imported from rules)."""
    from scripts.docs_claim_disposition_rules import check_candidate_id_valid
    return check_candidate_id_valid(dispositions, valid_candidate_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify docs claim candidate dispositions")
    parser.add_argument("--self-test", action="store_true", help="Run self-test mode")
    args = parser.parse_args()

    if args.self_test:
        success = run_selftest()
        return 0 if success else 1

    success = run_verification()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
