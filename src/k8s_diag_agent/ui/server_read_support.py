"""Read-only support helpers for the UI server.

This module contains read-only helper functions extracted from server.py.
These helpers perform no mutation and are used by server_reads.py to build
read-side payloads.

Keep behavior unchanged: no logic changes, no response shape changes.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)


def _get_field_with_fallback(data: dict[str, object], *keys: str) -> object | None:
    """Get a value from dict with fallback keys, preserving false/0 values.

    Checks each key in order and returns the first one that exists (even if falsy).
    Returns None if no key is found.
    """
    for key in keys:
        if key in data:
            return data[key]
    return None


def _get_field_with_default(data: dict[str, object], default: object, *keys: str) -> object:
    """Get a value from dict with fallback keys, returning default if not found.

    Checks each key in order and returns the first one that exists (even if falsy).
    Returns the provided default value if no key is found.
    """
    for key in keys:
        if key in data:
            return data[key]
    return default


def _load_alertmanager_review_artifacts(
    external_analysis_dir: Path, run_id: str
) -> dict[str, dict[str, object]]:
    """Discover Alertmanager review artifacts and return latest per source execution artifact.

    Scans external-analysis/ for review artifacts matching:
    {run_id}-next-check-execution-alertmanager-review-*.json

    Returns a dict mapping source_artifact path -> latest review artifact data.
    If multiple reviews exist for the same source, returns the most recent one.

    Each review artifact is enriched with the review file's relative path as
    `artifact_path` so that callers can include the review artifact path in
    merged entries (not just the source artifact path).

    Args:
        external_analysis_dir: Path to external-analysis directory
        run_id: The run ID to filter by

    Returns:
        Dict mapping source artifact relative path -> latest review artifact data,
        with each review also containing `artifact_path` = relative path of the review file
    """
    from ..external_analysis.artifact import ExternalAnalysisPurpose

    reviews_by_source: dict[str, dict[str, object]] = {}

    if not external_analysis_dir.exists():
        return reviews_by_source

    # Find all Alertmanager review artifacts for this run
    review_pattern = f"{run_id}-next-check-execution-alertmanager-review-*.json"
    for review_file in external_analysis_dir.glob(review_pattern):
        try:
            review_data = json.loads(review_file.read_text(encoding="utf-8"))
            if not isinstance(review_data, dict):
                continue

            purpose = review_data.get("purpose")
            # Accept both the formal purpose constant and the legacy literal for backward compatibility
            formal_purpose = ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION_ALERTMANAGER_REVIEW.value
            if purpose != formal_purpose and purpose != "next-check-execution-alertmanager-review":
                continue

            # Get source artifact path (the execution artifact this review is for)
            source_artifact = review_data.get("source_artifact")
            if not isinstance(source_artifact, str):
                continue

            # Inject the review file's relative path as artifact_path
            # This allows callers to include the review artifact path, not just the source
            review_data["artifact_path"] = str(review_file.relative_to(external_analysis_dir.parent))

            # Get review timestamp for determining "latest"
            reviewed_at = review_data.get("reviewed_at", "")
            existing = reviews_by_source.get(source_artifact)
            if existing is None or reviewed_at > existing.get("reviewed_at", ""):
                reviews_by_source[source_artifact] = review_data

        except Exception:
            continue

    return reviews_by_source


def _merge_alertmanager_review_into_history_entry(
    entry: Mapping[str, object], review: Mapping[str, object] | None
) -> dict[str, object]:
    """Merge Alertmanager review data into an execution history entry.

    If a review exists for this entry's source artifact, merge the relevance
    judgment and provenance into the entry for API serialization.

    Args:
        entry: The execution history entry dict
        review: The latest Alertmanager review artifact data, or None if no review

    Returns:
        Entry dict with alertmanager review fields merged in
    """
    if review is None:
        return dict(entry)

    # Create merged entry
    merged = dict(entry)

    # Add Alertmanager relevance judgment from review
    relevance = review.get("alertmanager_relevance")
    if isinstance(relevance, str):
        merged["alertmanagerRelevance"] = relevance

    summary = review.get("alertmanager_relevance_summary")
    if isinstance(summary, str):
        merged["alertmanagerRelevanceSummary"] = summary

    # Add provenance preserved from execution artifact
    provenance = review.get("alertmanager_provenance")
    if provenance is not None:
        merged["alertmanagerProvenance"] = provenance

    # Add review metadata
    reviewed_at = review.get("reviewed_at")
    if isinstance(reviewed_at, str):
        merged["alertmanagerReviewedAt"] = reviewed_at

    review_artifact = review.get("artifact_path") or review.get("source_artifact")
    if isinstance(review_artifact, str):
        merged["alertmanagerReviewArtifactPath"] = review_artifact

    return merged


def _build_review_enrichment_status_for_past_run(
    run_config: dict[str, object] | None,
) -> dict[str, object] | None:
    """Build review enrichment status for past runs using run-scoped config.

    This is a simplified version of health/ui's _build_review_enrichment_status
    that only checks run-level config (from review artifact), not current policy.
    For past runs, we want to show the status based on what was configured
    for that specific run, independent of the current policy.

    Args:
        run_config: The review_enrichment config dict from the review artifact,
                    or None if not present.

    Returns:
        Status dict with fields: status, reason, policyEnabled, providerConfigured,
        adapterAvailable, runEnabled, runProvider.
        Returns None only if run_config is None (no info available).
    """
    if run_config is None:
        return None

    enabled = run_config.get("enabled")
    provider = run_config.get("provider")

    # Strict boolean parsing: only treat actual booleans as authoritative.
    # Values like "false", 1, 0, or other junk are treated as unknown,
    # preventing misleading truth values.
    run_enabled: bool | None
    if isinstance(enabled, bool):
        run_enabled = enabled
    else:
        # Non-bool values (including "false", 1, 0) are treated as unknown
        run_enabled = None

    # Normalize values
    policy_enabled = True  # For past runs, we don't check current policy
    provider_configured = bool(provider)
    run_provider = str(provider).strip() if provider else None

    # Determine status based on run-level config
    if run_enabled is False:
        status = "disabled-for-run"
        reason = "Review enrichment was explicitly disabled for this run."
    elif run_enabled is None:
        status = "unknown"
        reason = "Review enrichment configuration is missing for this run."
    elif not run_provider:
        status = "provider-missing"
        reason = "Review enrichment was enabled but no provider was configured."
    else:
        # Enabled and has provider - but no artifact was produced
        status = "not-attempted"
        reason = (
            f"Review enrichment was enabled for '{run_provider}' in this run, "
            "but no artifact was recorded."
        )

    return {
        "status": status,
        "reason": reason,
        "provider": None,  # Current provider - not relevant for past runs
        "policyEnabled": policy_enabled,
        "providerConfigured": provider_configured,
        "adapterAvailable": None,  # Can't check without live adapter registry
        "runEnabled": run_enabled,
        "runProvider": run_provider,
    }


def _build_clusters_from_review(
    run_id: str, review_data: dict[str, object], runs_dir: Path
) -> list[dict[str, object]]:
    """Build clusters list from review artifact's selected_drilldowns."""
    clusters: list[dict[str, object]] = []
    selected_drilldowns = review_data.get("selected_drilldowns", [])

    if not isinstance(selected_drilldowns, list):
        return clusters

    for drilldown in selected_drilldowns:
        if not isinstance(drilldown, dict):
            continue

        label = drilldown.get("label", "unknown")
        context = drilldown.get("context", "")

        # Check if drilldown artifact exists
        drilldowns_dir = runs_dir / "health" / "drilldowns"
        drilldown_artifact = None
        drilldown_timestamp = None
        if drilldowns_dir.exists():
            for df in drilldowns_dir.glob(f"{run_id}-{label}-*.json"):
                try:
                    df_data = json.loads(df.read_text(encoding="utf-8"))
                    drilldown_artifact = str(df.relative_to(runs_dir))
                    drilldown_timestamp = df_data.get("timestamp")
                    break
                except Exception:
                    continue

        clusters.append({
            "label": label,
            "context": context,
            "cluster_class": "primary",
            "cluster_role": "worker",
            "baseline_cohort": "fleet",
            "node_count": drilldown.get("node_count", 0),
            "control_plane_version": "unknown",
            "health_rating": "degraded",  # Selected drilldowns indicate issues
            "warnings": drilldown.get("warning_event_count", 0),
            "non_running_pods": drilldown.get("non_running_pod_count", 0),
            "baseline_policy_path": "",
            "missing_evidence": drilldown.get("missing_evidence", []),
            "latest_run_timestamp": review_data.get("timestamp", ""),
            "top_trigger_reason": drilldown.get("reasons", [None])[0] if drilldown.get("reasons") else None,
            "drilldown_available": drilldown_artifact is not None,
            "drilldown_timestamp": drilldown_timestamp,
            "artifact_paths": {
                "snapshot": None,
                "assessment": None,
                "drilldown": drilldown_artifact,
            },
        })

    return clusters


