"""Terminal decision helpers for read-only diagnosis-loop outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def is_terminal_no_checks_decision(detail: dict[str, Any]) -> bool:
    """Check if the incident detail shows a terminal no-checks decision.

    A terminal no-checks decision occurs when:
    - automatic_diagnosis_review.available == True
    - automatic_diagnosis_review.artifact_type == "diagnosis-loop-review-packet"
    - automatic_diagnosis_review.decision == "stop_no_checks_proposed"
    - automatic_diagnosis_review.checks_requested == 0
    - automatic_diagnosis_review.checks_run == 0

    Args:
        detail: Incident detail dict from backend API

    Returns:
        True if this is a terminal no-checks decision
    """
    review = detail.get("automatic_diagnosis_review")
    if not isinstance(review, dict):
        return False

    if review.get("available") is not True:
        return False

    if review.get("artifact_type") != "diagnosis-loop-review-packet":
        return False

    if review.get("decision") != "stop_no_checks_proposed":
        return False

    checks_requested = review.get("checks_requested")
    checks_run = review.get("checks_run")

    # Treat None as 0 for comparison purposes
    if (checks_requested or 0) != 0:
        return False

    if (checks_run or 0) != 0:
        return False

    return True


def is_read_only_terminal_decision(detail: dict[str, Any]) -> bool:
    """Check if the terminal decision satisfies read-only constraints.

    A valid read-only terminal decision:
    - Has automatic_diagnosis_review
    - Has review_required_before_any_action == True
    - Has no_remediation_attempted == True

    Args:
        detail: Incident detail dict from backend API

    Returns:
        True if the terminal decision is read-only
    """
    review = detail.get("automatic_diagnosis_review")
    if not isinstance(review, dict):
        return False

    return (
        review.get("review_required_before_any_action") is True
        and review.get("no_remediation_attempted") is True
    )


__all__ = [
    "is_terminal_no_checks_decision",
    "is_read_only_terminal_decision",
]
