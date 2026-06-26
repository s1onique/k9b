#!/usr/bin/env python
"""Verify LLM security requirements register integrity.

This script checks that:
1. Register file exists and parses strictly as CSV
2. Required columns are present
3. No duplicate req_id values
4. req_id matches REQ-LLMSEC-0001 pattern
5. REQ IDs are sorted ascending
6. Required fields are non-empty
7. claim_category is from allowed enum
8. security_domain is from allowed enum
9. assurance_level is from allowed enum
10. status is from allowed enum
11. implementation_refs are non-empty for current MUST/SHOULD
12. verification_refs are non-empty for current MUST/SHOULD
13. N/A requirements have specific evidence of non-applicability
14. implementation_ref paths exist on disk
15. source_doc paths exist on disk

Usage:
    python scripts/verify_llm_security_requirements.py           # verify
    python scripts/verify_llm_security_requirements.py --self-test  # run self-test
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from verify_llm_security_requirements_checks import (
    check_csv_parse,
    check_dangling_req_refs,
    check_enum_field,
    check_na_requirements,
    check_no_duplicate_ids,
    check_refs_exist,
    check_refs_non_empty_for_current,
    check_req_id_format,
    check_req_ids_sorted,
    check_required_fields,
    get_all_checks,
    print_summary,
    read_registry,
)
from verify_llm_security_requirements_contract import (
    ALLOWED_ASSURANCE_LEVEL,
    ALLOWED_CLAIM_CATEGORY,
    ALLOWED_SECURITY_DOMAIN,
    ALLOWED_STATUS,
    REGISTRY_CSV,
    REQCheckResult,
)
from verify_llm_security_requirements_fixtures import SELF_TEST_CASES


def _check_impl_refs_exist(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that implementation_ref paths exist on disk."""
    from verify_llm_security_requirements_contract import REPO_ROOT
    result = REQCheckResult()
    errors, _ = check_refs_exist(rows, "implementation_refs", REPO_ROOT)
    for err in errors:
        result.add_error(err)
    return result


def _check_ver_refs_exist(rows: list[dict[str, str]]) -> REQCheckResult:
    """Check that verification_ref paths exist on disk."""
    from verify_llm_security_requirements_contract import REPO_ROOT
    result = REQCheckResult()
    errors, _ = check_refs_exist(rows, "verification_refs", REPO_ROOT)
    for err in errors:
        result.add_error(err)
    return result


def run_verification() -> bool:
    """Run all verification checks."""
    print("=== LLM Security Requirements Verification ===\n")

    # Read registry
    rows, error = read_registry(REGISTRY_CSV)
    if error:
        print(f"[FAIL] CSV parse: {error}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    # Read header
    try:
        with open(REGISTRY_CSV, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
    except Exception as exc:
        print(f"[FAIL] Could not read CSV header: {exc}")
        print("\nVERIFICATION GATE: FAILED")
        return False

    print(f"[INFO] Registry has {len(rows)} requirements")

    # Run checks
    checks_results = get_all_checks(rows, header)

    all_passed = True
    for name, result in checks_results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {name}")
        for error_msg in result.errors:
            print(f"      ERROR: {error_msg}")
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


def _run_single_self_test(
    case: dict[str, str], case_num: int, tmp_path: Path
) -> tuple[bool, bool]:
    """Run a single self-test case. Returns (passed, test_passed)."""
    tmp_registry = tmp_path / "docs" / "requirements" / "llm_security_requirements.csv"
    tmp_registry.parent.mkdir(parents=True, exist_ok=True)
    tmp_registry.write_text(str(case["registry"]))

    # Create fixture docs directory structure
    (tmp_path / "docs" / "security").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "requirements").mkdir(parents=True, exist_ok=True)

    # Handle doc_content from fixture (for dangling REQ tests)
    doc_content = case.get("doc_content", {})
    if doc_content:
        for rel_path, content in doc_content.items():
            fpath = tmp_path / rel_path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
    else:
        # Create minimal fixture docs that won't reference any REQ IDs
        (tmp_path / "docs" / "security" / "test_fixture.md").write_text("# Test Fixture\n")
        (tmp_path / "docs" / "requirements" / "test_fixture.md").write_text("# Test Fixture\n")

    rows, error = read_registry(tmp_registry)
    if error and case["should_fail"]:
        return True, True
    if error and not case["should_fail"]:
        return False, False

    try:
        with open(tmp_registry, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, [])
    except Exception:
        return False, False

    # Run all checks including dangling REQ check with tmp_path
    # Note: source_doc_exists and impl/ver refs are skipped in self-test
    # because fixture docs don't reference actual paths
    def _get_checks_for_test(r: list[dict[str, str]], h: list[str], root: Path) -> list[tuple[str, REQCheckResult]]:
        """Return all checks with dangling check using given root."""
        checks = [
            ("CSV structure", check_csv_parse(r, h)),
            ("No duplicate req_id", check_no_duplicate_ids(r)),
            ("req_id format", check_req_id_format(r)),
            ("req_id sorted ascending", check_req_ids_sorted(r)),
            ("Required fields non-empty", check_required_fields(r)),
            ("claim_category valid", check_enum_field(r, "claim_category", ALLOWED_CLAIM_CATEGORY)),
            ("security_domain valid", check_enum_field(r, "security_domain", ALLOWED_SECURITY_DOMAIN)),
            ("assurance_level valid", check_enum_field(r, "assurance_level", ALLOWED_ASSURANCE_LEVEL)),
            ("status valid", check_enum_field(r, "status", ALLOWED_STATUS)),
            ("implementation_refs for MUST/SHOULD", check_refs_non_empty_for_current(r, "implementation_refs")),
            ("verification_refs for MUST/SHOULD", check_refs_non_empty_for_current(r, "verification_refs")),
            ("N/A requirements rationale", check_na_requirements(r)),
            # Skip source_doc_exists and impl/ver refs checks in self-test
            # because fixtures use non-existent paths
            ("dangling REQ refs in docs", check_dangling_req_refs(r, root)),
        ]
        return checks

    checks_results = _get_checks_for_test(rows, header, tmp_path)
    all_errors = [e for _, r in checks_results for e in r.errors]
    any_failed = any(not r.passed for _, r in checks_results)

    expected_fail = bool(case["should_fail"])
    expect_contains = case.get("expect_error_contains", "").lower()

    if expected_fail:
        if not any_failed:
            return False, False
        if expect_contains:
            found = any(expect_contains in e.lower() for e in all_errors)
            return found, True
        return True, True
    else:
        return not any_failed, not any_failed


def run_self_test() -> bool:
    """Run self-test mode with inline fixture cases."""
    print("=== LLM Security Requirements Self-Test ===\n")

    (Path(".") / "docs" / "security").mkdir(parents=True, exist_ok=True)
    (Path(".") / "src").mkdir(parents=True, exist_ok=True)
    (Path(".") / "tests").mkdir(parents=True, exist_ok=True)

    all_passed = True
    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            passed, test_passed = _run_single_self_test(case, i, tmp_path)
            if not test_passed:
                all_passed = False

    print()
    print("SELF-TEST: " + ("PASSED" if all_passed else "FAILED"))
    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify LLM security requirements register")
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
        rows, error = read_registry(REGISTRY_CSV)
        if error:
            print(f"Error reading registry: {error}")
            return 1
        print_summary(rows)
        return 0

    if args.self_test:
        success = run_self_test()
    else:
        success = run_verification()

    # Always print summary in verify mode
    if not args.self_test and success:
        rows, _ = read_registry(REGISTRY_CSV)
        print_summary(rows)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
