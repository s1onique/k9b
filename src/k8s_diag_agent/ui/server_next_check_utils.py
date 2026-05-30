"""Utility functions for next-check server operations.

Extracted from server_next_checks.py to reduce file size and improve modularity.
These functions are used by the next-check mutation handlers.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any


def resolve_plan_candidate(
    candidates: Sequence[object],
    requested_candidate_id: str | None,
    requested_candidate_index: int | None,
) -> tuple[dict[str, object] | None, int | None]:
    """Resolve a plan candidate by ID or index.

    Args:
        candidates: Sequence of candidate dicts
        requested_candidate_id: Optional candidate ID to find
        requested_candidate_index: Optional candidate index to find

    Returns:
        Tuple of (candidate_entry, resolved_index) if found, else (None, None)
    """
    if not isinstance(candidates, Sequence):
        return None, None
    entries = list(candidates)
    found_entry: dict[str, object] | None = None
    found_position: int | None = None
    if requested_candidate_id:
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("candidateId")
            if isinstance(entry_id, str) and entry_id == requested_candidate_id:
                found_entry = dict(entry)
                found_position = idx
                break
    if found_entry is None and requested_candidate_index is not None:
        if 0 <= requested_candidate_index < len(entries):
            entry = entries[requested_candidate_index]
            if isinstance(entry, dict):
                found_entry = dict(entry)
                found_position = requested_candidate_index
    if found_entry is None:
        return None, None
    candidate_index_value: int | None = None
    explicit_index = found_entry.get("candidateIndex")
    if isinstance(explicit_index, int):
        candidate_index_value = explicit_index
    elif found_position is not None:
        candidate_index_value = found_position
    elif requested_candidate_index is not None:
        candidate_index_value = requested_candidate_index
    return found_entry, candidate_index_value


def find_candidate_in_all_plan_artifacts(
    health_root: Path,
    run_id: str,
    candidate_id: str | None,
    candidate_index: int | None,
) -> tuple[dict[str, object] | None, int | None, Path | None]:
    """Search for a candidate across all planner artifacts for the given run.

    This handles cases where the plan artifact path in the queue may differ from
    the current next_check_plan.artifact_path (e.g., due to plan regeneration).

    Args:
        health_root: Path to the health root directory (runs/health/)
        run_id: The run ID
        candidate_id: Optional candidate ID to find
        candidate_index: Optional candidate index to find

    Returns:
        Tuple of (candidate_entry, resolved_index, plan_path) if found.
    """
    import json

    from ..external_analysis.deterministic_next_check_promotion import collect_promoted_queue_entries
    from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

    # SECURITY: Validate run_id before using in glob pattern to prevent path traversal
    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        # Invalid run_id - cannot safely search, return empty result
        return None, None, None

    glob_pattern = safe_run_artifact_glob(validated_run_id, "-next-check-plan*.json")
    promotions = collect_promoted_queue_entries(health_root, validated_run_id)
    if promotions:
        entry, idx = resolve_plan_candidate(
            promotions,
            candidate_id,
            candidate_index,
        )
        if entry is not None and idx is not None:
            return dict(entry), idx, None

    external_analysis_dir = health_root / "external-analysis"
    if external_analysis_dir.exists():
        for artifact_file in external_analysis_dir.glob(glob_pattern):
            try:
                artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
                purpose = artifact_data.get("purpose")
                if purpose != "next-check-planning":
                    continue

                payload = artifact_data.get("payload", {})
                candidates = payload.get("candidates", [])
                entry, idx = resolve_plan_candidate(
                    candidates if isinstance(candidates, Sequence) else (),
                    candidate_id,
                    candidate_index,
                )
                if entry is not None and idx is not None:
                    return dict(entry), idx, Path("external-analysis") / artifact_file.name
            except (OSError, json.JSONDecodeError, ValueError):
                continue

    return None, None, None


def determine_execution_state_from_artifact(artifact: Any) -> str:
    """Determine execution state from an execution artifact.

    Args:
        artifact: The execution artifact from manual next-check execution.

    Returns:
        Execution state string: "executed-success", "executed-failed", or "timed-out".
    """
    from ..external_analysis.artifact import ExternalAnalysisStatus

    if artifact.timed_out:
        return "timed-out"
    if artifact.status == ExternalAnalysisStatus.SUCCESS:
        return "executed-success"
    return "executed-failed"


def relative_path(base: Path, target: object | None) -> str | None:
    """Compute relative path from base to target, returning None if target is None.

    Args:
        base: The base path to compute relative path from.
        target: The target path (or None).

    Returns:
        Relative path string from base to target, or str(target) if not relative.
        Returns None if target is None.
    """
    if target is None:
        return None
    candidate = Path(str(target))
    try:
        return str(candidate.relative_to(base))
    except ValueError:
        return str(candidate)
