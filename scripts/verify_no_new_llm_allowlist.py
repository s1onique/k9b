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
import tempfile
from pathlib import Path

from llm_allowlist_policy.changed_files import ChangedFile, get_changed_files
from llm_allowlist_policy.verify import run_verification


def run_self_test_with_errors() -> tuple[bool, list[str]]:
    """Run self-tests for error conditions including changed-file discovery errors.

    Returns:
        (success, error_messages)
    """
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        (repo_root / "docs" / "tooling").mkdir(parents=True)
        (repo_root / "scripts").mkdir(parents=True)

        # Test 13: Changed-file discovery errors fail closed (CLI behavior)
        print("\nTest 13: Changed-file discovery errors fail closed => FAIL")
        baseline_csv = repo_root / "docs" / "tooling" / "llm_large_file_allowlist_baseline.csv"
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        # Use fixture mode with a non-existent fixture - should fail
        fixture_path = tmp_path / "nonexistent.json"
        changed_files, changed_errors = get_changed_files(
            repo_root,
            mode="fixture",
            fixture_path=fixture_path,
        )

        # The changed_errors should contain the "not found" error
        if changed_errors and any("not found" in e for e in changed_errors):
            print("  PASS: Changed-file discovery errors correctly collected")
        else:
            errors.append(f"Test 13 FAILED: Changed-file discovery errors should be collected, got: {changed_errors}")

        # Test 14: CSV overflow (too many columns) fails
        print("\nTest 14: CSV overflow (too many columns) => FAIL")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            # Extra column after expected columns
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None,EXTRA\n")

        from llm_allowlist_policy.baseline import parse_baseline_csv
        entries, parse_errors = parse_baseline_csv(baseline_csv)

        if parse_errors and any("too many columns" in e or "overflow" in e for e in parse_errors):
            print("  PASS: CSV overflow correctly detected")
        else:
            errors.append(f"Test 14 FAILED: CSV overflow should be detected, got: {parse_errors}")

    print("\n" + "=" * 50)
    if errors:
        print(f"Self-tests (errors) FAILED ({len(errors)} errors):")
        for err in errors:
            print(f"  - {err}")
        return False, errors
    else:
        print("All error self-tests PASSED")
        return True, []