def _count_run_artifacts(artifacts_dir: Path, run_id: str) -> int:
    """Count artifacts belonging to a specific run in a directory."""
    if not artifacts_dir.exists():
        return 0
    count = 0
    for artifact_file in artifacts_dir.glob(f"{run_id}-*.json"):
        count += 1
    return count


def _load_proposals_for_run(
    proposals_dir: Path, run_id: str
) -> tuple[list[dict[str, object]], int]:
    """Load proposals for a specific run and return proposals data + count."""
    proposals: list[dict[str, object]] = []

    if not proposals_dir.exists():
        return proposals, 0

    for proposal_file in sorted(proposals_dir.glob(f"{run_id}-*.json")):
        try:
            proposal_data = json.loads(proposal_file.read_text(encoding="utf-8"))
            if isinstance(proposal_data, dict):
                proposals.append(proposal_data)
        except Exception:
            continue

    return proposals, len(proposals)


def _scan_external_analysis(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object]:
    """Scan external-analysis directory for artifacts belonging to a run."""
    entries: list[dict[str, object]] = []
    counts: dict[str, int] = {}

    if not external_analysis_dir.exists():
        return {"count": 0, "status_counts": [], "artifacts": entries}

    for artifact_file in sorted(external_analysis_dir.glob(f"{run_id}-*.json")):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            status = str(artifact_data.get("status", "unknown")).lower()
            counts[status] = counts.get(status, 0) + 1

            entries.append({
                "tool_name": artifact_data.get("tool_name", "unknown"),
                "cluster_label": artifact_data.get("cluster_label"),
                "run_id": artifact_data.get("run_id"),
                "run_label": artifact_data.get("run_label"),
                "status": status,
                "summary": artifact_data.get("summary"),
                "findings": artifact_data.get("findings", []),
                "suggested_next_checks": artifact_data.get("suggested_next_checks", []),
                "timestamp": artifact_data.get("timestamp"),
                "artifact_path": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "duration_ms": artifact_data.get("duration_ms"),
                "provider": artifact_data.get("provider"),
                "purpose": artifact_data.get("purpose"),
                "payload": artifact_data.get("payload"),
                "error_summary": artifact_data.get("error_summary"),
                "skip_reason": artifact_data.get("skip_reason"),
            })
        except Exception:
            continue

    status_counts = [{"status": status, "count": count} for status, count in sorted(counts.items())]

    return {"count": len(entries), "status_counts": status_counts, "artifacts": entries}


