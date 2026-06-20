"""Data models and risk scoring for documentation claim candidate backlog reporter."""

from __future__ import annotations

import re

from .claim_classification import classify_claim_candidate

# High-value doc path terms (security-relevant or operator-facing)
HIGH_VALUE_PATH_TERMS = {
    "security",
    "auth",
    "incident",
    "diagnosis",
    "automatic",
    "runtime",
    "artifact",
    "evidence",
    "review-packets",
    "operator",
    "ci",
    "gate",
    "truthfulness",
    "data-model",
}

# Normative text terms
NORMATIVE_TEXT_TERMS = {
    "must",
    "should",
    "cannot",
    "never",
    "only",
    "guarantee",
    "required",
    "protected",
    "authenticated",
    "secure",
    "immutable",
    "append-only",
    "read-only",
    "mutation",
    "source of truth",
    "evidence",
    "invariant",
    "production",
    "operator",
}

# Generic note patterns to detect low-value ignored notes
GENERIC_NOTE_PATTERNS = [
    re.compile(r"^Low-value prose fragment from:"),
    re.compile(r"^From stale doc:"),
    re.compile(r"^From historical doc:"),
    re.compile(r"^Already registered to DOC-CLAIM-"),
]

# ACT review markers (case-insensitive, handles trailing punctuation)
_ACT_5_0_RE = re.compile(r"\bACT\s*5\.0\s*review\b", re.IGNORECASE)
_ACT_5_2_RE = re.compile(r"\bACT\s*5\.2\s*review\b", re.IGNORECASE)

# Structural/non-normative reason codes
STRUCTURAL_REASON_CODES = {
    "generated_from_table_fragment",
    "generated_from_heading",
    "schema_field_label",
}

NON_NORMATIVE_REASON_CODES = {
    "non_normative_description",
    "design_or_future_note",
    "example_or_exemplar",
    "policy_statement",
    "implementation_detail",
}

# Review class values
REVIEW_CLASS_CLAIM_CANDIDATE = "claim_candidate"
REVIEW_CLASS_STRUCTURAL_FRAGMENT = "structural_fragment"
REVIEW_CLASS_NON_NORMATIVE_PROSE = "non_normative_prose"
REVIEW_CLASS_COVERED_OR_REGISTERED = "covered_or_registered"
REVIEW_CLASS_STALE_OR_HISTORICAL = "stale_or_historical"
REVIEW_CLASS_REVIEWED_LOW_VALUE = "reviewed_low_value"
REVIEW_CLASS_UNKNOWN = "unknown"

ALL_REVIEW_CLASSES = [
    REVIEW_CLASS_CLAIM_CANDIDATE,
    REVIEW_CLASS_STRUCTURAL_FRAGMENT,
    REVIEW_CLASS_NON_NORMATIVE_PROSE,
    REVIEW_CLASS_COVERED_OR_REGISTERED,
    REVIEW_CLASS_STALE_OR_HISTORICAL,
    REVIEW_CLASS_REVIEWED_LOW_VALUE,
    REVIEW_CLASS_UNKNOWN,
]

# Score adjustments by review class
REVIEW_CLASS_SCORE_ADJUSTMENTS: dict[str, int] = {
    REVIEW_CLASS_CLAIM_CANDIDATE: 20,
    REVIEW_CLASS_STRUCTURAL_FRAGMENT: -30,
    REVIEW_CLASS_NON_NORMATIVE_PROSE: -25,
    REVIEW_CLASS_REVIEWED_LOW_VALUE: -40,
    REVIEW_CLASS_STALE_OR_HISTORICAL: -30,
    REVIEW_CLASS_COVERED_OR_REGISTERED: -20,
    REVIEW_CLASS_UNKNOWN: 0,
}

# Type aliases
CandidateData = dict[str, str]
BacklogEntry = dict[str, str | int | list[str]]


def has_act_5_0_marker(notes: str) -> bool:
    """Check if reviewer notes contain ACT 5.0 marker."""
    return bool(_ACT_5_0_RE.search(notes))


def has_act_5_2_marker(notes: str) -> bool:
    """Check if reviewer notes contain ACT 5.2 marker."""
    return bool(_ACT_5_2_RE.search(notes))


def has_any_act_marker(notes: str) -> bool:
    """Check if reviewer notes contain any ACT review marker."""
    return has_act_5_0_marker(notes) or has_act_5_2_marker(notes)


def is_generic_low_value_note(notes: str) -> bool:
    """Check if reviewer notes match generic low-value patterns."""
    notes = notes.strip()
    for pattern in GENERIC_NOTE_PATTERNS:
        if pattern.match(notes):
            return True
    return False


def is_stale_disposition(disposition: str) -> bool:
    """Check if disposition indicates stale."""
    return disposition == "stale"


