"""Queue explanation and status derivation for planner candidates.

This module provides pure derivation helpers for building queue explanations
when the next-check queue is empty or needs contextual framing.

Responsibilities:
- Determine queue explanation status based on plan and review state
- Collect human-readable reasons for the explanation status
- Derive planner artifact paths for queue explanation
- Build comprehensive queue explanation with cluster state and recommendations
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

# =============================================================================
# Re-exports for backward compatibility
# =============================================================================

__all__ = [
    "_PLANNER_ARTIFACT_KEYS",
    "_NEXT_CHECK_QUEUE_EXPLANATION_HINTS",
    "_build_candidate_accounting",
    "_build_next_check_queue_explanation",
    "_collect_queue_explanation_reason",
    "_derive_queue_artifact_path",
    "_pluck_plan_candidates",
    "_summarize_deterministic_checks",
    "_determine_queue_explanation_status",
]


# =============================================================================
# Constants: Queue Explanation Hints
# =============================================================================

_NEXT_CHECK_QUEUE_EXPLANATION_HINTS: dict[str, str] = {
    "planner-present-with-candidates": (
        "Planner candidates are available; clear queue filters or focus on a cluster to surface them."
    ),
    "queue-exhausted-by-completion-or-filtering": (
        "All planner candidates were completed or filtered out; check deterministic evidence for remaining work."
    ),
    "enrichment-succeeded-without-next-checks": (
        "Review deterministic Cluster Detail next-checks since enrichment returned no planner candidates."
    ),
    "enrichment-failed": (
        "Inspect the failed review enrichment artifact before relying on deterministic Cluster Detail next checks."
    ),
    "enrichment-not-attempted": (
        "Inspect Review Enrichment configuration or provider registration to understand why the planner didn't run."
    ),
    "planner-missing-unexpectedly": (
        "The planner artifact is missing despite enrichment success; inspect the enrichment artifact and deterministic evidence chain."
    ),
}

_PLANNER_ARTIFACT_KEYS = ("artifactPath", "enrichmentArtifactPath", "reviewPath")


# =============================================================================
# Candidate Extraction Helpers
# =============================================================================


def _pluck_plan_candidates(plan_entry: Mapping[str, object] | None) -> list[Mapping[str, object]]:
    """Extract candidate list from plan entry."""
    if not isinstance(plan_entry, Mapping):
        return []
    raw = plan_entry.get("candidates")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return [entry for entry in raw if isinstance(entry, Mapping)]
    return []


def _summarize_deterministic_checks(
    deterministic_next_checks: Mapping[str, object] | None,
    clusters: Sequence[dict[str, object]],
    drilldown_availability: dict[str, object],
) -> dict[str, object]:
    """Summarize deterministic check state for queue explanation."""
    deterministic_total = 0
    deterministic_clusters = 0
    if isinstance(deterministic_next_checks, Mapping):
        deterministic_total = _coerce_int_value(
            deterministic_next_checks.get("totalNextCheckCount")
        )
        deterministic_clusters = _coerce_int_value(
            deterministic_next_checks.get("clusterCount")
        )
    degraded_labels = [
        str(cluster.get("label"))
        for cluster in clusters
        if str(cluster.get("health_rating") or "").lower() == "degraded"
    ]
    drilldown_ready = _coerce_int_value(drilldown_availability.get("available", 0))
    return {
        "degradedClusterCount": len(degraded_labels),
        "degradedClusterLabels": degraded_labels,
        "deterministicNextCheckCount": deterministic_total,
        "deterministicClusterCount": deterministic_clusters,
        "drilldownReadyCount": drilldown_ready,
    }


def _coerce_int_value(value: object | None) -> int:
    """Coerce a value to int, returning 0 for None/invalid."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _build_candidate_accounting(plan_entry: Mapping[str, object] | None) -> dict[str, int]:
    """Build accounting of candidate statuses for queue explanation."""
    candidates = _pluck_plan_candidates(plan_entry)
    safe = approval_needed = duplicate = completed = stale_orphaned = 0
    approval_needed_states = {"approval-needed"}
    for candidate in candidates:
        status = str(candidate.get("queueStatus") or "").lower()
        if status in ("safe-ready", "approved-ready"):
            safe += 1
        if status in approval_needed_states:
            approval_needed += 1
        if status == "duplicate-or-stale":
            duplicate += 1
        if status == "completed":
            completed += 1
        approval_state = str(candidate.get("approvalState") or "").lower()
        if approval_state in ("approval-stale", "approval-orphaned") or status == "duplicate-or-stale":
            stale_orphaned += 1
    orphaned = plan_entry.get("orphanedApprovalCount") if isinstance(plan_entry, Mapping) else 0
    orphaned_value = _coerce_int_value(orphaned)
    generated = _coerce_int_value(
        plan_entry.get("candidateCount") if isinstance(plan_entry, Mapping) else len(candidates)
    )
    return {
        "generated": generated,
        "safe": safe,
        "approvalNeeded": approval_needed,
        "duplicate": duplicate,
        "completed": completed,
        "staleOrphaned": stale_orphaned,
        "orphanedApprovals": orphaned_value,
    }


