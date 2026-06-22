#!/usr/bin/env python3
"""Verify no new LLM-friendly allowlist entries and modified allowlisted files.

This script enforces the policy:
1. The LLM-friendly allowlist is a debt ledger - no new entries allowed.
2. No baseline additions in normal transactions.
3. If an already-allowlisted file is modified, it must be removed from the
   active allowlist in the same transaction.
4. .llm-friendly-ignore entries cannot escape the repo.

Usage:
    python scripts/verify_no_new_llm_allowlist.py           # local mode
    python scripts/verify_no_new_llm_allowlist.py -v        # verbose
    python scripts/verify_no_new_llm_allowlist.py --ci       # CI mode
    python scripts/verify_no_new_llm_allowlist.py --fixture fixtures/changed.json  # fixture mode
    python scripts/verify_no_new_llm_allowlist.py --self-test  # self-tests

Exit codes:
    0 - All checks pass
    1 - Check failed
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from llm_allowlist_policy.changed_files import get_changed_files
from llm_allowlist_policy.verify import run_verification


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify no new LLM-friendly allowlist entries and modified files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run verification (local mode)
    python scripts/verify_no_new_llm_allowlist.py

    # Run with verbose output
    python scripts/verify_no_new_llm_allowlist.py -v

    # Run in CI mode
    python scripts/verify_no_new_llm_allowlist.py --ci

    # Run with fixture
    python scripts/verify_no_new_llm_allowlist.py --fixture fixtures/changed.json

    # Run self-tests
    python scripts/verify_no_new_llm_allowlist.py --self-test
        """,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    parser.add_argument("--ci", action="store_true", help="Use CI mode for changed files")
    parser.add_argument(
        "--fixture",
        type=Path,
        help="Path to fixture file with changed files (JSON format: {\"changed\": [...]})",
    )
    parser.add_argument(
        "--base-ref",
        help="Base git ref (for CI mode)",
    )
    parser.add_argument(
        "--head-ref",
        help="Head git ref (for CI mode)",
    )
    parser.add_argument(
        "--bootstrap-baseline",
        action="store_true",
        help="Bootstrap mode: allow baseline additions for initial introduction only. "
             "Not for use in normal verification profiles.",
    )

    args = parser.parse_args()

    if args.self_test:
        # Run all self-tests: basic, error-condition, hardening, and base_ref threading
        from llm_allowlist_policy.test_basic import run_self_test as run_basic_test
        from llm_allowlist_policy.test_helpers import run_base_ref_threading_tests, run_hardening_self_tests, run_self_test_with_errors
        success1, errors1 = run_basic_test()
        success2, errors2 = run_self_test_with_errors()
        success3, errors3 = run_hardening_self_tests()
        success4, errors4 = run_base_ref_threading_tests()
        success = success1 and success2 and success3 and success4
        errors = errors1 + errors2 + errors3 + errors4
        return 0 if success else 1

    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent

    if args.ci:
        mode = "ci"
        base_ref = args.base_ref
        head_ref = args.head_ref
        fixture_path = None
    elif args.fixture:
        mode = "fixture"
        base_ref = None
        head_ref = None
        fixture_path = args.fixture
    else:
        mode = "local"
        base_ref = None
        head_ref = None
        fixture_path = None

    changed_files, resolved_base_ref, changed_errors = get_changed_files(
        repo_root,
        mode=mode,
        base_ref=base_ref,
        head_ref=head_ref,
        fixture_path=fixture_path,
    )

    # For bootstrap mode, skip baseline growth check
    skip_growth_check = args.bootstrap_baseline
    if skip_growth_check and args.verbose:
        print("Bootstrap mode: skipping baseline growth check")

    success, errors, warnings = run_verification(
        repo_root,
        changed_files=changed_files,
        old_baseline_paths=None,  # Always fetch from HEAD, growth check is controlled by flag
        verbose=args.verbose,
        skip_baseline_growth_check=skip_growth_check,
        base_ref=resolved_base_ref or "HEAD",  # Use resolved base_ref for comment classification
    )

    # CRITICAL: Fail closed on changed-file discovery errors
    errors.extend(changed_errors)
    success = success and not changed_errors

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  {w}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e}")
        if changed_errors:
            print("\nFAILURE: Changed-file discovery failed (fail-closed).")
        else:
            print("\nFAILURE: Allowlist policy violations detected.")
            print("Policy: The LLM-friendly allowlist is a debt ledger.")
            print("        New entries are regressions.")
            print("        Modified allowlisted files must be removed from allowlist.")
            print("        Baseline growth requires a separate policy change.")
        return 1

    print("\nPASS: No allowlist policy violations detected.")
    print("Baseline: docs/tooling/llm_large_file_allowlist_baseline.csv")
    print("Policy: docs/doctrine/no-new-llm-large-file-allowlist.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