def _load_notifications_for_run(
    notifications_dir: Path, run_id: str
) -> tuple[list[dict[str, object]], int]:
    """Load notifications for a specific run."""
    notifications: list[dict[str, object]] = []

    if not notifications_dir.exists():
        return notifications, 0

    for notif_file in sorted(notifications_dir.glob("*.json")):
        try:
            notif_data = json.loads(notif_file.read_text(encoding="utf-8"))
            if not isinstance(notif_data, dict):
                continue

            # Filter by run_id if present
            notif_run_id = notif_data.get("run_id")
            if notif_run_id and notif_run_id != run_id:
                continue

            notifications.append({
                "kind": notif_data.get("kind", "info"),
                "summary": notif_data.get("summary", ""),
                "timestamp": notif_data.get("timestamp", ""),
                "run_id": notif_run_id,
                "cluster_label": notif_data.get("cluster_label"),
                "context": notif_data.get("context"),
                "details": notif_data.get("details", []),
                "artifact_path": str(notif_file.relative_to(notifications_dir.parent)),
            })
        except Exception:
            continue

    return notifications, len(notifications)


def _build_drilldown_availability_from_review(
    review_data: dict[str, object], drilldowns_dir: Path, run_id: str
) -> dict[str, object]:
    """Build drilldown availability from review clusters + drilldown artifacts."""
    selected_drilldowns = review_data.get("selected_drilldowns", [])
    if not isinstance(selected_drilldowns, list):
        selected_drilldowns = []

    total = len(selected_drilldowns)
    available = 0
    missing_labels: list[str] = []
    coverage: list[dict[str, object]] = []

    # Check which drilldowns have artifacts
    existing_drilldowns = set()
    if drilldowns_dir.exists():
        for df in drilldowns_dir.glob(f"{run_id}-*.json"):
            # Extract cluster label from filename pattern
            df_name = df.stem
            # Pattern: {run_id}-{cluster_label}-...
            if df_name.startswith(run_id + "-"):
                cluster_label = df_name[len(run_id) + 1:].split("-")[0]
                existing_drilldowns.add(cluster_label)

    for drilldown in selected_drilldowns:
        if not isinstance(drilldown, dict):
            continue

        label = drilldown.get("label", "unknown")
        context = drilldown.get("context", "")

        if label in existing_drilldowns:
            available += 1
            timestamp = review_data.get("timestamp")  # Use review timestamp as approximation
            available_flag = True
            # Find the actual artifact path
            artifact_path = None
            for df in drilldowns_dir.glob(f"{run_id}-{label}-*.json"):
                artifact_path = str(df.relative_to(drilldowns_dir.parent))
                break
        else:
            timestamp = None
            artifact_path = None
            missing_labels.append(label)
            available_flag = False

        coverage.append({
            "label": label,
            "context": context,
            "available": available_flag,
            "timestamp": timestamp,
            "artifact_path": artifact_path,
        })

    return {
        "total_clusters": total,
        "available": available,
        "missing": max(total - available, 0),
        "missing_clusters": missing_labels,
        "coverage": coverage,
    }


