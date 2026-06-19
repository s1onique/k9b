"""Self-test fixtures for docs_claim_disposition verifier.

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
    check_no_duplicate_dispositions,
    check_reason_code_enum_valid,
    check_reviewed_at_valid,
    check_reviewer_notes_required,
)

# Valid claim IDs for testing
VALID_CLAIM_IDS = {"DOC-CLAIM-0001", "DOC-CLAIM-0002", "DOC-CLAIM-0066"}
# Candidate IDs must be DOC-CAND- followed by exactly 12 hex characters
VALID_CANDIDATE_IDS = {"DOC-CAND-abc123def456", "DOC-CAND-def456abc789", "DOC-CAND-000999012345"}

TODAY = "2026-06-19"

SELF_TEST_CASES = [
    # Happy path cases
    {
        "name": "registered_existing_claim passes",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "registered_existing_claim",
                "claim_id": "DOC-CLAIM-0001",
                "covered_by_claim_id": "",
                "reason_code": "already_registered",
                "reviewed_at": TODAY,
                "reviewer_notes": "",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": False,
    },
    {
        "name": "covered_by_existing_claim passes",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-def456abc789",
                "disposition": "covered_by_existing_claim",
                "claim_id": "",
                "covered_by_claim_id": "DOC-CLAIM-0002",
                "reason_code": "covered_by_broader_claim",
                "reviewed_at": TODAY,
                "reviewer_notes": "Broader claim covers this specific case",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": False,
    },
    {
        "name": "duplicate_candidate with notes passes",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-000999012345",
                "disposition": "duplicate_candidate",
                "claim_id": "",
                "covered_by_claim_id": "DOC-CLAIM-0001",
                "reason_code": "duplicate_same_doc",
                "reviewed_at": TODAY,
                "reviewer_notes": "Duplicate of line 50 in same doc",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": False,
    },
    {
        "name": "ignored_by_policy with valid reason passes",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-000999012345",
                "disposition": "ignored_by_policy",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "low_value_context",
                "reviewed_at": TODAY,
                "reviewer_notes": "Low-value prose fragment, not worth registry entry",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": False,
    },
    # Negative test cases
    {
        "name": "missing disposition for candidate fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "registered_existing_claim",
                "claim_id": "DOC-CLAIM-0001",
                "covered_by_claim_id": "",
                "reason_code": "already_registered",
                "reviewed_at": TODAY,
                "reviewer_notes": "",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": {"DOC-CAND-abc123def456", "DOC-CAND-missing123456"},  # Extra candidate
        "should_fail": True,
        "expect_error_contains": "without disposition",
    },
    {
        "name": "disposition for unknown candidate fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "registered_existing_claim",
                "claim_id": "DOC-CLAIM-0001",
                "covered_by_claim_id": "",
                "reason_code": "already_registered",
                "reviewed_at": TODAY,
                "reviewer_notes": "",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": {"DOC-CAND-other123456"},  # Unknown candidate
        "should_fail": True,
        "expect_error_contains": "not found in generated candidates",
    },
    {
        "name": "duplicate disposition fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "registered_existing_claim",
                "claim_id": "DOC-CLAIM-0001",
                "covered_by_claim_id": "",
                "reason_code": "already_registered",
                "reviewed_at": TODAY,
                "reviewer_notes": "",
            },
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "covered_by_existing_claim",
                "claim_id": "",
                "covered_by_claim_id": "DOC-CLAIM-0002",
                "reason_code": "covered_by_broader_claim",
                "reviewed_at": TODAY,
                "reviewer_notes": "Duplicate entry",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "duplicate",
    },
    {
        "name": "invalid disposition enum fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "invalid_disposition",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "",
                "reviewed_at": TODAY,
                "reviewer_notes": "Test",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "invalid disposition",
    },
    {
        "name": "invalid reason_code fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "ignored_by_policy",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "invalid_reason",
                "reviewed_at": TODAY,
                "reviewer_notes": "Test",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "invalid reason_code",
    },
    {
        "name": "covered_by_existing_claim without covered_by_claim_id fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "covered_by_existing_claim",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "covered_by_broader_claim",
                "reviewed_at": TODAY,
                "reviewer_notes": "Test",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "requires covered_by_claim_id",
    },
    {
        "name": "registered_existing_claim pointing to missing claim fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "registered_existing_claim",
                "claim_id": "DOC-CLAIM-9999",
                "covered_by_claim_id": "",
                "reason_code": "already_registered",
                "reviewed_at": TODAY,
                "reviewer_notes": "",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "not found in registry",
    },
    {
        "name": "empty notes fail where required",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "ignored_by_policy",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "low_value_context",
                "reviewed_at": TODAY,
                "reviewer_notes": "",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "requires non-empty reviewer_notes",
    },
    {
        "name": "empty reviewed_at fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "registered_existing_claim",
                "claim_id": "DOC-CLAIM-0001",
                "covered_by_claim_id": "",
                "reason_code": "already_registered",
                "reviewed_at": "",
                "reviewer_notes": "",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "empty reviewed_at",
    },
    {
        "name": "needs_new_claim without reason fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "needs_new_claim",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "",
                "reviewed_at": TODAY,
                "reviewer_notes": "Test",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "requires reason_code",
    },
]


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
        # because it requires ALL candidates to have dispositions.
        # Individual tests test partial sets. The full check is done
        # by the verifier when the real ledger is complete.

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
