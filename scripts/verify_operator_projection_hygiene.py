#!/usr/bin/env python3
"""Operator Projection Sanitization Hygiene Verification Gate.

This script verifies that operator-facing UI/API projection files properly sanitize
execution output and exception messages before returning them to the operator UI.

Scope:
    - src/k8s_diag_agent/ui/api_*.py
    - src/k8s_diag_agent/ui/server_*.py
    - src/k8s_diag_agent/ui/model_*.py
    - src/k8s_diag_agent/ui/*projection*.py
    - src/k8s_diag_agent/ui/*summary*.py
    - src/k8s_diag_agent/ui/*status*.py
    - src/k8s_diag_agent/ui/notifications*.py
    - src/k8s_diag_agent/health/ui_projection/*.py

Forbidden patterns:
    1. str(exc) in response payloads - must use sanitize_exception_message()
    2. exc_info=True in non-logger contexts - traceback leaks to UI
    3. stdout/stderr in response payloads - must be sanitized
    4. artifact.raw_output used directly - must use sanitize_execution_output()
    5. artifact.error_summary used directly - must use sanitize_execution_output()
    6. traceback.format_exc() or format_exception - raw traceback leaks
    7. raw_output/error_summary/error_message field keys without sanitization

Usage:
    python scripts/verify_operator_projection_hygiene.py
    python scripts/verify_operator_projection_hygiene.py --verbose
    python scripts/verify_operator_projection_hygiene.py --sentinel  # self-test

Exit codes:
    0 - All checks passed
    1 - One or more forbidden patterns detected
    2 - Sentinel test failed (self-test mode detected regressions)

See: ACT: Audit remaining operator-facing UI projections for raw diagnostic leaks
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from verify_operator_projection_hygiene_helpers import (
    check_all_files,
    find_operator_projection_files,
    format_violations_report,
    run_sentinel_test,
)
from verify_operator_projection_hygiene_patterns import FORBIDDEN_PATTERNS


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify operator projection sanitization hygiene"
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
    print("Operator Projection Sanitization Hygiene Verification Gate")
    print("=" * 60)
    print()
    
    # Find the repository root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    
    # Find operator projection files
    projection_files = find_operator_projection_files(repo_root)
    
    print(f"[SCOPE] Checking {len(projection_files)} operator projection files:")
    for f in projection_files:
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
    violations_map = check_all_files(projection_files, FORBIDDEN_PATTERNS)
    
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
        print("  1. str(exc) in response payloads - must use sanitize_exception_message()")
        print("  2. exc_info=True in non-logger contexts - traceback leaks to UI")
        print("  3. stdout/stderr in response payloads - must be sanitized")
        print("  4. artifact.raw_output used directly - must use sanitize_execution_output()")
        print("  5. artifact.error_summary used directly - must use sanitize_execution_output()")
        print("  6. traceback.format_exc() or format_exception - raw traceback leaks")
        print("  7. raw_output/error_summary/error_message without sanitization")
        print()
        return 1
    else:
        print()
        print("=" * 60)
        print("VERIFICATION GATE: PASSED")
        print("=" * 60)
        print()
        print("All operator projection files comply with sanitization hygiene:")
        print("  - Exceptions sanitized via sanitize_exception_message()")
        print("  - No exc_info=True in operator-facing response paths")
        print("  - No raw stdout/stderr in response payloads")
        print("  - No artifact.raw_output without sanitize_execution_output()")
        print("  - No artifact.error_summary without sanitize_execution_output()")
        print("  - No raw traceback formatting")
        print("  - No unsanitized raw_output/error_summary/error_message field keys")
        return 0


if __name__ == "__main__":
    sys.exit(main())