def _find_review_enrichment(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object] | None:
    """Find and parse review enrichment artifact for a run."""
    if not external_analysis_dir.exists():
        return None

    for artifact_file in sorted(external_analysis_dir.glob(f"{run_id}-review-enrichment*.json")):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            purpose = artifact_data.get("purpose")
            if purpose != "review-enrichment":
                continue

            payload = artifact_data.get("payload", {})

            def _list_from(*keys: str) -> list[str]:
                """Get a list from payload, checking multiple key variants."""
                for key in keys:
                    value = payload.get(key)
                    if isinstance(value, list):
                        return [str(item) for item in value]
                return []

            return {
                "status": artifact_data.get("status", "unknown"),
                "provider": artifact_data.get("provider"),
                "timestamp": artifact_data.get("timestamp"),
                "summary": artifact_data.get("summary"),
                # Check both camelCase (ui-index format) and snake_case (artifact format)
                "triageOrder": _list_from("triageOrder", "triage_order"),
                "topConcerns": _list_from("topConcerns", "top_concerns"),
                "evidenceGaps": _list_from("evidenceGaps", "evidence_gaps"),
                "nextChecks": _list_from("nextChecks", "next_checks"),
                "focusNotes": _list_from("focusNotes", "focus_notes"),
                "artifactPath": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "errorSummary": artifact_data.get("error_summary"),
                "skipReason": artifact_data.get("skip_reason"),
            }
        except Exception:
            continue

    return None


