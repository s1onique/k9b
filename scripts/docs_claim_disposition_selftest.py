"""Self-test runner for docs_claim_disposition verifier.

Tests for disposition ledger validation rules.
"""

from __future__ import annotations

import sys

from scripts.docs_claim_disposition_rules import (
    check_all_candidates_have_disposition,
    check_candidate_id_valid,
    check_claim_id_valid_for_disposition,
    check_covered_by_claim_id_valid,
    check_disposition_enum_valid,
    check_high_risk_ignored_has_specific_notes,
    check_no_duplicate_dispositions,
    check_reason_code_enum_valid,
    check_reviewed_at_valid,
    check_reviewer_notes_required,
)
from scripts.docs_claim_disposition_selftest_cases import (  # noqa: E501
    SELF_TEST_CASES,
)


def run_self_test() -> bool:
    """Run self-test mode with fixture cases."""
    print("=== Docs Claim Disposition Self-Test ===\n")

    all_passed = True

    for i, case in enumerate(SELF_TEST_CASES):
        print(f"Test case {i + 1}: {case['name']}")

        dispositions = case.get("dispositions", [])
        valid_claim_ids = case.get("valid_claim_ids", set())
        valid_candidate_ids = case.get("valid_candidate_ids", set())
        should_fail = case.get("should_fail", False)
        expect_error = case.get("expect_error_contains", "")

        errors_found: list[str] = []

        # Run all checks
        result = check_disposition_enum_valid(dispositions)
        if not result.passed:
            errors_found.extend(result.errors)

        result = check_reason_code_enum_valid(dispositions)
        if not result.passed:
            errors_found.extend(result.errors)

        result = check_claim_id_valid_for_disposition(dispositions, valid_claim_ids)
        if not result.passed:
            errors_found.extend(result.errors)

        result = check_covered_by_claim_id_valid(dispositions, valid_claim_ids)
        if not result.passed:
            errors_found.extend(result.errors)

        result = check_candidate_id_valid(dispositions, valid_candidate_ids)
        if not result.passed:
            errors_found.extend(result.errors)

        result = check_reviewed_at_valid(dispositions)
        if not result.passed:
            errors_found.extend(result.errors)

        result = check_reviewer_notes_required(dispositions)
        if not result.passed:
            errors_found.extend(result.errors)

        result = check_no_duplicate_dispositions(dispositions)
        if not result.passed:
            errors_found.extend(result.errors)

        # Run candidate completeness check for negative tests
        if should_fail:
            result = check_all_candidates_have_disposition(dispositions, valid_candidate_ids)
            if not result.passed:
                errors_found.extend(result.errors)

        # NOTE: check_all_candidates_have_disposition is not run for happy-path tests
        # because individual tests only cover partial sets. The full check is done
        # by the verifier when the real ledger is complete.

        # Run high-risk guardrail check if candidates are provided
        candidates = case.get("candidates", [])
        if candidates:
            result = check_high_risk_ignored_has_specific_notes(dispositions, candidates)
            if not result.passed:
                errors_found.extend(result.errors)

        checks_failed = len(errors_found) > 0

        if should_fail:
            if not checks_failed:
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
            if checks_failed:
                print("  [UNEXPECTED FAIL] Expected pass but checks failed:")
                for e in errors_found:
                    print(f"         {e}")
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
