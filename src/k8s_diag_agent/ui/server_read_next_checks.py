"""Next-check plan and execution helpers for the UI server.

This module contains functions for finding next-check plans, scanning execution
artifacts, building queues, and building execution history. Extracted from
server_read_support.py for LLM-friendly organization.

Keep behavior unchanged: no logic changes, no response shape changes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from ..security.deanonymization import deanonymize_next_check_candidate
from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

logger = logging.getLogger(__name__)


def _find_next_check_plan(
    external_analysis_dir: Path, run_id: str, artifact_index: Any = None
) -> dict[str, object] | None:
    """Find and parse next-check plan artifact for a run.

    Uses artifact_index if provided for O(1) lookup, otherwise falls back
    to scanning the directory (for backward compatibility).

    Args:
        external_analysis_dir: Path to external-analysis directory (used if no index)
        run_id: The run ID to filter by
        artifact_index: Pre-built index for O(1) lookup (optional)

    Returns:
        Next-check plan data dict, or None if not found
    """
    # Import here to avoid circular imports
    from .server_read_support import _find_alias_mapping_from_review, _scan_execution_artifacts_for_queue

    # Use index for O(1) lookup if available
    _scan_plan_artifacts: list[dict[str, object]] = []
    if artifact_index is not None:
        _scan_plan_artifacts = list(artifact_index.next_check_plan)
    else:
        # Fall back to directory scan for backward compatibility
        if not external_analysis_dir.exists():
            return None

        # Validate run_id at function boundary for safe glob construction
        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            # Invalid run_id - cannot safely search, return None
            return None

        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")
        for artifact_file in sorted(external_analysis_dir.glob(glob_pattern)):
            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                if isinstance(artifact_data, dict):
                    purpose = artifact_data.get("purpose")
                    if purpose == "next-check-planning":
                        artifact_data["artifact_path"] = str(artifact_file.relative_to(external_analysis_dir.parent))
                        _scan_plan_artifacts.append(artifact_data)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Skipped malformed next-check-plan artifact: %s",
                    artifact_file.name,
                    extra={
                        "run_id": run_id,
                        "artifact_kind": "next-check-plan",
                        "scan_name": "_find_next_check_plan",
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                continue

    if not _scan_plan_artifacts:
        return None

    # Take the first (sorted) matching artifact
    artifact_data = _scan_plan_artifacts[0]

    raw_payload = artifact_data.get("payload")
    payload: dict[str, object] = raw_payload if isinstance(raw_payload, dict) else {}

    # Get artifact path
    artifact_path = artifact_data.get("artifact_path")

    # Get alias mapping from plan artifact and apply de-anonymization to candidates.
    # The alias_mapping may be stored in the plan artifact (from planner's anonymized input).
    # If not present in plan, fall back to the review-enrichment artifact's mapping.
    _plan_alias: object | None = artifact_data.get("alias_mapping")
    if isinstance(_plan_alias, dict) and _plan_alias:
        alias_mapping: dict[str, str] | None = cast("dict[str, str]", _plan_alias)
    else:
        # Fall back to review-enrichment artifact for alias mapping
        alias_mapping = _find_alias_mapping_from_review(external_analysis_dir, run_id, artifact_index)

    # Scan execution artifacts for overlay derivation
    # This enables queue items to reflect actual execution state from artifacts
    execution_overlays = _scan_execution_artifacts_for_queue(
        external_analysis_dir,
        run_id,
        artifact_index=artifact_index,
    )

    deanon_candidates = _build_queue_from_plan(payload, alias_mapping, execution_overlays)

    return {
        "status": artifact_data.get("status", "unknown"),
        "summary": payload.get("summary"),
        "artifactPath": artifact_path,
        "reviewPath": payload.get("reviewPath"),
        "enrichmentArtifactPath": payload.get("enrichmentArtifactPath"),
        "candidateCount": len(deanon_candidates),
        "candidates": deanon_candidates,
        "orphanedApprovals": [],
        "outcomeCounts": [],
        "orphanedApprovalCount": 0,
    }


def _scan_execution_artifacts_for_queue(
    external_analysis_dir: Path,
    run_id: str,
    *,
    artifact_index: Any = None,
) -> list[dict[str, object]]:
    """Scan external-analysis directory for execution artifacts to overlay queue state.

    Uses artifact_index if provided for O(1) lookup, otherwise falls back
    to scanning the directory (for backward compatibility).

    Returns a list of overlays that can be matched against queue candidates.
    Each overlay contains: candidate_index, command_family, target_cluster, status, artifact_path, timestamp.

    Args:
        external_analysis_dir: Path to external-analysis directory (used if no index)
        run_id: The run ID to filter by
        artifact_index: Pre-built index for O(1) lookup (optional)
    """
    overlays: list[dict[str, object]] = []

    # Use index for O(1) lookup if available
    if artifact_index is not None:
        execution_artifacts = list(artifact_index.next_check_execution)
    else:
        # Fall back to directory scan for backward compatibility
        if not external_analysis_dir.exists():
            return overlays

        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            return overlays

        _scan_execution: list[dict[str, object]] = []
        # SECURITY: run_id validated by validate_run_id() before glob construction
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-execution-*.json")
        for artifact_file in sorted(external_analysis_dir.glob(glob_pattern)):
            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                if isinstance(artifact_data, dict) and artifact_data.get("purpose") == "next-check-execution":
                    # Add artifact_path for reference (relative to external-analysis parent)
                    artifact_data["artifact_path"] = str(artifact_file.relative_to(external_analysis_dir.parent))
                    _scan_execution.append(artifact_data)
            except (OSError, json.JSONDecodeError):
                continue

        execution_artifacts = _scan_execution

    # Process artifacts (from index or scan) - all have artifact_path set
    for artifact_data in execution_artifacts:
        try:
            # Verify purpose (already filtered for index path, but check for scan path)
            purpose = artifact_data.get("purpose")
            if purpose != "next-check-execution":
                continue

            payload = artifact_data.get("payload", {})
            if not isinstance(payload, dict):
                continue

            # Extract matching fields from payload
            candidate_id = payload.get("candidateId") or payload.get("candidate_id")
            candidate_index_raw = payload.get("candidateIndex") or payload.get("candidate_index")
            candidate_index: int | None = None
            if candidate_index_raw is not None:
                try:
                    candidate_index = int(str(candidate_index_raw))
                except (ValueError, TypeError):
                    pass

            # Extract command_family
            command_family = payload.get("commandFamily") or payload.get("command_family")
            if not command_family:
                tool_name = payload.get("tool_name") or ""
                if isinstance(tool_name, str) and "-" in tool_name:
                    command_family = tool_name.split("-", 1)[1] if "-" in tool_name else tool_name

            # Extract target_cluster
            target_cluster = payload.get("clusterLabel") or payload.get("cluster_label") or payload.get("targetCluster")

            # Extract status and timestamp
            status = artifact_data.get("status")
            timestamp = artifact_data.get("timestamp")

            # Use artifact_path from index or scan (already set above)
            artifact_path = artifact_data.get("artifact_path")
            if not isinstance(artifact_path, str):
                artifact_path = str(artifact_data)

            overlays.append({
                "candidate_id": str(candidate_id) if candidate_id else None,
                "candidate_index": candidate_index,
                "command_family": str(command_family) if command_family else None,
                "target_cluster": str(target_cluster) if target_cluster else None,
                "status": str(status) if status else None,
                "timestamp": str(timestamp) if timestamp else None,
                "artifact_path": artifact_path,
            })
        except (OSError, json.JSONDecodeError):
            continue

    return overlays


def _match_overlay_to_candidate(
    overlay: dict[str, object],
    candidate: dict[str, object],
) -> bool:
    """Check if an execution overlay matches a queue candidate.

    Primary match: candidate_index + command_family + target_cluster (all required)
    Fallback match: candidate_id + target_cluster (all required)
    """
    overlay_index = overlay.get("candidate_index")
    overlay_family = overlay.get("command_family")
    overlay_cluster = overlay.get("target_cluster")
    overlay_id = overlay.get("candidate_id")

    candidate_index = candidate.get("candidateIndex") or candidate.get("candidate_index")
    candidate_family = candidate.get("suggestedCommandFamily") or candidate.get("commandFamily") or candidate.get("command_family")
    candidate_cluster = candidate.get("targetCluster") or candidate.get("target_cluster")
    candidate_id = candidate.get("candidateId") or candidate.get("candidate_id")

    # Primary match: candidate_index + command_family + target_cluster
    if overlay_index is not None and overlay_family and overlay_cluster:
        index_match = overlay_index == candidate_index
        family_match = overlay_family.lower() == str(candidate_family).lower() if candidate_family else False
        cluster_match = overlay_cluster == candidate_cluster
        if index_match and family_match and cluster_match:
            return True

    # Fallback match: candidate_id + target_cluster
    if overlay_id and overlay_cluster:
        id_match = overlay_id == candidate_id
        cluster_match = overlay_cluster == candidate_cluster
        if id_match and cluster_match:
            return True

    return False


def _derive_execution_state_from_status(status: str | None) -> str:
    """Derive execution_state from artifact status.

    Maps artifact status to queue item execution_state:
    - "success" -> "executed-success"
    - "failed" -> "executed-failed"
    - "timed-out" / "timeout" -> "timed-out"
    - other -> "executed-success" (default for any completed artifact)
    """
    if status is None:
        return "executed-success"

    status_lower = status.lower()
    if status_lower == "success":
        return "executed-success"
    elif status_lower == "failed":
        return "executed-failed"
    elif status_lower in ("timed-out", "timeout"):
        return "timed-out"
    else:
        return "executed-success"


def _build_queue_from_plan(
    plan: dict[str, object] | None,
    alias_mapping: dict[str, str] | None = None,
    execution_overlays: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Build next-check queue from plan artifact with execution state overlay.

    Args:
        plan: The plan artifact dict containing candidates
        alias_mapping: Optional alias-to-real mapping for de-anonymization
        execution_overlays: Optional list of execution artifact overlays to apply
                           (e.g., from _scan_execution_artifacts_for_queue)
    """
    if not plan:
        return []

    candidates = plan.get("candidates", [])
    if not isinstance(candidates, list):
        return []

    queue: list[dict[str, object]] = []
    for idx, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue

        # Apply de-anonymization if alias_mapping provided
        if alias_mapping:
            deanon_candidate = deanonymize_next_check_candidate(candidate, alias_mapping)
        else:
            deanon_candidate = candidate

        requires_approval = bool(deanon_candidate.get("requiresOperatorApproval"))
        safe_to_automate = bool(deanon_candidate.get("safeToAutomate"))

        # Check for matching execution overlay
        execution_state = deanon_candidate.get("executionState", "unexecuted")
        outcome_status = deanon_candidate.get("outcomeStatus")
        latest_artifact_path = deanon_candidate.get("latestArtifactPath")

        if execution_overlays:
            for overlay in execution_overlays:
                if _match_overlay_to_candidate(overlay, deanon_candidate):
                    # Found matching execution artifact - overlay execution state
                    status_value = overlay.get("status")
                    execution_state = _derive_execution_state_from_status(str(status_value) if status_value is not None else None)
                    outcome_status = execution_state  # Map executionState to outcomeStatus
                    latest_artifact_path = overlay.get("artifact_path")
                    break

        # Determine queue status
        queue_status = "safe-ready"
        if requires_approval:
            approval_state = str(deanon_candidate.get("approvalState", "")).lower()
            if approval_state == "approved":
                queue_status = "approved-ready"
            else:
                queue_status = "approval-needed"
        elif not safe_to_automate:
            queue_status = "duplicate-or-stale"

        queue.append({
            "candidateId": deanon_candidate.get("candidateId"),
            "candidateIndex": deanon_candidate.get("candidateIndex", idx),
            "description": deanon_candidate.get("description", ""),
            "targetCluster": deanon_candidate.get("targetCluster"),
            "priorityLabel": deanon_candidate.get("priorityLabel"),
            "suggestedCommandFamily": deanon_candidate.get("suggestedCommandFamily"),
            "safeToAutomate": safe_to_automate,
            "requiresOperatorApproval": requires_approval,
            "approvalState": deanon_candidate.get("approvalState"),
            "executionState": execution_state,
            "outcomeStatus": outcome_status,
            "latestArtifactPath": latest_artifact_path,
            "queueStatus": queue_status,
            "sourceReason": deanon_candidate.get("sourceReason"),
            "expectedSignal": deanon_candidate.get("expectedSignal"),
            "normalizationReason": deanon_candidate.get("normalizationReason"),
            "safetyReason": deanon_candidate.get("safetyReason"),
            "approvalReason": deanon_candidate.get("approvalReason"),
            "duplicateReason": deanon_candidate.get("duplicateReason"),
            "blockingReason": deanon_candidate.get("blockingReason"),
            "targetContext": deanon_candidate.get("targetContext"),
            "commandPreview": deanon_candidate.get("commandPreview"),
            "planArtifactPath": plan.get("artifactPath"),
        })

    return queue


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