def _find_next_check_plan(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object] | None:
    """Find and parse next-check plan artifact for a run."""
    if not external_analysis_dir.exists():
        return None

    # Look for plan artifacts - they have purpose = "next-check-planning"
    for artifact_file in sorted(external_analysis_dir.glob(f"{run_id}-next-check-plan*.json")):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            purpose = artifact_data.get("purpose")
            if purpose != "next-check-planning":
                continue

            payload = artifact_data.get("payload", {})
            candidates = payload.get("candidates", [])

            return {
                "status": artifact_data.get("status", "unknown"),
                "summary": payload.get("summary"),
                "artifactPath": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "reviewPath": payload.get("reviewPath"),
                "enrichmentArtifactPath": payload.get("enrichmentArtifactPath"),
                "candidateCount": len(candidates) if isinstance(candidates, list) else 0,
                "candidates": candidates,
                "orphanedApprovals": [],
                "outcomeCounts": [],
                "orphanedApprovalCount": 0,
            }
        except Exception:
            continue

    return None


def _build_queue_from_plan(plan: dict[str, object] | None) -> list[dict[str, object]]:
    """Build next-check queue from plan artifact."""
    if not plan:
        return []

    candidates = plan.get("candidates", [])
    if not isinstance(candidates, list):
        return []

    queue: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue

        requires_approval = bool(candidate.get("requiresOperatorApproval"))
        safe_to_automate = bool(candidate.get("safeToAutomate"))

        # Determine queue status
        queue_status = "safe-ready"
        if requires_approval:
            approval_state = str(candidate.get("approvalState", "")).lower()
            if approval_state == "approved":
                queue_status = "approved-ready"
            else:
                queue_status = "approval-needed"
        elif not safe_to_automate:
            queue_status = "duplicate-or-stale"

        queue.append({
            "candidateId": candidate.get("candidateId"),
            "candidateIndex": candidate.get("candidateIndex", idx),
            "description": candidate.get("description", ""),
            "targetCluster": candidate.get("targetCluster"),
            "priorityLabel": candidate.get("priorityLabel"),
            "suggestedCommandFamily": candidate.get("suggestedCommandFamily"),
            "safeToAutomate": safe_to_automate,
            "requiresOperatorApproval": requires_approval,
            "approvalState": candidate.get("approvalState"),
            "executionState": candidate.get("executionState", "unexecuted"),
            "outcomeStatus": candidate.get("outcomeStatus"),
            "latestArtifactPath": candidate.get("latestArtifactPath"),
            "queueStatus": queue_status,
            "sourceReason": candidate.get("sourceReason"),
            "expectedSignal": candidate.get("expectedSignal"),
            "normalizationReason": candidate.get("normalizationReason"),
            "safetyReason": candidate.get("safetyReason"),
            "approvalReason": candidate.get("approvalReason"),
            "duplicateReason": candidate.get("duplicateReason"),
            "blockingReason": candidate.get("blockingReason"),
            "targetContext": None,
            "commandPreview": None,
            "planArtifactPath": plan.get("artifactPath"),
        })

    return queue


