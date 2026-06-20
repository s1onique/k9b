"""Data models and risk scoring for documentation claim candidate backlog reporter."""

from __future__ import annotations

import re

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