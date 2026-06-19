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
19. Semantic combinations (none evidence_kind requires none coverage_strength, etc.)

Usage:
    python scripts/verify_docs_claim_traceability.py           # verify
    python scripts/verify_docs_claim_traceability.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import sys

from docs_claim_traceability_loader import read_matrix, read_registry, read_ci_gate_mapping
from docs_claim_traceability_rules import get_all_checks
from docs_claim_traceability_rules_linked import print_coverage_report
from docs_claim_traceability_selftest import run_self_test as run_selftest


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== Docs Claim Traceability Verification ===\n")

    rows, error = read_matrix()
    if error:
        print(f"[FAIL] CSV parse: {error}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    print(f"[INFO] Matrix has {len(rows)} trace rows")

    registry_rows, reg_error = read_registry()
    if reg_error:
        print(f"[WARNING] Could not read registry: {reg_error}")
        registry_rows = []

    gate_mapping, mapping_error = read_ci_gate_mapping()
    if mapping_error:
        print(f"[WARNING] Could not read CI gate mapping: {mapping_error}")
        gate_mapping = {}

    checks_results = get_all_checks(rows, registry_rows, gate_mapping)

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

    if all_passed:
        print_coverage_report(rows, registry_rows)

    print()
    if all_passed:
        print("VERIFICATION GATE: PASSED")
    else:
        print("VERIFICATION GATE: FAILED")

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
        success = run_selftest()
    else:
        success = run_verification()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())