def _build_execution_history(
    external_analysis_dir: Path, run_id: str
) -> list[dict[str, object]]:
    """Build next-check execution history from execution artifacts.

    Uses prefix-based matching to handle any artifact naming pattern,
    matching any file starting with run_id and ending with '-next-check-execution'.
    This mirrors the approach used in build_runs_list() for consistency.

    After building execution entries, merges in Alertmanager review artifacts
    so the UI can display relevance judgments.
    """
    history: list[dict[str, object]] = []

    if not external_analysis_dir.exists():
        return history

    # Pre-load Alertmanager review artifacts for merging into entries
    reviews_by_source = _load_alertmanager_review_artifacts(external_analysis_dir, run_id)

    # Pre-sort files by length (longest first) to handle prefixed run_ids correctly
    # e.g., "run-2024-01-15" should match before "run-2024"
    all_files = sorted(external_analysis_dir.glob("*-next-check-execution*.json"), key=lambda p: len(p.name), reverse=True)

    for artifact_file in all_files:
        filename = artifact_file.stem  # filename without extension
        # Verify run_id boundary: must be followed by hyphen (for child runs) or end of string
        # Without this check, "run-2024" would match "run-20240-execution.json"
        if not filename.startswith(run_id):
            continue
        if len(filename) > len(run_id) and filename[len(run_id)] != "-":
            continue

        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            purpose = artifact_data.get("purpose")
            if purpose != "next-check-execution":
                continue

            # Verify run_id matches in artifact data as additional safety check
            # Only enforce if artifact has a run_id field (backward compatibility)
            artifact_run_id = artifact_data.get("run_id")
            if artifact_run_id is not None and artifact_run_id != run_id:
                continue

            payload = artifact_data.get("payload", {})

            # Extract provenance fields from payload
            candidate_id = _get_field_with_fallback(payload, "candidateId", "candidate_id")
            candidate_index_raw = _get_field_with_default(payload, None, "candidateIndex", "candidate_index")
            candidate_index: int | None = None
            if candidate_index_raw is not None:
                try:
                    candidate_index = int(str(candidate_index_raw))
                except (ValueError, TypeError):
                    candidate_index = None

            entry: dict[str, object] = {
                "timestamp": artifact_data.get("timestamp"),
                "clusterLabel": _get_field_with_fallback(payload, "clusterLabel", "cluster_label"),
                "candidateDescription": _get_field_with_fallback(payload, "candidateDescription", "candidate_description"),
                "commandFamily": _get_field_with_fallback(payload, "commandFamily", "command_family"),
                "status": artifact_data.get("status", "unknown"),
                "durationMs": _get_field_with_default(artifact_data, 0, "duration_ms", "durationMs"),
                "artifactPath": str(artifact_file.relative_to(external_analysis_dir.parent)),
                "timedOut": _get_field_with_default(artifact_data, False, "timed_out", "timedOut"),
                "stdoutTruncated": _get_field_with_default(artifact_data, False, "stdout_truncated", "stdoutTruncated"),
                "stderrTruncated": _get_field_with_default(artifact_data, False, "stderr_truncated", "stderrTruncated"),
                "outputBytesCaptured": _get_field_with_default(artifact_data, 0, "output_bytes_captured", "outputBytesCaptured"),
                "candidateId": candidate_id,
                "candidateIndex": candidate_index,
            }

            # Merge Alertmanager review if exists for this source artifact
            source_artifact = str(artifact_file.relative_to(external_analysis_dir.parent))
            review = reviews_by_source.get(source_artifact)
            if review is not None:
                entry = _merge_alertmanager_review_into_history_entry(entry, review)

            history.append(entry)
        except Exception:
            continue

    # Sort by timestamp descending (most recent first) using ISO timestamp comparison
    history.sort(key=lambda x: cast(str, x.get("timestamp") or ""), reverse=True)

    return history[:5]  # Limit to 5 most recent