def is_historical_disposition(disposition: str) -> bool:
    """Check if disposition indicates historical."""
    return disposition == "historical"


def is_high_value_doc(doc_path: str) -> bool:
    """Check if doc path contains high-value terms."""
    doc_path_lower = doc_path.lower()
    for term in HIGH_VALUE_PATH_TERMS:
        if term in doc_path_lower:
            return True
    return False


def has_normative_text(candidate_text: str) -> bool:
    """Check if candidate text contains normative language."""
    text_lower = candidate_text.lower()
    words = re.findall(r"\b\w+\b", text_lower)
    for term in NORMATIVE_TEXT_TERMS:
        if term in words:
            return True
        if " " in term and term in text_lower:
            return True
    return False


def get_truth_status_from_inventory(doc_path: str, inventory: dict[str, str]) -> str:
    """Get truth_status for a doc from inventory."""
    return inventory.get(doc_path, "")


def is_stale_doc(doc_path: str, inventory: dict[str, str]) -> bool:
    """Check if doc is marked stale in inventory."""
    return get_truth_status_from_inventory(doc_path, inventory) == "stale"


def is_historical_doc(doc_path: str, inventory: dict[str, str]) -> bool:
    """Check if doc is marked historical in inventory."""
    return get_truth_status_from_inventory(doc_path, inventory) == "historical"


def compute_risk_score(
    disposition: str,
    reason_code: str,
    notes: str,
    doc_path: str,
    candidate_text: str,
    inventory: dict[str, str],
    has_act_5_0: bool,
    has_act_5_2: bool,
) -> tuple[int, list[str]]:
    """Compute risk score and reasons for a candidate.

    Returns (score, reasons).
    """
    score = 0
    reasons: list[str] = []

    # Base score adjustments
    if disposition == "ignored_by_policy" and is_generic_low_value_note(notes):
        score += 20
        reasons.append("generic_ignored_note")

    if disposition == "covered_by_existing_claim" and is_generic_low_value_note(notes):
        score += 12
        reasons.append("covered_note_weak")

    # High-value doc check
    if is_high_value_doc(doc_path):
        doc_lower = doc_path.lower()
        for term in HIGH_VALUE_PATH_TERMS:
            if term in doc_lower:
                reasons.append(f"high_value_doc:{term}")
        score += 10
        if is_stale_doc(doc_path, inventory):
            score += 5
            reasons.append("high_value_but_stale")
        if is_historical_doc(doc_path, inventory):
            score += 3
            reasons.append("high_value_but_historical")

    # Normative text check
    if has_normative_text(candidate_text):
        score += 8
        reasons.append("normative_text")
        text_lower = candidate_text.lower()
        for term in ["must", "should", "cannot", "never", "required", "guarantee"]:
            if f" {term} " in f" {text_lower} " or text_lower.startswith(f"{term} "):
                reasons.append(f"normative:{term}")
                break

    # Reviewer note quality check (no ACT marker)
    if not has_any_act_marker(notes):
        score += 4
        reasons.append("no_act_marker")

    # Already reviewed deprioritization
    if has_act_5_0:
        score -= 20
        reasons.append("deprioritized:act_5_0_reviewed")
    elif has_act_5_2:
        score -= 20
        reasons.append("deprioritized:act_5_2_reviewed")

    # Stale/historical doc deprioritization
    if is_stale_doc(doc_path, inventory) and not is_high_value_doc(doc_path):
        score -= 12
        reasons.append("deprioritized:stale")
    elif is_historical_doc(doc_path, inventory) and not is_high_value_doc(doc_path):
        score -= 15
        reasons.append("deprioritized:historical")

    return score, reasons


def _is_structural_fragment(
    reason_code: str,
    notes: str,
) -> tuple[bool, list[str]]:
    """Check if candidate is a structural fragment.
    
    Returns (is_structural, reasons).
    """
    reasons: list[str] = []
    
    # Check reason code
    if reason_code in STRUCTURAL_REASON_CODES:
        reasons.append(f"structural:{reason_code}")
    
    # Check notes patterns
    notes_lower = notes.lower()
    structural_patterns = [
        ("table", "structural:table_phrase"),
        ("schema field", "structural:schema_field_label"),
        ("heading", "structural:heading_fragment"),
        ("list item", "structural:list_item_fragment"),
        ("metadata", "structural:metadata_annotation"),
        ("column label", "structural:column_label"),
        ("header", "structural:header_fragment"),
    ]
    
    for pattern, tag in structural_patterns:
        if pattern in notes_lower:
            reasons.append(tag)
    
    return len(reasons) > 0, reasons


