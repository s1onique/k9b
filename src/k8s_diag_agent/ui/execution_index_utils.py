"""Shared execution artifact index utilities.

This module provides utility functions for collecting execution indices from
next-check execution artifacts. It centralizes the scanning logic to ensure
consistency between the index-backed path and fresh worklist path.

See: https://github.com/s1onique/k9b/issues/XXX (Recent Runs execution summary mismatch)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

logger = logging.getLogger(__name__)


def collect_execution_indices_for_run(
    external_analysis_dir: Path,
    run_id: str,
) -> dict[int, str]:
    """Collect execution indices and statuses for a run using run_id-scoped glob.

    This function scans the external-analysis directory for execution artifacts
    belonging to a specific run using a run_id-scoped glob pattern:
        {run_id}-next-check-execution-*.json

    This ensures consistency with the fresh worklist path which uses the same
    run_id-scoped scanning approach. Previously, the index-backed path used
    a global glob pattern which could miss execution artifacts when the run_id
    field in the artifact didn't match expectations.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The run ID to filter by

    Returns:
        Dict mapping candidate_index (int) -> status (str)
        Empty dict if no execution artifacts found or directory doesn't exist.
    """
    result: dict[int, str] = {}

    if not external_analysis_dir.is_dir():
        return result

    try:
        validated_run_id = validate_run_id(run_id)
    except SecurityError:
        return result

    # Collect all execution artifact files matching target run_id by filename
    # Also scan all execution files to catch cases where filename doesn't match run_id field
    glob_patterns = [
        safe_run_artifact_glob(validated_run_id, "-next-check-execution-*.json"),
        safe_run_artifact_glob(validated_run_id, "-next-check-execution.json"),
    ]

    # Collect files matching run_id-scoped patterns
    all_files: list[Path] = []
    for pattern in glob_patterns:
        all_files.extend(external_analysis_dir.glob(pattern))
    
    # For run_id-scoped patterns, we need to check filename matches the target run_id
    # But also need to handle the case where filename doesn't match run_id field in artifact
    # by scanning all next-check-execution files and filtering by run_id field
    for pattern in ["*-next-check-execution-*.json", "*-next-check-execution.json"]:
        for f in external_analysis_dir.glob(pattern):
            if f not in all_files:
                all_files.append(f)
    
    for artifact_file in sorted(all_files):
        try:
            raw = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue

            if raw.get("purpose") != "next-check-execution":
                continue

            # Extract run_id from artifact's run_id field
            # This is the primary source of truth for associating artifacts with runs
            artifact_run_id = raw.get("run_id")
            
            # If run_id field is missing, rely on filename matching as fallback
            # This handles execution artifacts that don't have run_id in the artifact
            if not isinstance(artifact_run_id, str):
                # Verify via filename for artifacts without run_id field
                filename = artifact_file.stem
                marker = f"{run_id}-next-check-execution"
                if not filename.startswith(marker):
                    continue
            elif artifact_run_id != run_id:
                # Artifact's run_id doesn't match target - skip this artifact
                # The artifact belongs to a different run
                continue

            exec_payload = raw.get("payload", {})
            candidate_index = exec_payload.get("candidateIndex")

            # Extract status from artifact for failedCandidates derivation
            status = raw.get("status", "unknown")
            if not isinstance(status, str):
                status = "unknown"

            if isinstance(candidate_index, int):
                result[candidate_index] = status

        except (OSError, json.JSONDecodeError) as exc:
            logger.debug(
                "Skipped malformed execution artifact during index collection: %s",
                artifact_file.name,
                extra={
                    "run_id": run_id,
                    "error": str(exc),
                },
            )
            continue

    return result