def run_self_test() -> tuple[bool, list[str]]:
    """Run self-tests to verify the verifier itself.

    Returns:
        (success, error_messages)
    """
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        (repo_root / "docs" / "tooling").mkdir(parents=True)
        (repo_root / "scripts").mkdir(parents=True)

        print("Running self-tests...")

        # Test 1: Clean baseline passes
        print("\nTest 1: Clean baseline (no current entries) passes")
        baseline_csv = repo_root / "docs" / "tooling" / "llm_large_file_allowlist_baseline.csv"
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        allowlist_py = repo_root / "scripts" / "llm_friendly_allowlist.py"
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = []\n")

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if success:
            print("  PASS: Clean baseline passes")
        else:
            errors.append(f"Test 1 FAILED: Clean baseline should pass, got: {test_errors}")

        # Test 2: Adding new entry fails
        print("\nTest 2: Adding new allowlist entry fails")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt"), ("src/new_large.py", "[BIG] New")]\n')

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("NEW allowlist entries" in e for e in test_errors):
            print("  PASS: Adding new entry correctly fails")
        else:
            errors.append(f"Test 2 FAILED: Adding new entry should fail, got: {test_errors}")

        # Test 3: Existing entry in baseline passes
        print("\nTest 3: Existing baseline entry passes")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if success:
            print("  PASS: Existing entry passes")
        else:
            errors.append(f"Test 3 FAILED: Existing entry should pass, got: {test_errors}")

        # Test 4: Duplicate baseline entry fails
        print("\nTest 4: Duplicate baseline entry fails")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Duplicate,team,grandfathered,None\n")

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("Duplicate" in e for e in test_errors):
            print("  PASS: Duplicate baseline entry fails")
        else:
            errors.append(f"Test 4 FAILED: Duplicate should fail, got: {test_errors}")

        # Test 5: Path traversal in baseline fails
        print("\nTest 5: Path traversal in baseline fails")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("../secret.py,llm_friendly_allowlist_py,[BAD] Path traversal,team,grandfathered,None\n")

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths=set(),
            verbose=False,
        )
        if not success and any(e for e in test_errors):
            print("  PASS: Path traversal fails")
        else:
            errors.append(f"Test 5 FAILED: Path traversal should fail, got: {test_errors}")

        # Test 6: .llm-friendly-ignore new entry fails
        print("\nTest 6: .llm-friendly-ignore new entry fails")
        subdir = repo_root / "src" / "newdir"
        subdir.mkdir(parents=True)
        ignore_file = subdir / ".llm-friendly-ignore"
        with open(ignore_file, "w", encoding="utf-8") as f:
            f.write("# Comment\noversized_file.py\n")

        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = []\n")

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("NEW allowlist entries" in e for e in test_errors):
            print("  PASS: .llm-friendly-ignore new entry fails")
        else:
            errors.append(f"Test 6 FAILED: Should fail, got: {test_errors}")

        # Test 7: Modified allowlisted file still allowlisted => FAIL
        print("\nTest 7: Modified allowlisted file still allowlisted => FAIL")
        if ignore_file.exists():
            ignore_file.unlink()
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        changed = [ChangedFile(path="src/legacy.py", old_path=None, status="M")]
        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=changed,
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("Modified allowlisted files remain" in e for e in test_errors):
            print("  PASS: Modified allowlisted still in allowlist fails")
        else:
            errors.append(f"Test 7 FAILED: Should fail, got: {test_errors}")

        # Test 8: Modified allowlisted file removed from allowlist => PASS
        print("\nTest 8: Modified allowlisted file removed from allowlist => PASS")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = []\n")

        changed = [ChangedFile(path="src/legacy.py", old_path=None, status="M")]
        success, test_errors, test_warnings = run_verification(
            repo_root,
            changed_files=changed,
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if success and any("removed from allowlist" in w for w in test_warnings):
            print("  PASS: Modified and removed from allowlist passes")
        else:
            errors.append(f"Test 8 FAILED: Should pass, got: {test_errors}")

        # Test 9: Deleted allowlisted file plus removed allowlist entry => PASS
        print("\nTest 9: Deleted allowlisted file plus removed entry => PASS")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write("ALLOWLIST = []\n")

        changed = [ChangedFile(path="src/legacy.py", old_path=None, status="D")]
        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=changed,
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if success:
            print("  PASS: Deleted file removed from allowlist passes")
        else:
            errors.append(f"Test 9 FAILED: Should pass, got: {test_errors}")

        # Test 10: Renamed allowlisted file still allowlisted => FAIL
        print("\nTest 10: Renamed allowlisted file still allowlisted => FAIL")
        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/new_name.py", "[LEGACY] Old debt")]\n')

        changed = [ChangedFile(path="src/new_name.py", old_path="src/legacy.py", status="R")]
        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=changed,
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("Renamed allowlisted file still allowlisted" in e for e in test_errors):
            print("  PASS: Renamed allowlisted still in allowlist fails")
        else:
            errors.append(f"Test 10 FAILED: Should fail, got: {test_errors}")

        # Test 11: .llm-friendly-ignore with repo escape => FAIL
        print("\nTest 11: .llm-friendly-ignore with repo escape => FAIL")
        subdir2 = repo_root / "src" / "testdir"
        subdir2.mkdir(parents=True)
        ignore_file2 = subdir2 / ".llm-friendly-ignore"
        with open(ignore_file2, "w", encoding="utf-8") as f:
            f.write("../outside.py\n")

        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")

        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any(e for e in test_errors):
            print("  PASS: .llm-friendly-ignore repo escape fails")
        else:
            errors.append(f"Test 11 FAILED: Should fail, got: {test_errors}")

        # Test 12: Baseline growth => FAIL
        print("\nTest 12: Baseline growth => FAIL")
        with open(baseline_csv, "w", encoding="utf-8") as f:
            f.write("path,source,reason,owner,status,migration_note\n")
            f.write("src/legacy.py,llm_friendly_allowlist_py,[LEGACY] Old debt,team,grandfathered,None\n")
            f.write("src/new_entry.py,llm_friendly_allowlist_py,[NEW] New entry,team,grandfathered,None\n")

        with open(allowlist_py, "w", encoding="utf-8") as f:
            f.write('ALLOWLIST = [("src/legacy.py", "[LEGACY] Old debt")]\n')

        success, test_errors, _ = run_verification(
            repo_root,
            changed_files=[],
            old_baseline_paths={"src/legacy.py"},
            verbose=False,
        )
        if not success and any("BASELINE GROWTH" in e for e in test_errors):
            print("  PASS: Baseline growth fails")
        else:
            errors.append(f"Test 12 FAILED: Should fail, got: {test_errors}")

    print("\n" + "=" * 50)
    if errors:
        print(f"Self-tests FAILED ({len(errors)} errors):")
        for err in errors:
            print(f"  - {err}")
        return False, errors
    else:
        print("All self-tests PASSED")
        return True, []


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
        # Run both normal and error-condition tests
        success1, errors1 = run_self_test()
        success2, errors2 = run_self_test_with_errors()
        success = success1 and success2
        errors = errors1 + errors2
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

    changed_files, changed_errors = get_changed_files(
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
