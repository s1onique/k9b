"""Recent runs summary projection for health UI.

Extracted from health/ui.py to provide a focused module for recent-runs concerns.

This module handles:
- Recent runs summary building with batch eligibility computation
- Plan data extraction for execution index diagnostics
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ...datetime_utils import parse_iso_to_utc
from ...ui.execution_index_utils import collect_execution_indices_for_all_runs

logger = logging.getLogger(__name__)

# Version marker for execution index collector
# If marker is missing in bundle, deployment/runtime is stale
EXECUTION_INDEX_COLLECTOR_VERSION = "shared-one-pass-v1"

# Regex pattern for extracting timestamp from run_id
_RUN_ID_TIMESTAMP_PATTERN = re.compile(r"(\d{8}T\d{6}Z)$")

# Minimum datetime for sorting
_MIN_DATETIME = datetime.min.replace(tzinfo=UTC)


def _build_recent_runs_summary(
    reviews_dir: Path,
    max_runs: int = 500,
    *,
    external_analysis_dir: Path | None = None,
) -> dict[str, object]:
    """Build a compact summary of recent runs for fast /api/runs default path.

    This is the key optimization to avoid scanning all review files on each request.
    Each entry contains fields needed for Recent Runs list including batch eligibility:
    - run_id, run_label, timestamp, cluster_count
    - batchEligibility, batchExecutable, batchEligibleCount
    - reviewStatus, executionCount, reviewedCount, triaged (if available from external-analysis)

    The batch eligibility and execution summary are computed during index generation
    (where the external-analysis directory is already being scanned), so this function
    can include them without additional cost.

    The _plan_data and _execution_indices fields are stored for use by the API layer's
    _build_runs_list_with_batch_eligibility_index() function, which needs this data
    to compute executionSummary without filesystem access.

    Args:
        reviews_dir: Path to the reviews directory
        max_runs: Maximum number of run summaries to store (default 500 for most UIs)
        external_analysis_dir: Path to external-analysis directory for batch eligibility computation

    Returns:
        Dict with 'runs' list, 'total_count', 'version', and internal data for API layer
    """
    if not reviews_dir.is_dir():
        return {"runs": [], "total_count": 0, "generated_at": _get_current_timestamp(), "version": 2}

    # Pre-scan external-analysis directory for batch eligibility computation
    # This is done once during index generation, not on each API request
    # Structure: plan_data[run_id] = plan artifact dict
    plan_data: dict[str, dict[str, object]] = {}
    # Structure: execution_indices[run_id] = {candidate_index: status_string}
    execution_indices_with_status: dict[str, dict[int, str]] = {}

    # Use shared one-pass collector for O(artifacts) instead of O(runs × artifacts)
    # This ensures consistency between index-backed and fresh worklist paths
    exec_dir = external_analysis_dir if external_analysis_dir is not None else None
    if exec_dir is None:
        execution_indices_with_status = {}
        exec_diagnostics: dict[str, object] = {}
    else:
        execution_indices_with_status, exec_diagnostics = collect_execution_indices_for_all_runs(
            exec_dir, 
            health_root=reviews_dir.parent if reviews_dir.parent.name == "health" else None
        )
    
    # Load plan files for all runs
    if external_analysis_dir is not None and external_analysis_dir.is_dir():
        for plan_path in external_analysis_dir.glob("*-next-check-plan*.json"):
            try:
                raw = json.loads(plan_path.read_text(encoding="utf-8"))
                if raw.get("purpose") == "next-check-planning":
                    # Extract run_id from filename: {run_id}-next-check-plan*.json
                    filename = plan_path.stem
                    for candidate_run_id in _extract_run_ids_from_filename(filename, "-next-check-plan"):
                        if candidate_run_id:
                            plan_data[candidate_run_id] = raw
                            break
            except (OSError, json.JSONDecodeError):
                continue

    # Collect all run summaries with batch eligibility
    run_summaries: list[dict[str, object]] = []
    for path in reviews_dir.glob("*-review.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipped malformed recent-run artifact: %s", path.name, exc_info=True)
            continue

        run_id = raw.get("run_id")
        timestamp = raw.get("timestamp")
        if not isinstance(run_id, str) or not isinstance(timestamp, str):
            continue

        # Compute batch eligibility for this run if we have plan data
        batch_executable = False
        batch_eligible_count = 0
        batch_eligibility = "unknown"

        if run_id in plan_data:
            batch_executable, batch_eligible_count = _compute_batch_eligibility_indexed(
                plan_data[run_id],
                set(execution_indices_with_status.get(run_id, {}).keys()),
            )
            batch_eligibility = "computed"
            if batch_executable and batch_eligible_count > 0:
                batch_eligible_count = batch_eligible_count
            else:
                batch_eligible_count = 0

        run_summaries.append(
            {
                "run_id": run_id,
                "run_label": raw.get("run_label", run_id) if isinstance(raw.get("run_label"), str) else run_id,
                "timestamp": timestamp,
                "cluster_count": raw.get("cluster_count", 0) if isinstance(raw.get("cluster_count"), int) else 0,
                "batchEligibility": batch_eligibility,
                "batchExecutable": batch_executable,
                "batchEligibleCount": batch_eligible_count,
            }
        )

    # Sort by timestamp descending (newest first)
    # Sort by timestamp descending (newest first)
    def get_sort_key(entry: dict[str, object]) -> datetime:
        ts = entry.get("timestamp", "")
        parsed = parse_iso_to_utc(ts)
        return parsed if parsed else _MIN_DATETIME

    run_summaries.sort(key=get_sort_key, reverse=True)

    # Store only the most recent runs (bounded for index size)
    total_count = len(run_summaries)
    recent_runs = run_summaries[:max_runs]

    # Add execution index diagnostics for bundle debugging
    # This includes scan metadata: total found, run_ids discovered, sample files, etc.
    exec_diagnostics_with_version = dict(exec_diagnostics) if exec_diagnostics else {}
    exec_diagnostics_with_version["_execution_index_collector_version"] = EXECUTION_INDEX_COLLECTOR_VERSION

    result = {
        "runs": recent_runs,
        "total_count": total_count,
        "generated_at": _get_current_timestamp(),
        "version": 3,  # Schema version 3: includes _execution_index_diagnostics
        # Internal data for API layer - enables executionSummary computation without filesystem access
        # _plan_data: run_id -> plan artifact dict
        # _execution_indices: run_id -> {candidate_index: status_string}
        "_plan_data": plan_data,
        "_execution_indices": execution_indices_with_status,
        # Execution index diagnostics: scan metadata for bundle debugging
        # Includes total found, run_ids discovered, sample files, skipped reasons
        "_execution_index_diagnostics": exec_diagnostics_with_version,
    }

    return result


def _extract_run_ids_from_filename(filename: str, marker: str) -> list[str]:
    """Extract run_id from a filename by finding the marker and stripping everything after.

    Args:
        filename: The filename (without extension) to extract run_id from
        marker: The marker to find (e.g., "-next-check-plan", "-next-check-execution")

    Returns:
        List containing the run_id (extracted by finding marker anywhere in filename)
    """
    if not filename or not marker:
        return []

    # Find marker anywhere in filename (not just at end)
    marker_index = filename.find(marker)
    if marker_index < 0:
        return []

    base = filename[:marker_index]
    if not base:
        return []

    return [base]


def _compute_batch_eligibility_indexed(
    plan_data: dict[str, object],
    execution_indices: set[int],
) -> tuple[bool, int]:
    """Compute batch eligibility using pre-loaded plan data (no filesystem access).

    This is used during index generation where plan data is already in memory.

    Args:
        plan_data: The next-check-plan artifact data
        execution_indices: Set of already-executed candidate indices

    Returns:
        Tuple of (batchExecutable: bool, batchEligibleCount: int)
    """
    # Get candidates from plan
    candidates_data: list[dict[str, object]] = []
    if "candidates" in plan_data and isinstance(plan_data["candidates"], list):
        candidates_data = cast(list[dict[str, object]], plan_data["candidates"])
    elif "payload" in plan_data and isinstance(plan_data["payload"], dict):
        payload = cast(dict[str, object], plan_data["payload"])
        if "candidates" in payload and isinstance(payload["candidates"], list):
            candidates_data = cast(list[dict[str, object]], payload["candidates"])

    if not candidates_data:
        return False, 0

    # Count eligible candidates using the same logic as run_batch_next_checks.py
    # IMPORTANT: Use candidateIndex from plan artifact if present (for non-contiguous cases),
    # fall back to enumerate index for backward compatibility
    eligible_count = 0
    for idx, candidate in enumerate(candidates_data):
        # Get the actual candidate index from the plan artifact if present
        # This handles non-contiguous candidateIndex values
        plan_candidate_index = candidate.get("candidateIndex")
        if isinstance(plan_candidate_index, int):
            actual_idx = plan_candidate_index
        else:
            actual_idx = idx

        # Already executed? (check against the actual index)
        if actual_idx in execution_indices:
            continue

        # Must be safe to automate
        if not candidate.get("safeToAutomate"):
            continue

        # Must have a valid command family
        family = candidate.get("suggestedCommandFamily")
        if not family or not isinstance(family, str):
            continue

        # Must have a description
        description = candidate.get("description")
        if not description or not isinstance(description, str):
            continue

        # Must have target context info
        target_context = candidate.get("targetContext")
        if not target_context or not isinstance(target_context, str):
            continue

        # Check approval requirement
        requires_approval = candidate.get("requiresOperatorApproval")
        if requires_approval:
            approval_status = str(candidate.get("approvalStatus") or "").lower()
            if approval_status != "approved":
                continue

        # Check for duplicates
        if candidate.get("duplicateOfExistingEvidence"):
            continue

        eligible_count += 1

    return eligible_count > 0, eligible_count


def _get_current_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


# Re-export for backward compatibility
__all__ = [
    "_build_recent_runs_summary",
    "_compute_batch_eligibility_indexed",
    "_extract_run_ids_from_filename",
    "EXECUTION_INDEX_COLLECTOR_VERSION",
]