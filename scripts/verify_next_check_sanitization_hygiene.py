#!/usr/bin/env python3
"""Next-Check Projection Sanitization Hygiene Verification Gate.

This script verifies that next-check response paths properly sanitize execution
output and exception messages before returning them to the UI.

Scope:
    - src/k8s_diag_agent/ui/*next_check*.py
    - src/k8s_diag_agent/ui/*server_next_check*.py

Usage:
    python scripts/verify_next_check_sanitization_hygiene.py
    python scripts/verify_next_check_sanitization_hygiene.py --verbose
    python scripts/verify_next_check_sanitization_hygiene.py --sentinel  # self-test

Exit codes:
    0 - All checks passed
    1 - One or more forbidden patterns detected
    2 - Sentinel test failed (self-test mode detected regressions)

See: ACT: Add static hygiene verifier for next-check projection sanitization
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verify_next_check_hygiene_helpers import (
    check_all_files,
    find_next_check_files,
    format_violations_report,
    run_sentinel_test,
)
from verify_next_check_hygiene_patterns import FORBIDDEN_PATTERNS


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify next-check sanitization hygiene"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verbose output including file contents",
    )
    parser.add_argument(
        "--sentinel",
        action="store_true",
        help="Run sentinel self-test to verify the checker works",
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("Next-Check Sanitization Hygiene Verification Gate")
    print("=" * 60)
    print()
    
    # Find the repository root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    
    # Find next-check files
    next_check_files = find_next_check_files(repo_root)
    
    print(f"[SCOPE] Checking {len(next_check_files)} next-check files:")
    for f in next_check_files:
        print(f"         - {f.relative_to(repo_root)}")
    print()
    
    # Run sentinel test first if requested
    if args.sentinel:
        print("[SENTINEL] Running self-test with synthetic violations...")
        sentinel_passed, sentinel_output = run_sentinel_test()
        print(sentinel_output)
        print()
        if not sentinel_passed:
            print("SENTINEL TEST FAILED - Verifier itself is broken")
            return 2
        print("SENTINEL TEST PASSED - Verifier correctly detects violations")
        print()
    
    # Check all files
    print("[CHECK] Scanning for forbidden patterns...")
    violations_map = check_all_files(next_check_files, FORBIDDEN_PATTERNS)
    
    # Report results
    if violations_map:
        print()
        print("FORBIDDEN PATTERNS DETECTED:")
        print("-" * 40)
        
        total_violations, violations_report = format_violations_report(
            violations_map, repo_root
        )
        print(violations_report)
        
        print()
        print("=" * 60)
        print(f"VERIFICATION GATE: FAILED ({total_violations} violation(s))")
        print("=" * 60)
        print()
        print("Forbidden patterns enforced:")
        print("  1. artifact.raw_output - must use sanitize_execution_output()")
        print("  2. artifact.error_summary - must use sanitize_execution_output()")
        print("  3. str(exc) - must use sanitize_exception_message()")
        print("  4. exc_info=True - traceback logging leaks to UI")
        print("  5. stdout/stderr in payloads - must be sanitized")
        print("  6. traceback.format_* - raw traceback leaks sensitive data")
        print()
        return 1
    else:
        print()
        print("=" * 60)
        print("VERIFICATION GATE: PASSED")
        print("=" * 60)
        print()
        print("All next-check files comply with sanitization hygiene:")
        print("  - artifact.raw_output sanitized via sanitize_execution_output()")
        print("  - artifact.error_summary sanitized via sanitize_execution_output()")
        print("  - Exceptions sanitized via sanitize_exception_message()")
        print("  - No exc_info=True in next-check response paths")
        print("  - No raw stdout/stderr in response payloads")
        print("  - No raw traceback formatting")
        return 0


if __name__ == "__main__":
    sys.exit(main())