def _parse_positive_int(value: object | None) -> int | None:
    """Parse a positive integer duration from various types.

    Returns None for missing, zero, negative, or non-numeric values.
    Only positive (> 0) durations are included in latency percentiles.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float):
        int_val = int(value)
        return int_val if int_val > 0 else None
    if isinstance(value, str):
        try:
            int_val = int(value)
            return int_val if int_val > 0 else None
        except ValueError:
            return None
    return None


def _build_llm_stats_for_run(
    external_analysis_dir: Path, run_id: str
) -> dict[str, object]:
    """Build LLM stats from external-analysis artifacts for a specific run."""
    total_calls = 0
    successful_calls = 0
    failed_calls = 0
    latest_timestamp: str | None = None
    provider_counts: dict[str, dict[str, int]] = {}
    # Collect positive durations only from successful calls for latency percentile computation
    successful_durations: list[int] = []

    if not external_analysis_dir.exists():
        return {
            "totalCalls": 0,
            "successfulCalls": 0,
            "failedCalls": 0,
            "lastCallTimestamp": None,
            "p50LatencyMs": None,
            "p95LatencyMs": None,
            "p99LatencyMs": None,
            "providerBreakdown": [],
            "scope": "current_run",
        }

    for artifact_file in sorted(external_analysis_dir.glob(f"{run_id}-*.json")):
        try:
            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(artifact_data, dict):
                continue

            status = str(artifact_data.get("status", "")).lower()
            if status not in ("success", "failed"):
                continue

            total_calls += 1
            if status == "success":
                successful_calls += 1
                # Collect positive duration from successful calls for latency percentiles.
                # Prefer snake_case field name, fall back to camelCase for compatibility.
                # Only positive durations are included; zero/negative/missing yield None.
                duration_ms = artifact_data.get("duration_ms")
                duration = _parse_positive_int(duration_ms)
                if duration is None:
                    duration = _parse_positive_int(artifact_data.get("durationMs"))
                if duration is not None:
                    successful_durations.append(duration)
            if status == "failed":
                failed_calls += 1

            # Track latest timestamp
            timestamp = artifact_data.get("timestamp")
            if timestamp:
                if latest_timestamp is None or timestamp > latest_timestamp:
                    latest_timestamp = timestamp

            # Track provider breakdown
            provider = str(artifact_data.get("tool_name") or artifact_data.get("provider") or "unknown")
            if provider not in provider_counts:
                provider_counts[provider] = {"calls": 0, "failedCalls": 0}
            provider_counts[provider]["calls"] += 1
            if status == "failed":
                provider_counts[provider]["failedCalls"] += 1

        except Exception:
            continue

    provider_breakdown = [
        {"provider": provider, "calls": data["calls"], "failedCalls": data["failedCalls"]}
        for provider, data in sorted(provider_counts.items())
    ]

    # Compute latency percentiles from successful call durations
    percentile_values: dict[str, int | None] = {
        "p50": None,
        "p95": None,
        "p99": None,
    }
    if successful_durations:
        float_durations = [float(value) for value in successful_durations]
        float_durations.sort()
        percentile_values["p50"] = _percentile_value(float_durations, 50)
        percentile_values["p95"] = _percentile_value(float_durations, 95)
        percentile_values["p99"] = _percentile_value(float_durations, 99)

    return {
        "totalCalls": total_calls,
        "successfulCalls": successful_calls,
        "failedCalls": failed_calls,
        "lastCallTimestamp": latest_timestamp,
        "p50LatencyMs": percentile_values["p50"],
        "p95LatencyMs": percentile_values["p95"],
        "p99LatencyMs": percentile_values["p99"],
        "providerBreakdown": provider_breakdown,
        "scope": "current_run",
    }


# Mirrors the algorithm in health/ui_llm_stats.py for consistency.
# Local duplication avoids a cross-module dependency from ui to health layer.
def _percentile_value(values: list[float], percentile: float) -> int | None:
    """Compute a percentile value from a sorted list of floats.

    Returns None if the input list is empty.
    Uses nearest-rank method: index = ceil(p/100 * n) - 1.
    """
    if not values:
        return None
    idx = math.ceil((percentile / 100) * len(values)) - 1
    idx = max(0, min(idx, len(values) - 1))
    return int(values[idx])


def _build_proposal_status_summary(proposals: list[dict[str, object]]) -> dict[str, object]:
    """Build proposal status summary from proposals list."""
    counts: dict[str, int] = {}

    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        status = str(proposal.get("status", "unknown")).lower()
        counts[status] = counts.get(status, 0) + 1

    status_counts = [{"status": status, "count": count} for status, count in sorted(counts.items())]

    return {"status_counts": status_counts}
