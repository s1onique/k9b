"""Next-check execution failure classification helpers.

This module extracts failure classification logic and constants
from ui_next_check_execution.py for better separation of concerns.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ui_next_check_execution_history import FailureFollowUp


# Failure classification constants
_FAILURE_CLASS_TIMED_OUT = "timed-out"
_FAILURE_CLASS_COMMAND_UNAVAILABLE = "command-unavailable"
_FAILURE_CLASS_CONTEXT_UNAVAILABLE = "context-unavailable"
_FAILURE_CLASS_COMMAND_FAILED = "command-failed"
_FAILURE_CLASS_BLOCKED_BY_GATING = "blocked-by-gating"
_FAILURE_CLASS_APPROVAL_MISSING = "approval-missing-or-stale"
_FAILURE_CLASS_UNKNOWN = "unknown-failure"

_FAILURE_ACTIONS: dict[str, str] = {
    _FAILURE_CLASS_TIMED_OUT: "Retry candidate",
    _FAILURE_CLASS_COMMAND_UNAVAILABLE: "Inspect artifact output",
    _FAILURE_CLASS_CONTEXT_UNAVAILABLE: "Open cluster detail",
    _FAILURE_CLASS_COMMAND_FAILED: "Inspect artifact output",
    _FAILURE_CLASS_BLOCKED_BY_GATING: "Open cluster detail",
    _FAILURE_CLASS_APPROVAL_MISSING: "Review approval state",
    _FAILURE_CLASS_UNKNOWN: "Inspect artifact output",
}

_FAILURE_DEFAULT_SUMMARIES: dict[str, str] = {
    _FAILURE_CLASS_TIMED_OUT: "Command timed out.",
    _FAILURE_CLASS_COMMAND_UNAVAILABLE: "kubectl is unavailable on this host.",
    _FAILURE_CLASS_CONTEXT_UNAVAILABLE: "Unable to resolve the cluster context.",
    _FAILURE_CLASS_COMMAND_FAILED: "Command returned a non-zero exit code.",
    _FAILURE_CLASS_BLOCKED_BY_GATING: "Candidate was blocked by planner gating.",
    _FAILURE_CLASS_APPROVAL_MISSING: "Candidate requires operator approval.",
    _FAILURE_CLASS_UNKNOWN: "Execution failed without details.",
}


def _classify_blocked_candidate(candidate: Mapping[str, object]) -> FailureFollowUp | None:
    """Classify a blocked candidate into a failure category with suggested action.

    Checks queue status, approval state, and gating reasons to determine
    whether a candidate is blocked and how to advise the operator.
    """
    # Import here to avoid circular dep on FailureFollowUp
    from .ui_next_check_execution_history import FailureFollowUp

    queue_status = str(candidate.get("queueStatus") or "")
    if queue_status == "duplicate-or-stale":
        return None
    requires_approval = bool(candidate.get("requiresOperatorApproval"))
    approval_state = str(candidate.get("approvalState") or "").lower()
    if requires_approval and approval_state not in ("approved", "not-required"):
        if approval_state == "approval-stale":
            summary = "Approval is stale; reapprove this candidate."
        elif approval_state == "approval-orphaned":
            summary = "Approval record is orphaned; reapprove the candidate."
        else:
            summary = "Candidate requires operator approval before execution."
        return FailureFollowUp(
            _FAILURE_CLASS_APPROVAL_MISSING,
            summary,
            _FAILURE_ACTIONS[_FAILURE_CLASS_APPROVAL_MISSING],
        )
    if queue_status in ("failed", "approval-needed", "safe-ready", "approved-ready"):
        gating_reason = candidate.get("gatingReason") or candidate.get("blockingReason")
        reason_text = str(gating_reason).strip() if gating_reason else ""
        if reason_text:
            summary = f"Gating reason: {reason_text}"
            return FailureFollowUp(
                _FAILURE_CLASS_BLOCKED_BY_GATING,
                summary,
                _FAILURE_ACTIONS[_FAILURE_CLASS_BLOCKED_BY_GATING],
            )
    return None
