"""Operator worklist payload builders.

These functions derive the ranked operator worklist projection from existing
UI context artifacts (assessments, next-check queue, execution history).
They do not introduce new immutable artifacts; the output is a read-only API projection.

This module is an extraction from api_incident_report.py to reduce its
LLM-friendly file size while preserving backward-compatible re-exports.

Security note:
    All operator-facing text fields are sanitized at serialization boundary
    to prevent internal context markers from leaking to the operator UI.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypedDict, cast

from ..security.kubectl_context import (
    CLUSTER_LOCAL_PRESENTATION_LABEL,
    is_internal_kube_marker,
    sanitize_kubectl_display_command,
    sanitize_operator_text,
)
from .api_incident_report_filtering import (
    filter_artifact_refs_preserving_minimum,
)
from .api_incident_report_worklist_helpers import (
    ExecutionArtifactOverlay,
    _derive_execution_state_from_artifact,
    _match_execution_overlay_to_queue_item,
    _scan_execution_artifacts_for_worklist,
)
from .api_payloads import (
    ArtifactLink,
    FeedbackAdaptationProvenancePayload,
    OperatorWorklistItemPayload,
    OperatorWorklistPayload,
)
from .model import UIIndexContext

logger = logging.getLogger(__name__)

# =============================================================================
# Constants and Item State Definitions
# =============================================================================

_ITEM_STATE_ADVISORY = "advisory"
_ITEM_STATE_APPROVAL_NEEDED = "approval-needed"
_ITEM_STATE_APPROVED = "approved"
_ITEM_STATE_QUEUED = "queued"
_ITEM_STATE_EXECUTED = "executed"
_ITEM_STATE_REVIEWED = "reviewed"

_SOURCE_TYPE_DETERMINISTIC = "deterministic"
_SOURCE_TYPE_PLANNER = "planner"
_SOURCE_TYPE_PROMOTION = "promotion"
_SOURCE_TYPE_VMALERT_ALERT = "vmalert-alert"

# Staleness thresholds in seconds
_STALENESS_FRESH_SECONDS = 5 * 60  # < 5 minutes
_STALENESS_AGING_SECONDS = 30 * 60  # 5-30 minutes
# > 30 minutes = stale

# Adaptation effect constants
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
        summary = usefulness_summary[:100] if usefulness_summary else "Strengthened leading workload hypothesis"
        summary = f"Strengthened leading hypothesis: {summary}"
    elif effect == _ADAPTATION_EFFECT_UNKNOWN_RESOLVED:
        summary = usefulness_summary[:100] if usefulness_summary else "Resolved missing evidence gap"
        summary = f"Resolved evidence gap: {summary}"
    elif effect == _ADAPTATION_EFFECT_NO_MATERIAL_CHANGE:
        summary = usefulness_summary[:100] if usefulness_summary else "No material change to diagnosis"
        summary = f"No material change: {summary}"
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
# Temporal Context Derivation
# =============================================================================


def _parse_timestamp(timestamp_str: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string to datetime."""
    if not timestamp_str:
        return None
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        pass
    return None


class StalenessClass(TypedDict):
    pass


def _derive_temporal_context(
    first_recommended_at: str | None,
    last_state_changed_at: str | None,
    current_run_timestamp: str | None,
) -> tuple[str | None, str | None, int | None, Literal['fresh', 'aging', 'stale', 'unknown'] | None]:
    """Derive temporal context for a worklist item."""
    # Handle insufficient timing data first
    if not first_recommended_at or not current_run_timestamp:
        return first_recommended_at, last_state_changed_at, None, "unknown"
    
    now_dt = _parse_timestamp(current_run_timestamp)
    first_dt = _parse_timestamp(first_recommended_at)
    
    if not now_dt or not first_dt:
        return first_recommended_at, last_state_changed_at, None, "unknown"
    
    delta = now_dt - first_dt
    age_seconds = int(delta.total_seconds())
    
    if age_seconds < 0:
        return first_recommended_at, last_state_changed_at, None, "unknown"
    
    if age_seconds < _STALENESS_FRESH_SECONDS:
        staleness: Literal["fresh", "aging", "stale", "unknown"] = "fresh"
    elif age_seconds < _STALENESS_AGING_SECONDS:
        staleness = "aging"
    else:
        staleness = "stale"
    
    return first_recommended_at, last_state_changed_at, age_seconds, staleness


