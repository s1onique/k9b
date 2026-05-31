"""Notification and promotion index projections for health UI.

Extracted from health/ui.py to provide focused modules for index-building concerns:
- notification_index: Compact notification list index for fast /api/notifications path
- promotions_index: Promotion entries index for fast /api/run promotions loading
- proposal_status_summary: Write-through cache for proposal status in review artifacts

These projections avoid repeated directory scanning on cold startup and API requests.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ...security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id
from ..notifications import NotificationArtifact
from ..ui_serialization import _stringify_notification_value
from ..ui_shared import _relative_path

logger = logging.getLogger(__name__)

# Maximum number of notification summaries to store in the index
# This bounds index size while providing fast default list access
_NOTIFICATION_INDEX_LIMIT = 500

# Maximum number of promotion entries to store in the index
# Most runs have very few promotions, so this is generous
_PROMOTIONS_INDEX_LIMIT = 100

NotificationRecord = tuple[NotificationArtifact, Path]


def _build_notification_index(
    notifications: Sequence[NotificationRecord],
    output_dir: Path,
) -> dict[str, object]:
    """Build a compact notification index for fast /api/notifications default path.

    This is the key optimization to avoid scanning all notification files on cold startup.
    Each entry contains only the fields needed for the initial notification list:
    - kind, summary, timestamp, runId, clusterLabel
    - artifactPath for provenance pointer to full artifact

    The index is bounded to latest 500 notifications to keep index size manageable.

    Args:
        notifications: Sequence of (NotificationArtifact, Path) tuples
        output_dir: Path to the health directory for relative path computation

    Returns:
        Dict with 'notifications' list, 'total_count', 'generated_at', 'version'
    """
    if not notifications:
        return {
            "notifications": [],
            "total_count": 0,
            "generated_at": datetime.now(UTC).isoformat(),
            "version": 1,
        }

    # Sort by timestamp descending (newest first)
    sorted_notifications = sorted(
        notifications,
        key=lambda item: item[0].timestamp,
        reverse=True,
    )

    total_count = len(sorted_notifications)

    # Build notification entries with list-view fields
    entries: list[dict[str, object]] = []
    for artifact, path in sorted_notifications:
        # Build minimal detail entries for the list view
        detail_entries = [
            {"label": str(key), "value": _stringify_notification_value(value)}
            for key, value in sorted(artifact.details.items())
        ]

        entry: dict[str, object] = {
            "kind": artifact.kind,
            "summary": artifact.summary,
            "timestamp": artifact.timestamp,
            "runId": artifact.run_id,
            "clusterLabel": artifact.cluster_label,
            "context": artifact.context,
            "details": detail_entries,
            "artifactPath": _relative_path(output_dir, path),
        }

        # Thread artifact_id for provenance/debugging surfaces (optional)
        if artifact.artifact_id:
            entry["artifact_id"] = artifact.artifact_id

        entries.append(entry)

    # Bound entries to limit
    bounded_entries = entries[:_NOTIFICATION_INDEX_LIMIT]

    return {
        "notifications": bounded_entries,
        "total_count": total_count,
        "generated_at": datetime.now(UTC).isoformat(),
        "version": 1,
    }


def _build_promotions_index(
    external_analysis_dir: Path,
    run_id: str,
) -> dict[str, object]:
    """Build a compact promotions index for fast /api/run promotions loading.

    This is the key optimization to avoid globbing all external-analysis files
    on each /api/run request. The index stores promotion entries for the current
    run only, with enough data to reconstruct queue entries without re-reading
    promotion artifacts.

    IMPORTANT: The index is run-scoped to prevent cross-run data leakage.
    When /api/run requests a historical run, it must validate that the index's
    run_id matches the requested run_id, otherwise fall back to file-based loading.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The current run ID to filter promotions for

    Returns:
        Dict with 'run_id', 'promotions' list, 'total_count', 'generated_at', 'version'
    """
    if not external_analysis_dir.is_dir():
        return {
            "run_id": run_id,
            "promotions": [],
            "total_count": 0,
            "generated_at": datetime.now(UTC).isoformat(),
            "version": 1,
        }

    # SECURITY: Validate run_id before using in glob pattern to prevent path traversal
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return safe fallback
        return {
            "run_id": run_id,
            "promotions": [],
            "total_count": 0,
            "generated_at": datetime.now(UTC).isoformat(),
            "version": 1,
        }

    # Scan for promotion artifacts for this run only
    promotion_entries: list[dict[str, object]] = []
    # SECURITY: run_id validated by validate_run_id() before glob construction
    for artifact_path in external_analysis_dir.glob(
        safe_run_artifact_glob(validated_run_id, "-next-check-promotion-*.json")
    ):
        try:
            raw = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "Skipped malformed promotion artifact: %s",
                artifact_path.name,
                exc_info=True,
            )
            continue

        # Extract payload for queue entry reconstruction
        payload = raw.get("payload")
        if not isinstance(payload, Mapping):
            continue

        # Build minimal queue entry from promotion payload
        entry: dict[str, object] = {
            "candidateId": payload.get("candidateId"),
            "candidateIndex": payload.get("promotionIndex", 0),
            "description": payload.get("description", "Deterministic next check"),
            "targetCluster": payload.get("clusterLabel", ""),
            "targetContext": payload.get("targetContext"),
            "sourceReason": (
                payload.get("whyNow") or payload.get("topProblem") or "Deterministic next check"
            ),
            "workstream": payload.get("workstream"),
            "urgency": payload.get("urgency"),
            "priorityScore": payload.get("priorityScore"),
            "sourceType": "deterministic",
            "approvalState": "approval-required",
            "executionState": "unexecuted",
            "queueStatus": "approval-needed",
            "artifactPath": _relative_path(external_analysis_dir.parent, artifact_path),
        }

        promotion_entries.append(entry)

    # Sort by promotion index (consistent ordering)
    promotion_entries.sort(key=lambda x: cast(int, x.get("candidateIndex") or 0))

    # Bound entries to limit
    bounded_entries = promotion_entries[:_PROMOTIONS_INDEX_LIMIT]

    return {
        "run_id": run_id,  # CRITICAL: run-scoped to prevent cross-run data leakage
        "promotions": bounded_entries,
        "total_count": len(promotion_entries),
        "generated_at": datetime.now(UTC).isoformat(),
        "version": 1,
    }


def _write_proposal_status_summary_to_review(
    output_dir: Path,
    run_id: str,
    proposal_status_summary: dict[str, object],
) -> None:
    """Write proposal_status_summary to review artifact for fast past-run loading.

    NOTE: The summary is stored as _proposal_status_summary in the review artifact.
    This is derived read-model metadata (underscore-prefixed to mark as internal
    indexing data), NOT source evidence. It provides a fast path to skip proposals/
    directory scanning when loading historical runs via /api/run?run_id=.

    Fallback behavior: If a review artifact lacks _proposal_status_summary (e.g., from
    an older run created before this optimization), _load_context_for_run() will fall
    back to scanning the proposals/ directory and building the summary on-demand.

    This is the key optimization to avoid _load_context_for_run() scanning
    the proposals/ directory on each /api/run request for historical runs.

    Args:
        output_dir: Path to the health directory (runs/health/)
        run_id: The run ID to update the review artifact for
        proposal_status_summary: The pre-computed proposal status summary dict
    """
    reviews_dir = output_dir / "reviews"
    review_path = reviews_dir / f"{run_id}-review.json"

    if not review_path.exists():
        return

    try:
        review_data = json.loads(review_path.read_text(encoding="utf-8"))
        if not isinstance(review_data, dict):
            return

        # Add proposal_status_summary to review artifact
        # Use underscore prefix to mark as internal indexing metadata
        review_data["_proposal_status_summary"] = proposal_status_summary

        # Write back preserving original formatting (compact write)
        review_path.write_text(json.dumps(review_data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        # Non-fatal: if we can't write the summary, past runs will still work
        # by falling back to the directory scan path
        logger.warning(
            "Failed to write proposal status summary to review: %s",
            review_path.name,
            exc_info=True,
        )


__all__ = [
    "_NOTIFICATION_INDEX_LIMIT",
    "_PROMOTIONS_INDEX_LIMIT",
    "_build_notification_index",
    "_build_promotions_index",
    "_write_proposal_status_summary_to_review",
    "NotificationRecord",
]
