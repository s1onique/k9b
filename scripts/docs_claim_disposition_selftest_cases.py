"""Self-test cases for docs_claim_disposition verifier.

Defines fixture cases for disposition ledger validation rules self-testing.
"""

from __future__ import annotations

# Valid claim IDs for testing
VALID_CLAIM_IDS = {"DOC-CLAIM-0001", "DOC-CLAIM-0002", "DOC-CLAIM-0066"}
# Candidate IDs must be DOC-CAND- followed by exactly 12 hex characters
VALID_CANDIDATE_IDS = {
    "DOC-CAND-abc123def456",
    "DOC-CAND-def456abc789",
    "DOC-CAND-000999012345",
}

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
        # Extra candidate without disposition
        "valid_candidate_ids": {
            "DOC-CAND-abc123def456",
            "DOC-CAND-missing123456",
        },
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
    # High-risk guardrail tests
    {
        "name": "high-risk ignored with generic notes fails",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "disposition": "ignored_by_policy",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "low_value_context",
                "reviewed_at": TODAY,
                "reviewer_notes": "Low-value prose fragment from: README.md",
            },
        ],
        "candidates": [
            {
                "candidate_id": "DOC-CAND-abc123def456",
                "doc_path": "README.md",
                "candidate_text": (
                    "The system must never mutate production without approval"
                ),
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": True,
        "expect_error_contains": "high-risk normative claim",
    },
    {
        "name": "high-risk ignored with specific notes passes",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-def456abc789",
                "disposition": "ignored_by_policy",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "low_value_context",
                "reviewed_at": TODAY,
                "reviewer_notes": "Design guideline only; no testable behavioral invariant",
            },
        ],
        "candidates": [
            {
                "candidate_id": "DOC-CAND-def456abc789",
                "doc_path": "docs/doctrine/constitution.md",
                "candidate_text": (
                    "The system must never mutate production without approval"
                ),
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": False,
    },
    {
        "name": "table fragment with generic notes passes",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-000999012345",
                "disposition": "ignored_by_policy",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "low_value_context",
                "reviewed_at": TODAY,
                "reviewer_notes": "Low-value prose fragment from: docs/data-model.md",
            },
        ],
        "candidates": [
            {
                "candidate_id": "DOC-CAND-000999012345",
                "doc_path": "docs/data-model/artifacts.md",
                "candidate_text": "| Artifact | Path | Type |",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": VALID_CANDIDATE_IDS,
        "should_fail": False,
    },
    {
        "name": "short fragment with generic notes passes",
        "dispositions": [
            {
                "candidate_id": "DOC-CAND-00000001ab12",
                "disposition": "ignored_by_policy",
                "claim_id": "",
                "covered_by_claim_id": "",
                "reason_code": "low_value_context",
                "reviewed_at": TODAY,
                "reviewer_notes": "Low-value prose fragment from: README.md",
            },
        ],
        "candidates": [
            {
                "candidate_id": "DOC-CAND-00000001ab12",
                "doc_path": "README.md",
                "candidate_text": "immutable",
            },
        ],
        "valid_claim_ids": VALID_CLAIM_IDS,
        "valid_candidate_ids": {"DOC-CAND-00000001ab12"},
        "should_fail": False,
    },
]