def _derive_item_state(queue_item: object) -> str | None:
    """Derive canonical item state from queue item execution and approval state."""
    execution_state = getattr(queue_item, "execution_state", None) or ""
    if execution_state in ("executed-success", "executed-failed", "timed-out", "completed"):
        if execution_state in ("executed-success", "completed"):
            return _ITEM_STATE_EXECUTED
        return _ITEM_STATE_REVIEWED
    # Check both snake_case and camelCase for backward compatibility
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
# Operator Worklist Payload Builder
# =============================================================================


def _build_operator_worklist_payload(
    context: UIIndexContext,
    health_root: Path | None = None,
) -> OperatorWorklistPayload | None:
    """Derive a ranked operator worklist from deterministic next checks and queue state."""
    items: list[OperatorWorklistItemPayload] = []
    execution_overlays: tuple[ExecutionArtifactOverlay, ...] = ()
    if health_root is not None:
        run_id = context.run.run_id if hasattr(context.run, "run_id") else ""
        if run_id:
            overlays, _ = _scan_execution_artifacts_for_worklist(health_root, run_id)
            execution_overlays = tuple(overlays)
    deterministic_ids: set[str] = set()
    deterministic = context.run.deterministic_next_checks
    run_timestamp = context.run.timestamp if hasattr(context.run, "timestamp") else None
    if deterministic is not None:
        rank = 1
        for cluster in deterministic.clusters:
            safe_cluster = _sanitize_target_cluster(cluster.label, cluster.context)
            safe_context = _sanitize_target_context(cluster.context)
            if safe_cluster is None:
                rank += len(list(cluster.deterministic_next_check_summaries))
                continue
            for summary in cluster.deterministic_next_check_summaries:
                title_str = sanitize_operator_text(summary.description)
                title_str = title_str if title_str is not None else summary.description
                item_id = f"deterministic-{safe_cluster}-{rank}"
                deterministic_ids.add(item_id)
                item_state = _ITEM_STATE_ADVISORY
                ranking_reason = _derive_worklist_ranking_reason(
                    source_type=_SOURCE_TYPE_DETERMINISTIC,
                    item_state=item_state,
                    execution_state=None,
                    is_primary_triage=summary.is_primary_triage,
                    urgency=summary.urgency,
                    priority_label=None,
                    command=None,
                    workstream=summary.workstream,
                )
                assessment_timestamp = None
                if cluster.assessment_artifact_path:
                    assessment_timestamp = context.latest_assessment.timestamp if context.latest_assessment else None
                first_recommended_at = assessment_timestamp
                last_state_changed_at: str | None = None
                first_rec, last_change, age_sec, staleness = _derive_temporal_context(
                    first_recommended_at=first_recommended_at,
                    last_state_changed_at=last_state_changed_at,
                    current_run_timestamp=run_timestamp,
                )
                items.append({
                    "id": item_id,
                    "rank": rank,
                    "workstream": summary.workstream,
                    "title": title_str,
                    "description": sanitize_operator_text(
                        f"Owner: {summary.owner}; method: {summary.method}; evidence needed: {', '.join(summary.evidence_needed)}"
                    ),
                    "command": None,
                    "targetCluster": safe_cluster,
                    "targetContext": safe_context,
                    "reason": sanitize_operator_text(summary.why_now),
                    "expectedEvidence": sanitize_operator_text(", ".join(summary.evidence_needed)),
                    "safetyNote": sanitize_operator_text(
                        f"Urgency: {summary.urgency}; primary triage: {summary.is_primary_triage}"
                    ),
                    "itemState": item_state,
                    "approvalState": None,
                    "executionState": None,
                    "feedbackState": None,
                    "sourceType": _SOURCE_TYPE_DETERMINISTIC,
                    "mergedSources": None,
                    "sourceArtifactRefs": [
                        {"label": "Assessment", "path": path}
                        for path in [cluster.assessment_artifact_path, cluster.drilldown_artifact_path]
                        if path
                    ],
                    "rankingReason": ranking_reason,
                    "firstRecommendedAt": first_rec,
                    "lastStateChangedAt": last_change,
                    "recommendationAgeSeconds": age_sec,
                    "stalenessClass": staleness,
                })
                rank += 1
    queue_items = context.run.next_check_queue
    for queue_item in queue_items:
        item_id = queue_item.candidate_id or f"queue-{queue_item.description}"
        item_description = queue_item.description
        matched_deterministic = False
        if item_id in deterministic_ids:
            for existing in items:
                if existing.get("id") == item_id:
                    existing["approvalState"] = queue_item.approval_state
                    existing["executionState"] = queue_item.execution_state
                    existing["feedbackState"] = queue_item.outcome_status
                    existing["itemState"] = _derive_item_state(queue_item) or _ITEM_STATE_ADVISORY
                    existing["sourceType"] = _SOURCE_TYPE_PLANNER
                    existing["mergedSources"] = [_SOURCE_TYPE_DETERMINISTIC, _SOURCE_TYPE_PLANNER]
                    if queue_item.plan_artifact_path:
                        refs = list(existing.get("sourceArtifactRefs") or [])
                        refs.append({"label": "Next-Check Plan", "path": queue_item.plan_artifact_path})
                        existing["sourceArtifactRefs"] = refs
                    matched_deterministic = True
                    break
            if matched_deterministic:
                continue
        if not matched_deterministic and item_description:
            for existing in items:
                if existing.get("sourceType") == _SOURCE_TYPE_DETERMINISTIC and existing.get("title") == item_description:
                    existing["approvalState"] = queue_item.approval_state
                    existing["executionState"] = queue_item.execution_state
                    existing["feedbackState"] = queue_item.outcome_status
                    existing["itemState"] = _derive_item_state(queue_item) or _ITEM_STATE_ADVISORY
                    existing["sourceType"] = _SOURCE_TYPE_PLANNER
                    existing["mergedSources"] = [_SOURCE_TYPE_DETERMINISTIC, _SOURCE_TYPE_PLANNER]
                    if queue_item.plan_artifact_path:
                        refs = list(existing.get("sourceArtifactRefs") or [])
                        refs.append({"label": "Next-Check Plan", "path": queue_item.plan_artifact_path})
                        existing["sourceArtifactRefs"] = refs
                    matched_deterministic = True
                    break
            if matched_deterministic:
                continue
        existing_queue_ids = {
            cast(str | None, item.get("id"))
            for item in items
            if cast(str | None, item.get("sourceType")) == _SOURCE_TYPE_PLANNER
        }
        if item_id in existing_queue_ids:
            for existing in items:
                if existing.get("id") == item_id:
                    existing["executionState"] = queue_item.execution_state
                    existing["feedbackState"] = queue_item.outcome_status
                    existing["itemState"] = _derive_item_state(queue_item) or _ITEM_STATE_QUEUED
                    if queue_item.latest_artifact_path:
                        refs = list(existing.get("sourceArtifactRefs") or [])
                        refs.append({"label": "Next-Check Execution", "path": queue_item.latest_artifact_path})
                        existing["sourceArtifactRefs"] = refs
            continue
        queue_title = sanitize_operator_text(queue_item.description)
        queue_title = queue_title if queue_title is not None else queue_item.description
        source_type = _SOURCE_TYPE_PLANNER
        if queue_item.source_type == "deterministic":
            source_type = _SOURCE_TYPE_PROMOTION
        artifact_refs: list[ArtifactLink] = []
        if queue_item.plan_artifact_path:
            artifact_refs.append({"label": "Next-Check Plan", "path": queue_item.plan_artifact_path})
        if queue_item.latest_artifact_path:
            artifact_refs.append({"label": "Next-Check Execution", "path": queue_item.latest_artifact_path})
        queue_item_state = _derive_item_state(queue_item) or _ITEM_STATE_QUEUED
        command = sanitize_kubectl_display_command(queue_item.command_preview) if queue_item.command_preview else None
        ranking_reason = _derive_worklist_ranking_reason(
            source_type=source_type,
            item_state=queue_item_state,
            execution_state=queue_item.execution_state,
            is_primary_triage=None,
            urgency=None,
            priority_label=queue_item.priority_label,
            command=command,
            workstream=queue_item.workstream,
        )
        usefulness_class: str | None = None
        usefulness_summary: str | None = None
        result_summary: str | None = None
        if hasattr(queue_item, "usefulness_class"):
            usefulness_class = getattr(queue_item, "usefulness_class", None)
        if hasattr(queue_item, "usefulness_summary"):
            usefulness_summary = getattr(queue_item, "usefulness_summary", None)
        if hasattr(queue_item, "result_summary"):
            result_summary = getattr(queue_item, "result_summary", None)
        feedback_adaptation_provenance: dict[str, object] | None = None
        if hasattr(queue_item, "feedback_adaptation_provenance") and queue_item.feedback_adaptation_provenance:
            fp = queue_item.feedback_adaptation_provenance
            if hasattr(fp, "feedback_adaptation") and fp.feedback_adaptation:
                feedback_adaptation_provenance = {
                    "feedbackAdaptation": fp.feedback_adaptation,
                    "adaptationReason": fp.adaptation_reason,
                    "adaptationEffect": getattr(fp, "adaptation_effect", None),
                    "adaptationSummary": getattr(fp, "adaptation_summary", None),
                    "originalBonus": fp.original_bonus,
                    "suppressedBonus": fp.suppressed_bonus,
                    "penaltyApplied": fp.penalty_applied,
                    "explanation": fp.explanation,
                }
        if not feedback_adaptation_provenance and usefulness_class:
            feedback_adaptation_provenance = _derive_adaptation_provenance(
                usefulness_class=usefulness_class,
                usefulness_summary=usefulness_summary,
                execution_result_summary=result_summary,
            )
        first_recommended_at = queue_item.plan_artifact_timestamp if hasattr(queue_item, "plan_artifact_timestamp") and queue_item.plan_artifact_timestamp else None
        if not first_recommended_at and queue_item.plan_artifact_path:
            first_recommended_at = None
        last_state_changed_at = queue_item.latest_timestamp if hasattr(queue_item, "latest_timestamp") and queue_item.latest_timestamp else None
        first_rec, last_change, age_sec, staleness = _derive_temporal_context(
            first_recommended_at=first_recommended_at,
            last_state_changed_at=last_state_changed_at,
            current_run_timestamp=run_timestamp,
        )
        items.append({
            "id": item_id,
            "rank": len(items) + 1,
            "workstream": queue_item.workstream,
            "title": queue_title,
            "description": sanitize_operator_text(queue_item.source_reason),
            "command": command,
            "targetCluster": _sanitize_target_cluster(queue_item.target_cluster, queue_item.target_context),
            "targetContext": _sanitize_target_context(queue_item.target_context),
            "reason": sanitize_operator_text(queue_item.source_reason),
            "expectedEvidence": sanitize_operator_text(queue_item.expected_signal),
            "safetyNote": sanitize_operator_text(queue_item.safety_reason),
            "itemState": queue_item_state,
            "approvalState": queue_item.approval_state,
            "executionState": queue_item.execution_state,
            "feedbackState": queue_item.outcome_status,
            "sourceType": source_type,
            "mergedSources": None,
            "sourceArtifactRefs": artifact_refs,
            "rankingReason": ranking_reason,
            "feedbackAdaptationProvenance": cast("FeedbackAdaptationProvenancePayload | None", feedback_adaptation_provenance),
            "firstRecommendedAt": first_rec,
            "lastStateChangedAt": last_change,
            "recommendationAgeSeconds": age_sec,
            "stalenessClass": staleness,
        })
    vmalert_rule_state = context.vmalert_rule_state
    if vmalert_rule_state is not None:
        seen_vmalert_keys: set[tuple[str, str | None, str | None, str | None]] = set()
        for alert in vmalert_rule_state.alerts:
            if alert.state != "firing" or alert.severity != "critical":
                continue
            dedupe_key = (alert.alertname, alert.namespace, alert.workload, alert.source_endpoint)
            if dedupe_key in seen_vmalert_keys:
                continue
            seen_vmalert_keys.add(dedupe_key)
            ns_suffix = f"-{alert.namespace}" if alert.namespace else ""
            wl_suffix = f"-{alert.workload}" if alert.workload else ""
            ep_suffix = f"-{alert.source_endpoint}" if alert.source_endpoint else ""
            item_id = f"vmalert-critical-{alert.alertname}{ns_suffix}{wl_suffix}{ep_suffix}"
            title = f"Critical vmalert alert firing: {alert.alertname}"
            if alert.namespace or alert.workload:
                location_parts = [p for p in [alert.namespace, alert.workload] if p]
                title += f" ({'/'.join(location_parts)})"
            description_parts = []
            if alert.namespace:
                description_parts.append(f"namespace={alert.namespace}")
            if alert.workload:
                description_parts.append(f"workload={alert.workload}")
            if alert.instance:
                description_parts.append(f"instance={alert.instance}")
            description = "; ".join(description_parts) if description_parts else None
            reason = f"vmalert reported alert '{alert.alertname}' as firing with severity=critical"
            if alert.source_endpoint:
                reason += f" (source: {alert.source_endpoint})"
            vmalert_artifact_refs: list[ArtifactLink] = []
            if health_root is not None:
                run_id = context.run.run_id if hasattr(context.run, "run_id") else ""
                if run_id:
                    artifact_path = f"{run_id}-vmalert-rule-state.json"
                    vmalert_artifact_refs.append({"label": "VMAlert Rule State", "path": artifact_path})
            ranking_reason = "Critical vmalert alert firing; requires operator attention"
            item_rank = len(items) + 1
            items.append({
                "id": item_id,
                "rank": item_rank,
                "workstream": "incident",
                "title": title,
                "description": description,
                "command": None,
                "targetCluster": alert.cluster_label,
                "targetContext": None,
                "reason": reason,
                "expectedEvidence": None,
                "safetyNote": f"Severity: {alert.severity}; State: {alert.state}",
                "itemState": _ITEM_STATE_ADVISORY,
                "approvalState": None,
                "executionState": None,
                "feedbackState": None,
                "sourceType": _SOURCE_TYPE_VMALERT_ALERT,
                "mergedSources": None,
                "sourceArtifactRefs": vmalert_artifact_refs,
                "rankingReason": ranking_reason,
                "firstRecommendedAt": None,
                "lastStateChangedAt": None,
                "recommendationAgeSeconds": None,
                "stalenessClass": None,
            })
    if not items:
        return None
    for item in items:
        current_execution_state = item.get("executionState") or ""
        if current_execution_state in ("executed-success", "executed-failed", "timed-out", "completed"):
            continue
        item_candidate_id = item.get("id")
        item_candidate_index = None
        item_command_family = None
        item_target_cluster = item.get("targetCluster")
        description = item.get("description") or ""
        if "kubectl" in description.lower():
            parts = description.lower().split("kubectl")
            if len(parts) > 1:
                cmd_part = parts[1].split()[0] if parts[1].strip() else ""
                if cmd_part:
                    item_command_family = cmd_part
        for queue_item in queue_items:
            queue_item_id = queue_item.candidate_id or f"queue-{queue_item.description}"
            if queue_item_id == item_candidate_id:
                item_candidate_index = queue_item.candidate_index if hasattr(queue_item, "candidate_index") else None
                if hasattr(queue_item, "suggested_command_family") and queue_item.suggested_command_family:
                    item_command_family = queue_item.suggested_command_family
                break
        for overlay in execution_overlays:
            if _match_execution_overlay_to_queue_item(
                overlay=overlay,
                queue_item_candidate_id=str(item_candidate_id) if item_candidate_id else None,
                queue_item_candidate_index=item_candidate_index,
                queue_item_command_family=item_command_family,
                queue_item_target_cluster=item_target_cluster,
            ):
                derived_execution_state = _derive_execution_state_from_artifact(overlay.status)
                item["executionState"] = derived_execution_state
                item["itemState"] = _ITEM_STATE_EXECUTED
                if overlay.timestamp:
                    item["lastStateChangedAt"] = overlay.timestamp
                if overlay.artifact_path:
                    refs = list(item.get("sourceArtifactRefs") or [])
                    artifact_exists = any(ref.get("path") == overlay.artifact_path for ref in refs)
                    if not artifact_exists:
                        refs.append({"label": "Next-Check Execution", "path": overlay.artifact_path})
                        item["sourceArtifactRefs"] = refs
                item["rankingReason"] = _derive_worklist_ranking_reason(
                    source_type=item.get("sourceType"),
                    item_state=_ITEM_STATE_EXECUTED,
                    execution_state=derived_execution_state,
                    is_primary_triage=None,
                    urgency=None,
                    priority_label=cast("str | None", item.get("priorityLabel")),
                    command=item.get("command"),
                    workstream=item.get("workstream"),
                )
                break
    for item in items:
        refs = item.get("sourceArtifactRefs") or []
        filtered_refs = filter_artifact_refs_preserving_minimum(refs)
        item["sourceArtifactRefs"] = filtered_refs
    completed = sum(
        1
        for item in items
        if item.get("itemState") in (_ITEM_STATE_EXECUTED, _ITEM_STATE_REVIEWED)
        or item.get("executionState") in ("executed-success", "completed")
    )
    blocked = sum(
        1
        for item in items
        if item.get("itemState") == _ITEM_STATE_APPROVAL_NEEDED
        or item.get("approvalState") == "approval-required"
        or item.get("executionState") == "blocked"
    )
    return {
        "items": items,
        "totalItems": len(items),
        "completedItems": completed,
        "pendingItems": len(items) - completed - blocked,
        "blockedItems": blocked,
    }