def _build_execution_history(
    external_analysis_dir: Path, run_id: str, artifact_index: Any = None
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Build next-check execution history from execution artifacts.

    Uses artifact_index if provided for O(1) lookup, otherwise falls back
    to scanning the directory (for backward compatibility).

    Uses prefix-based matching to handle any artifact naming pattern,
    matching any file starting with run_id and ending with '-next-check-execution'.
    This mirrors the approach used in build_runs_list() for consistency.

    After building execution entries, merges in Alertmanager review artifacts
    so the UI can display relevance judgments.

    Args:
        external_analysis_dir: Path to external-analysis directory (used if no index)
        run_id: The run ID to filter by
        artifact_index: Pre-built index for O(1) lookup (optional)

    Returns:
        Tuple of (history entries, telemetry dict) sorted by timestamp descending
    """
    # Import here to avoid circular imports
    from .server_read_support import _load_alertmanager_review_artifacts, _merge_alertmanager_review_into_history_entry

    history: list[dict[str, object]] = []
    telemetry: dict[str, object] = {
        "execution_history_source": "unknown",
        "alertmanager_review_source": "unknown",
        "alertmanager_reviews_indexed": 0,
        "execution_entries_returned": 0,
    }

    # Determine Alertmanager review source:
    # - If artifact_index provided and has reviews, use index (no glob needed)
    # - Otherwise, fall back to file scan (backward compatibility)
    if artifact_index is not None and artifact_index.alertmanager_reviews_by_source:
        reviews_by_source = artifact_index.alertmanager_reviews_by_source
        telemetry["alertmanager_review_source"] = "artifact_index"
        telemetry["alertmanager_reviews_indexed"] = len(reviews_by_source)
    elif artifact_index is not None:
        # Index exists but no reviews indexed
        reviews_by_source = {}
        telemetry["alertmanager_review_source"] = "artifact_index"
        telemetry["alertmanager_reviews_indexed"] = 0
    else:
        # No index - fall back to file scan
        reviews_by_source = _load_alertmanager_review_artifacts(external_analysis_dir, run_id)
        telemetry["alertmanager_review_source"] = "file_scan"
        telemetry["alertmanager_reviews_indexed"] = len(reviews_by_source)

    # Use index for O(1) lookup if available
    # Declare type annotation to allow both tuple (from index) and list (from scan)
    execution_artifacts: Sequence[dict[str, object]]
    if artifact_index is not None:
        execution_artifacts = artifact_index.next_check_execution
        telemetry["execution_history_source"] = "artifact_index"
    else:
        telemetry["execution_history_source"] = "file_scan"
        # Fall back to directory scan for backward compatibility
        if not external_analysis_dir.exists():
            telemetry["execution_entries_returned"] = 0
            return history, telemetry

        # Validate run_id at function boundary for safe glob construction
        try:
            validated_run_id = validate_run_id(run_id)
        except SecurityError:
            # Invalid run_id - cannot safely search, return empty history
            telemetry["execution_entries_returned"] = 0
            return history, telemetry

        _scan_execution_artifacts: list[dict[str, object]] = []
        # SECURITY: run_id validated by validate_run_id() before glob construction
        # The suffix "-next-check-execution*.json" ensures we only match execution artifacts
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-execution*.json")
        for artifact_file in sorted(external_analysis_dir.glob(glob_pattern)):
            filename = artifact_file.stem
            # Enforce prefix boundary to prevent run_id collision
            # e.g., run_id="run-2024" should NOT match "run-20240-..."
            if len(filename) > len(validated_run_id) and filename[len(validated_run_id)] != "-":
                continue

            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                if isinstance(artifact_data, dict):
                    purpose = artifact_data.get("purpose")
                    if purpose == "next-check-execution":
                        # Add artifact_path for reference
                        artifact_data["artifact_path"] = str(artifact_file.relative_to(external_analysis_dir.parent))
                        _scan_execution_artifacts.append(artifact_data)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Skipped malformed next-check-execution artifact: %s",
                    artifact_file.name,
                    extra={
                        "run_id": run_id,
                        "artifact_kind": "next-check-execution",
                        "scan_name": "_build_execution_history",
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                continue

        # Assign scanned artifacts for iteration
        execution_artifacts = _scan_execution_artifacts

    for artifact_data in execution_artifacts:
        # Verify run_id matches in artifact data as additional safety check
        # Only enforce if artifact has a run_id field (backward compatibility)
        artifact_run_id = artifact_data.get("run_id")
        if artifact_run_id is not None and artifact_run_id != run_id:
            continue

        payload = artifact_data.get("payload", {})

        # Extract provenance fields from payload
        assert isinstance(payload, dict), "payload must be dict after isinstance check above"
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
            "artifactPath": artifact_data.get("artifact_path"),
            "timedOut": _get_field_with_default(artifact_data, False, "timed_out", "timedOut"),
            "stdoutTruncated": _get_field_with_default(artifact_data, False, "stdout_truncated", "stdoutTruncated"),
            "stderrTruncated": _get_field_with_default(artifact_data, False, "stderr_truncated", "stderrTruncated"),
            "outputBytesCaptured": _get_field_with_default(artifact_data, 0, "output_bytes_captured", "outputBytesCaptured"),
            "candidateId": candidate_id,
            "candidateIndex": candidate_index,
        }

        # Merge Alertmanager review if exists for this source artifact
        source_artifact = artifact_data.get("artifact_path")
        if isinstance(source_artifact, str) and source_artifact:
            review = reviews_by_source.get(source_artifact)
            if review is not None:
                entry = _merge_alertmanager_review_into_history_entry(entry, review)

        history.append(entry)

    # Sort by timestamp descending (most recent first) using ISO timestamp comparison
    history.sort(key=lambda x: cast(str, x.get("timestamp") or ""), reverse=True)
    telemetry["execution_entries_returned"] = len(history[:5])

    return history[:5], telemetry  # Limit to 5 most recent