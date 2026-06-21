"""Self-test fixtures for docs_claim_candidate_coverage verifier.

Uses TemporaryDirectory for hermetic testing.
"""

from __future__ import annotations

import sys

from scripts.docs_claim_candidate_coverage_rules import (
    check_high_severity_unregistered_current_not_required,
    check_high_severity_unregistered_current_trace_required,
    check_no_duplicate_candidate_ids,
    check_registration_status_valid,
    check_severity_valid,
)

SELF_TEST_CASES: list[dict[str, object]] = [
    {
        "name": "registered candidate passes",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-abc123",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "registered",
                "candidate_severity": "high",
                "claim_trace_required": "true",
            },
        ],
        "should_fail": False,
    },
    {
        "name": "high-severity unregistered current trace-required warns (advisory only)",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-def456",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "unregistered",
                "candidate_severity": "high",
                "claim_trace_required": "true",
            },
        ],
        "should_fail": False,
        "expect_warning_contains": "trace_required=true",
    },
    {
        "name": "high-severity unregistered current trace-not-required warns but does not fail",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-ghi789",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "unregistered",
                "candidate_severity": "high",
                "claim_trace_required": "false",
            },
        ],
        "should_fail": False,
        "expect_warning_contains": "trace_required=false",
    },
    {
        "name": "duplicate candidate IDs are advisory only",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-xyz999",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "registered",
                "candidate_severity": "medium",
                "claim_trace_required": "false",
            },
            {
                "candidate_id": "DOC-CAND-xyz999",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "registered",
                "candidate_severity": "medium",
                "claim_trace_required": "false",
            },
        ],
        "should_fail": False,
        "expect_info_contains": "duplicate",
    },
    {
        "name": "invalid registration status fails",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-invalid",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "bad_status",
                "candidate_severity": "medium",
                "claim_trace_required": "false",
            },
        ],
        "should_fail": True,
        "expect_error_contains": "invalid registration_status",
    },
    {
        "name": "invalid severity fails",
        "candidates": [
            {
                "candidate_id": "DOC-CAND-sevbad",
                "doc_path": "docs/test.md",
                "truth_status": "current",
                "registration_status": "unregistered",
                "candidate_severity": "bad_severity",
                "claim_trace_required": "true",
            },
        ],
        "should_fail": True,
        "expect_error_contains": "invalid candidate_severity",
    },
]


def run_self_test() -> bool:
    """Run self-test mode with fixture cases."""
    print("=== Docs Claim Candidate Coverage Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        candidates = case.get("candidates", [])
        should_fail = case.get("should_fail", False)
        expect_error = case.get("expect_error_contains", "")
        expect_warning = case.get("expect_warning_contains", "")

        checks_passed = True
        errors_found: list[str] = []
        warnings_found: list[str] = []

        result = check_no_duplicate_candidate_ids(candidates)
        if not result.passed:
            checks_passed = False
            errors_found.extend(result.errors)

        result = check_registration_status_valid(candidates)
        if not result.passed:
            checks_passed = False
            errors_found.extend(result.errors)

        result = check_severity_valid(candidates)
        if not result.passed:
            checks_passed = False
            errors_found.extend(result.errors)

        result = check_high_severity_unregistered_current_trace_required(candidates)
        if not result.passed:
            checks_passed = False
            errors_found.extend(result.errors)
        warnings_found.extend(result.warnings)

        result = check_high_severity_unregistered_current_not_required(candidates)
        warnings_found.extend(result.warnings)

        if should_fail:
            if checks_passed:
                print("  [UNEXPECTED PASS] Expected failure but checks passed")
                all_passed = False
            else:
                if expect_error:
                    if any(expect_error.lower() in e.lower() for e in errors_found):
                        print("  [OK] Failed as expected with matching error")
                    else:
                        print("  [PARTIAL] Failed but error mismatch:")
                        for e in errors_found:
                            print(f"         {e}")
                        all_passed = False
                else:
                    print("  [OK] Failed as expected")
        else:
            if not checks_passed:
                print("  [UNEXPECTED FAIL] Expected pass but checks failed:")
                for e in errors_found:
                    print(f"         {e}")
                all_passed = False
            elif expect_warning and not any(expect_warning.lower() in w.lower() for w in warnings_found):
                print(f"  [UNEXPECTED] Expected warning containing '{expect_warning}' but none found")
                all_passed = False
            else:
                print("  [OK] Passed as expected")

    print()
    if all_passed:
        print("SELF-TEST: PASSED")
    else:
        print("SELF-TEST: FAILED")

    return all_passed


def main() -> int:
    """Entry point for standalone self-test runner."""
    success = run_self_test()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