def _is_non_normative_prose(
    reason_code: str,
    notes: str,
    candidate_text: str,
) -> tuple[bool, list[str]]:
    """Check if candidate is non-normative prose.
    
    Returns (is_non_normative, reasons).
    
    Note: Does NOT classify generic low-value notes as non-normative.
    That classification is handled separately in classify_review_class()
    to allow strong claim signals to override.
    """
    reasons: list[str] = []
    
    # Check reason code
    if reason_code in NON_NORMATIVE_REASON_CODES:
        reasons.append(f"non_normative:{reason_code}")
    
    # Check notes patterns indicating non-normative content
    notes_lower = notes.lower()
    non_normative_patterns = [
        ("descriptive prose", "non_normative:descriptive_prose"),
        ("design intent", "non_normative:design_intent"),
        ("example", "non_normative:example"),
        ("exemplar", "non_normative:exemplar"),
        ("architecture note", "non_normative:architecture_note"),
        ("not a standalone behavioral claim", "non_normative:not_standalone_claim"),
        ("lacks standalone behavioral claim", "non_normative:lacks_standalone_claim"),
        ("design note", "non_normative:design_note"),
        ("future note", "non_normative:future_note"),
    ]
    
    for pattern, tag in non_normative_patterns:
        if pattern in notes_lower:
            reasons.append(tag)
    
    return len(reasons) > 0, reasons


def classify_review_class(
    disposition: str,
    reason_code: str,
    notes: str,
    has_any_act_marker: bool,
    doc_path: str,
    inventory: dict[str, str],
    candidate_text: str,
) -> tuple[str, list[str]]:
    """Classify a candidate into a review class.
    
    Returns (review_class, review_class_reasons).
    
    Classification order (first match wins):
    1. covered_or_registered - disposition indicates coverage or registration
    2. stale_or_historical - disposition or doc indicates stale/historical
    3. reviewed_low_value - has ACT marker and is ignored_by_policy
    4. structural_fragment - table/heading/schema fragments
    5. claim_candidate - uses refined classification model
    6. non_normative_prose - descriptive/non-normative prose
    7. unknown - fallback
    """
    # A. covered_or_registered
    if disposition in ("covered_by_existing_claim", "registered_existing_claim"):
        return REVIEW_CLASS_COVERED_OR_REGISTERED, ["disposition:covered_or_registered"]
    
    # B. stale_or_historical
    if disposition in ("stale", "historical"):
        return REVIEW_CLASS_STALE_OR_HISTORICAL, [f"disposition:{disposition}"]
    
    # Check inventory for stale/historical docs
    truth_status = get_truth_status_from_inventory(doc_path, inventory)
    if truth_status in ("stale", "historical"):
        return REVIEW_CLASS_STALE_OR_HISTORICAL, [f"doc_truth_status:{truth_status}"]
    
    # C. reviewed_low_value
    if has_any_act_marker and disposition == "ignored_by_policy":
        return REVIEW_CLASS_REVIEWED_LOW_VALUE, ["deprioritized:act_review_marker"]
    
    # D. structural_fragment - check BEFORE claim signals
    # A structural fragment with normative words is still structural, not claim_candidate
    is_structural, structural_reasons = _is_structural_fragment(reason_code, notes)
    if is_structural:
        return REVIEW_CLASS_STRUCTURAL_FRAGMENT, structural_reasons
    
    # E. claim_candidate - use refined classification model
    is_claim_candidate, claim_reasons = classify_claim_candidate(
        candidate_text, notes, doc_path
    )
    if is_claim_candidate:
        return REVIEW_CLASS_CLAIM_CANDIDATE, claim_reasons
    
    # F. non_normative_prose - descriptive/non-normative content
    is_non_normative, non_normative_reasons = _is_non_normative_prose(
        reason_code, notes, candidate_text
    )
    if is_non_normative:
        return REVIEW_CLASS_NON_NORMATIVE_PROSE, non_normative_reasons
    
    # G. Generic low-value note without strong signals
    if is_generic_low_value_note(notes):
        return REVIEW_CLASS_NON_NORMATIVE_PROSE, ["structural:generic_ignored_note"]
    
    # H. unknown
    return REVIEW_CLASS_UNKNOWN, ["unknown"]


def compute_calibrated_score(
    base_score: int,
    review_class: str,
) -> int:
    """Apply review class calibration to base score.
    
    Returns calibrated score with review class adjustment applied.
    """
    adjustment = REVIEW_CLASS_SCORE_ADJUSTMENTS.get(review_class, 0)
    return base_score + adjustment


def is_cleanup_class(review_class: str) -> bool:
    """Check if review class is a cleanup class (not claim_candidate)."""
    return review_class in (
        REVIEW_CLASS_STRUCTURAL_FRAGMENT,
        REVIEW_CLASS_NON_NORMATIVE_PROSE,
        REVIEW_CLASS_REVIEWED_LOW_VALUE,
        REVIEW_CLASS_STALE_OR_HISTORICAL,
        REVIEW_CLASS_COVERED_OR_REGISTERED,
    )