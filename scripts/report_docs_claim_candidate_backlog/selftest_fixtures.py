"""Self-test fixtures for documentation claim candidate backlog reporter.

This module contains fixture data for self-tests to keep selftest.py under
the LLM-friendly line limit.
"""

from __future__ import annotations

# Type alias for test entries
TestEntry = dict[str, str | int | list[str]]


def make_generic_ignored_entry(
    candidate_id: str = "DOC-CAND-TEST000001",
    doc_path: str = "docs/security/auth.md",
    score: int = 42,
    has_any_marker: bool = False,
) -> TestEntry:
    """Create a generic ignored entry for testing."""
    return {
        "candidate_id": candidate_id,
        "disposition": "ignored_by_policy",
        "reason_code": "low_value_context",
        "source_doc_path": doc_path,
        "candidate_text": "Test text.",
        "reviewed_at": "",
        "reviewer_notes": "Low-value prose fragment from: docs/foo.md",
        "score": score,
        "calibrated_score": score,
        "risk_reasons": ["generic_ignored_note", "high_value_doc:security"],
        "review_class": "non_normative_prose",
        "review_class_reasons": ["structural:generic_ignored_note"],
        "is_act_5_0_reviewed": False,
        "is_act_5_2_reviewed": False,
        "has_any_act_review_marker": has_any_marker,
        "is_generic_low_value_note": True,
        "is_stale": False,
        "is_historical": False,
        "is_stale_doc": False,
        "is_historical_doc": False,
        "is_high_value_doc": True,
    }


def make_stale_entry(
    candidate_id: str = "DOC-CAND-TEST000002",
    score: int = -12,
) -> TestEntry:
    """Create a stale entry for testing."""
    return {
        "candidate_id": candidate_id,
        "disposition": "stale",
        "reason_code": "stale_doc",
        "source_doc_path": "docs/old/design.md",
        "candidate_text": "Test text 2.",
        "reviewed_at": "2026-06-19",
        "reviewer_notes": "From stale doc: docs/old/design.md",
        "score": score,
        "calibrated_score": score,
        "risk_reasons": ["deprioritized:stale"],
        "review_class": "stale_or_historical",
        "review_class_reasons": ["disposition:stale"],
        "is_act_5_0_reviewed": False,
        "is_act_5_2_reviewed": False,
        "has_any_act_review_marker": False,
        "is_generic_low_value_note": True,
        "is_stale": True,
        "is_historical": False,
        "is_stale_doc": True,
        "is_historical_doc": False,
        "is_high_value_doc": False,
    }


def make_claim_candidate_entry(
    candidate_id: str = "DOC-CAND-TEST000003",
    score: int = 62,
) -> TestEntry:
    """Create a claim candidate entry for testing."""
    return {
        "candidate_id": candidate_id,
        "disposition": "ignored_by_policy",
        "reason_code": "low_value_context",
        "source_doc_path": "docs/security/auth.md",
        "candidate_text": "The system must handle authentication securely.",
        "reviewed_at": "",
        "reviewer_notes": "Custom note about MUST requirement.",
        "score": score - 20,  # Base score before calibration
        "calibrated_score": score,
        "risk_reasons": ["generic_ignored_note", "high_value_doc:security", "normative_text"],
        "review_class": "claim_candidate",
        "review_class_reasons": ["claim_signal:must"],
        "is_act_5_0_reviewed": False,
        "is_act_5_2_reviewed": False,
        "has_any_act_review_marker": False,
        "is_generic_low_value_note": True,
        "is_stale": False,
        "is_historical": False,
        "is_stale_doc": False,
        "is_historical_doc": False,
        "is_high_value_doc": True,
    }


