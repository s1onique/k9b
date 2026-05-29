"""Next-check execution history helpers for the UI server.

This module contains functions for building execution history from artifacts.
Extracted from server_read_next_checks.py for LLM-friendly organization.

Keep behavior unchanged: no logic changes, no response shape changes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

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
    # Import from cluster module - this is the source module for alertmanager helpers
    from .server_read_clusters import (
        _load_alertmanager_review_artifacts,
        _merge_alertmanager_review_into_history_entry,
    )

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
