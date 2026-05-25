"""Planner queue ranking and priority rationale helpers.

This module provides pure derivation helpers for ranking reasons and priority
rationale that shape operator-facing queue projection logic.

Responsibilities:
- Derive structured ranking-reason/provenance categories from candidate state
- Derive compact operator-facing explanations for why an item is in its current state
- Provide priority ordering constants for queue sorting
"""

from __future__ import annotations

from collections.abc import Mapping

__all__ = [
    "NEXT_CHECK_QUEUE_PRIORITY_ORDER",
    "NEXT_CHECK_QUEUE_STATUS_ORDER",
    "QUEUE_STATUS_ORDER",
    "_derive_priority_rationale",
    "_derive_ranking_reason",
    "_determine_next_check_queue_status",
    "_queue_priority_value",
    "_queue_sort_key",
]


# =============================================================================
# Constants: Queue Status and Priority Ordering
# =============================================================================

NEXT_CHECK_QUEUE_STATUS_ORDER = (
    "approved-ready",
    "safe-ready",
    "approval-needed",
    "failed",
    "completed",
    "duplicate-or-stale",
)
NEXT_CHECK_QUEUE_PRIORITY_ORDER = {
    "primary": 0,
    "secondary": 1,
    "fallback": 2,
}
QUEUE_STATUS_ORDER = {status: idx for idx, status in enumerate(NEXT_CHECK_QUEUE_STATUS_ORDER)}


# =============================================================================
# Ranking Reason Derivation
# =============================================================================


def _derive_ranking_reason(entry: Mapping[str, object]) -> str | None:
    """Derive a structured ranking-reason/provenance category."""
    if bool(entry.get("duplicateOfExistingEvidence")):
        return "duplicate"

    approval_state = str(entry.get("approvalState") or "").lower()
    if approval_state == "approval-stale":
        return "stale-approval"
    if approval_state == "approval-orphaned":
        return "stale-approval"

    if bool(entry.get("requiresOperatorApproval")):
        return "approval-gated"

    if entry.get("safetyReason"):
        return "safety-gated"
    if entry.get("blockingReason"):
        return "execution-gated"
    if entry.get("gatingReason"):
        return "planner-gated"

    execution_state = str(entry.get("executionState") or "").lower()
    if execution_state == "executed-success":
        return "already-executed"
    if execution_state in ("executed-failed", "timed-out"):
        return "execution-failed"

    priority_label = str(entry.get("priorityLabel") or "").lower()
    if priority_label == "secondary":
        return "deterministic-secondary"
    if priority_label == "fallback":
        return "fallback"

    return None


# =============================================================================
# Priority Rationale Derivation
# =============================================================================


def _derive_priority_rationale(entry: Mapping[str, object]) -> str | None:
    """Derive a compact operator-facing explanation for why an item is in its current state."""
    original_priority_rationale = entry.get("priorityRationale")
    if isinstance(original_priority_rationale, str) and original_priority_rationale.strip():
        return original_priority_rationale.strip()

    if bool(entry.get("duplicateOfExistingEvidence")):
        dup_reason = entry.get("duplicateReason")
        if dup_reason:
            return "Already covered by existing evidence"
        return "Already covered by existing evidence"

    approval_state = str(entry.get("approvalState") or "").lower()
    if approval_state == "approval-stale":
        return "Approval is stale"
    if approval_state == "approval-orphaned":
        return "Approval record orphaned"

    requires_approval = bool(entry.get("requiresOperatorApproval"))
    if requires_approval:
        approval_reason = entry.get("approvalReason")
        if approval_reason:
            return "Approval required before execution"
        return "Approval required before execution"

    safety_reason = entry.get("safetyReason")
    blocking_reason = entry.get("blockingReason")
    gating_reason = entry.get("gatingReason")
    if safety_reason:
        return "Blocked by safety gating"
    if blocking_reason:
        return "Blocked by execution gating"
    if gating_reason:
        return "Blocked by planner gating"

    execution_state = str(entry.get("executionState") or "").lower()
    if execution_state == "executed-success":
        return "Already executed"
    if execution_state in ("executed-failed", "timed-out"):
        return "Execution failed"

    priority_label = str(entry.get("priorityLabel") or "").lower()
    if priority_label == "secondary":
        return "Secondary follow-up"
    if priority_label == "fallback":
        return "Fallback candidate"

    return None


# =============================================================================
# Queue Sorting Helpers
# =============================================================================


def _queue_priority_value(value: object | None) -> int:
    """Get numeric priority value for a priority label."""
    label = str(value or "").lower()
    return NEXT_CHECK_QUEUE_PRIORITY_ORDER.get(label, len(NEXT_CHECK_QUEUE_PRIORITY_ORDER))


def _queue_sort_key(entry: Mapping[str, object]) -> tuple[int, int, int, str]:
    """Compute sort key for queue entries: status, priority, index, id."""
    status = str(entry.get("queueStatus") or "duplicate-or-stale")
    status_index = QUEUE_STATUS_ORDER.get(status, len(QUEUE_STATUS_ORDER))
    priority_index = _queue_priority_value(entry.get("priorityLabel"))
    candidate_index = entry.get("candidateIndex")
    index_value = candidate_index if isinstance(candidate_index, int) else 0
    identifier = str(entry.get("candidateId") or "")
    return status_index, priority_index, index_value, identifier


def _determine_next_check_queue_status(candidate: Mapping[str, object]) -> str:
    """Determine the queue status for a candidate based on its state."""
    requires_approval = bool(candidate.get("requiresOperatorApproval"))
    safe_to_automate = bool(candidate.get("safeToAutomate"))
    approval_state = str(candidate.get("approvalState") or "").lower()
    execution_state = str(candidate.get("executionState") or "unexecuted").lower()
    duplicate = bool(candidate.get("duplicateOfExistingEvidence"))
    if duplicate or approval_state in ("approval-stale", "approval-orphaned"):
        return "duplicate-or-stale"
    if execution_state in ("executed-failed", "timed-out"):
        return "failed"
    if execution_state == "executed-success":
        return "completed"
    if requires_approval:
        if approval_state == "approved":
            return "approved-ready"
        return "approval-needed"
    if safe_to_automate and execution_state == "unexecuted":
        return "safe-ready"
    return "duplicate-or-stale"