def make_structural_fragment_entry(
    candidate_id: str = "DOC-CAND-TEST000004",
    score: int = 12,
) -> TestEntry:
    """Create a structural fragment entry for testing."""
    return {
        "candidate_id": candidate_id,
        "disposition": "ignored_by_policy",
        "reason_code": "generated_from_table_fragment",
        "source_doc_path": "docs/security/table.md",
        "candidate_text": "Row data from table.",
        "reviewed_at": "",
        "reviewer_notes": "Table fragment.",
        "score": score + 30,  # Base score before calibration
        "calibrated_score": score,
        "risk_reasons": ["generic_ignored_note", "high_value_doc:security"],
        "review_class": "structural_fragment",
        "review_class_reasons": ["structural:generated_from_table_fragment"],
        "is_act_5_0_reviewed": False,
        "is_act_5_2_reviewed": False,
        "has_any_act_review_marker": False,
        "is_generic_low_value_note": True,
        "is_stale": False,
        "is_historical": False,
        "is_stale_doc": False,
        "is_historical_doc": False,
        "is_high_value_doc": True,
    }


def make_covered_entry(
    candidate_id: str = "DOC-CAND-TEST000005",
    score: int = 0,
) -> TestEntry:
    """Create a covered entry for testing."""
    return {
        "candidate_id": candidate_id,
        "disposition": "covered_by_existing_claim",
        "reason_code": "covered_by_broader_claim",
        "source_doc_path": "docs/normal.md",
        "candidate_text": "Some text.",
        "reviewed_at": "2026-06-19",
        "reviewer_notes": "Already covered by DOC-CLAIM-0001.",
        "score": score + 20,  # Base score before calibration
        "calibrated_score": score,
        "risk_reasons": ["covered_note_weak"],
        "review_class": "covered_or_registered",
        "review_class_reasons": ["disposition:covered_or_registered"],
        "is_act_5_0_reviewed": False,
        "is_act_5_2_reviewed": False,
        "has_any_act_review_marker": False,
        "is_generic_low_value_note": True,
        "is_stale": False,
        "is_historical": False,
        "is_stale_doc": False,
        "is_historical_doc": False,
        "is_high_value_doc": False,
    }


def make_reviewed_low_value_entry(
    candidate_id: str = "DOC-CAND-TEST000006",
    score: int = -20,
) -> TestEntry:
    """Create a reviewed low-value entry for testing."""
    return {
        "candidate_id": candidate_id,
        "disposition": "ignored_by_policy",
        "reason_code": "low_value_context",
        "source_doc_path": "docs/security/auth.md",
        "candidate_text": "Some text.",
        "reviewed_at": "2026-06-19",
        "reviewer_notes": "ACT 5.4 review: Low-value prose fragment from: docs/foo.md",
        "score": score + 40,  # Base score before calibration
        "calibrated_score": score,
        "risk_reasons": ["generic_ignored_note"],
        "review_class": "reviewed_low_value",
        "review_class_reasons": ["deprioritized:act_review_marker"],
        "is_act_5_0_reviewed": False,
        "is_act_5_2_reviewed": False,
        "has_any_act_review_marker": True,
        "is_generic_low_value_note": True,
        "is_stale": False,
        "is_historical": False,
        "is_stale_doc": False,
        "is_historical_doc": False,
        "is_high_value_doc": True,
    }


def make_unknown_entry(
    candidate_id: str = "DOC-CAND-TEST000007",
    score: int = 42,
) -> TestEntry:
    """Create an unknown classification entry for testing."""
    return {
        "candidate_id": candidate_id,
        "disposition": "ignored_by_policy",
        "reason_code": "low_value_context",
        "source_doc_path": "docs/normal/doc.md",
        "candidate_text": "Some normal text without strong signals.",
        "reviewed_at": "",
        "reviewer_notes": "Custom note without generic pattern.",
        "score": score,
        "calibrated_score": score,
        "risk_reasons": [],
        "review_class": "unknown",
        "review_class_reasons": ["unknown"],
        "is_act_5_0_reviewed": False,
        "is_act_5_2_reviewed": False,
        "has_any_act_review_marker": False,
        "is_generic_low_value_note": False,
        "is_stale": False,
        "is_historical": False,
        "is_stale_doc": False,
        "is_historical_doc": False,
        "is_high_value_doc": False,
    }
