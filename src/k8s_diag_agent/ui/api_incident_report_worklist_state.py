"""Item state derivation and sanitization helpers for operator worklist items.

This module provides item state classification, adaptation provenance derivation,
ranking rationale, and target sanitization for worklist items.

This module is an extraction from api_incident_report_worklist.py to reduce its
LLM-friendly file size while preserving backward-compatible re-exports.
"""

from __future__ import annotations

from ..security.kubectl_context import (
    CLUSTER_LOCAL_PRESENTATION_LABEL,
    is_internal_kube_marker,
)

# =============================================================================
# Constants - Item States
# =============================================================================

_ITEM_STATE_ADVISORY = "advisory"
_ITEM_STATE_APPROVAL_NEEDED = "approval-needed"
_ITEM_STATE_APPROVED = "approved"
_ITEM_STATE_QUEUED = "queued"
_ITEM_STATE_EXECUTED = "executed"
_ITEM_STATE_REVIEWED = "reviewed"


# =============================================================================
# Constants - Source Types
# =============================================================================

_SOURCE_TYPE_DETERMINISTIC = "deterministic"
_SOURCE_TYPE_PLANNER = "planner"
_SOURCE_TYPE_PROMOTION = "promotion"
_SOURCE_TYPE_VMALERT_ALERT = "vmalert-alert"


# =============================================================================
# Constants - Adaptation Effects
# =============================================================================

_ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED = "hypothesis_strengthened"
_ADAPTATION_EFFECT_HYPOTHESIS_WEAKENED = "hypothesis_weakened"
_ADAPTATION_EFFECT_UNKNOWN_RESOLVED = "unknown_resolved"
_ADAPTATION_EFFECT_RECOMMENDATION_PROMOTED = "recommendation_promoted"
_ADAPTATION_EFFECT_RECOMMENDATION_DEPRIORITIZED = "recommendation_deprioritized"
_ADAPTATION_EFFECT_NO_MATERIAL_CHANGE = "no_material_change"

_USE_TO_ADAPTATION_MAP: dict[str, str] = {
    "useful": _ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED,
    "partial": _ADAPTATION_EFFECT_UNKNOWN_RESOLVED,
    "noisy": _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE,
    "empty": _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE,
}


# =============================================================================
# Sanitization Helpers
# =============================================================================


def _sanitize_target_cluster(cluster: str | None, context: str | None = None) -> str | None:
    """Sanitize a cluster label for operator-facing display."""
    if cluster is None:
        return None
    if is_internal_kube_marker(cluster):
        if context and not is_internal_kube_marker(context):
            return context
        return CLUSTER_LOCAL_PRESENTATION_LABEL
    return cluster


def _sanitize_target_context(context: str | None) -> str | None:
    """Sanitize a context value for operator-facing display."""
    if context is None:
        return None
    if is_internal_kube_marker(context):
        return CLUSTER_LOCAL_PRESENTATION_LABEL
    return context


# =============================================================================
# Adaptation Provenance Derivation
# =============================================================================


def _derive_adaptation_provenance(
    usefulness_class: str | None,
    usefulness_summary: str | None,
    execution_result_summary: str | None,
) -> dict[str, object] | None:
    """Derive adaptation provenance from execution feedback."""
    if not usefulness_class:
        return None
    effect = _USE_TO_ADAPTATION_MAP.get(usefulness_class)
    if not effect:
        return None
    if effect == _ADAPTATION_EFFECT_HYPOTHESIS_STRENGTHENED:
        if usefulness_summary:
            summary = f"Strengthened leading hypothesis: {usefulness_summary[:100]}"
        else:
            summary = "Strengthened leading workload hypothesis"
    elif effect == _ADAPTATION_EFFECT_UNKNOWN_RESOLVED:
        if usefulness_summary:
            summary = f"Resolved evidence gap: {usefulness_summary[:100]}"
        else:
            summary = "Resolved missing evidence gap"
    elif effect == _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE:
        if usefulness_summary:
            summary = f"No material change: {usefulness_summary[:100]}"
        else:
            summary = "No material change to diagnosis"
    else:
        summary = None
    return {
        "feedbackAdaptation": True,
        "adaptationReason": f"usefulness:{usefulness_class}",
        "adaptationEffect": effect,
        "adaptationSummary": summary,
        "originalBonus": 0,
        "suppressedBonus": 0,
        "penaltyApplied": 0,
        "explanation": execution_result_summary,
    }


# =============================================================================
# Ranking Rationale Derivation
# =============================================================================


def _derive_worklist_ranking_reason(
    source_type: str | None,
    item_state: str | None,
    execution_state: str | None,
    is_primary_triage: bool | None,
    urgency: str | None,
    priority_label: str | None,
    command: str | None,
    workstream: str | None,
) -> str | None:
    """Derive a concise ranking rationale for a worklist item."""
    if item_state in (_ITEM_STATE_EXECUTED, _ITEM_STATE_REVIEWED):
        return "Already executed; retained for result review"
    if is_primary_triage and source_type == _SOURCE_TYPE_DETERMINISTIC:
        if urgency and urgency != "unknown":
            return f"Primary triage for current degraded workload ({urgency} urgency)"
        return "Primary triage for current degraded workload"
    if workstream == "drift":
        return "Fleet-level drift affects comparable clusters"
    if source_type in (_SOURCE_TYPE_PLANNER, _SOURCE_TYPE_PROMOTION) and command is not None:
        if item_state == _ITEM_STATE_APPROVAL_NEEDED:
            return "Pending operator approval before execution"
        if item_state == _ITEM_STATE_APPROVED:
            return "Approved and ready for execution"
        if item_state == _ITEM_STATE_QUEUED:
            if priority_label in ("primary", "critical"):
                return "Executable now; likely to confirm the leading hypothesis"
            return "Queued for automated execution"
        if priority_label in ("primary", "critical"):
            return "Executable now; likely to confirm the leading hypothesis"
        return "Planner-selected check; executable now"
    if source_type == _SOURCE_TYPE_DETERMINISTIC:
        if urgency and urgency != "unknown":
            return f"Advisory check; {urgency} urgency for evidence collection"
        return "Advisory check; method-based diagnostics"
    return None


# =============================================================================
# Item State Derivation
# =============================================================================


def _derive_item_state(queue_item: object) -> str | None:
    """Derive canonical item state from queue item execution and approval state.

    Restores exact old behavior:
    - usefulness_class present => reviewed
    - execution_state in executed-success/executed-failed/timed-out => executed
    """
    # Check usefulness_class first - any usefulness review means reviewed
    usefulness_class = getattr(queue_item, "usefulness_class", None)
    if usefulness_class:
        return _ITEM_STATE_REVIEWED

    execution_state = getattr(queue_item, "execution_state", None) or ""
    if execution_state in ("executed-success", "executed-failed", "timed-out", "completed"):
        return _ITEM_STATE_EXECUTED

    # Check approval state
    requires_approval = getattr(queue_item, "requires_operator_approval", False) or getattr(queue_item, "requires_approval", False)
    approval_state = getattr(queue_item, "approval_state", None) or ""

    if approval_state == "reviewed":
        return _ITEM_STATE_REVIEWED
    if requires_approval and approval_state == "approved":
        return _ITEM_STATE_APPROVED
    if requires_approval and approval_state != "approved":
        return _ITEM_STATE_APPROVAL_NEEDED

    safe_to_automate = getattr(queue_item, "safe_to_automate", False)
    if safe_to_automate and execution_state == "unexecuted":
        return _ITEM_STATE_QUEUED
    if execution_state == "unexecuted":
        return _ITEM_STATE_QUEUED

    return None