# =============================================================================
# Queue Explanation
# =============================================================================


def _determine_queue_explanation_status(
    plan_entry: Mapping[str, object] | None,
    review_entry: Mapping[str, object] | None,
    review_status: Mapping[str, object] | None,
) -> str:
    """Determine the queue explanation status based on plan and review state."""
    candidates = _pluck_plan_candidates(plan_entry)
    if candidates:
        return "planner-present-with-candidates"
    if plan_entry and not candidates:
        return "queue-exhausted-by-completion-or-filtering"
    if review_entry:
        entry_status = str(review_entry.get("status") or "").lower()
        next_checks = review_entry.get("nextChecks")
        has_checks = (
            isinstance(next_checks, Sequence)
            and not isinstance(next_checks, (str, bytes, bytearray))
            and bool(next_checks)
        )
        if entry_status != "success":
            return "enrichment-failed"
        if has_checks:
            return "planner-missing-unexpectedly"
        return "enrichment-succeeded-without-next-checks"
    if review_status:
        state = str(review_status.get("status") or "").lower()
        if state in (
            "policy-disabled",
            "provider-missing",
            "adapter-unavailable",
            "awaiting-next-run",
        ):
            return "enrichment-not-attempted"
        return "enrichment-not-attempted"
    return "enrichment-not-attempted"


def _collect_queue_explanation_reason(
    plan_entry: Mapping[str, object] | None,
    review_entry: Mapping[str, object] | None,
    review_status: Mapping[str, object] | None,
) -> str | None:
    """Collect the human-readable reason for the queue explanation status."""
    if plan_entry and isinstance(plan_entry, Mapping):
        summary = plan_entry.get("summary") or plan_entry.get("reason")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    if review_entry and isinstance(review_entry, Mapping):
        error = review_entry.get("errorSummary")
        if isinstance(error, str) and error.strip():
            return error.strip()
        summary = review_entry.get("reason")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    if review_status and isinstance(review_status, Mapping):
        reason = review_status.get("reason")
        if isinstance(reason, str) and reason.strip():
            return reason.strip()
    return None


def _derive_queue_artifact_path(
    plan_entry: Mapping[str, object] | None,
    review_entry: Mapping[str, object] | None,
) -> str | None:
    """Derive the planner artifact path for queue explanation."""
    if plan_entry and isinstance(plan_entry, Mapping):
        path = plan_entry.get("artifactPath")
        if isinstance(path, str) and path:
            return path
    if review_entry and isinstance(review_entry, Mapping):
        for key in _PLANNER_ARTIFACT_KEYS:
            value = review_entry.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _build_next_check_queue_explanation(
    clusters: Sequence[dict[str, object]],
    drilldown_availability: dict[str, object],
    plan_entry: Mapping[str, object] | None,
    queue: list[dict[str, object]],
    review_entry: Mapping[str, object] | None,
    review_status: Mapping[str, object] | None,
    deterministic_next_checks: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Build queue explanation when queue is empty."""
    if queue:
        return None
    status = _determine_queue_explanation_status(plan_entry, review_entry, review_status)
    reason = _collect_queue_explanation_reason(plan_entry, review_entry, review_status)
    cluster_state = _summarize_deterministic_checks(
        deterministic_next_checks, clusters, drilldown_availability
    )
    candidate_accounting = _build_candidate_accounting(plan_entry)
    next_action_hint = _NEXT_CHECK_QUEUE_EXPLANATION_HINTS.get(status)
    recommended_actions: list[str] = []
    if next_action_hint:
        recommended_actions.append(next_action_hint)
    if cluster_state.get("deterministicNextCheckCount"):
        recommended_actions.append(
            "Inspect deterministic Cluster Detail next checks to close the remaining evidence gaps."
        )
    return {
        "status": status,
        "reason": reason,
        "hint": next_action_hint,
        "plannerArtifactPath": _derive_queue_artifact_path(plan_entry, review_entry),
        "clusterState": cluster_state,
        "candidateAccounting": candidate_accounting,
        "deterministicNextChecksAvailable": bool(
            cluster_state.get("deterministicNextCheckCount")
        ),
        "recommendedNextActions": recommended_actions,
    }
