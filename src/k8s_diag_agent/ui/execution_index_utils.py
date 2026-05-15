"""Shared execution artifact index utilities.

This module provides utility functions for collecting execution indices from
next-check execution artifacts. It centralizes the scanning logic to ensure
consistency between the index-backed path and fresh worklist path.

The key insight is that both paths must use the same artifact discovery:
- Use artifact `run_id` field as the primary source of truth
- Fall back to filename parsing only when the `run_id` field is missing
- Skip review artifacts (alertmanager/usefulness reviews)
- Handle various execution artifact naming patterns

See: https://github.com/s1onique/k9b/issues/XXX (Recent Runs execution summary mismatch)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TypedDict

from ..security.path_validation import SecurityError, validate_run_id

logger = logging.getLogger(__name__)

# Pattern for extracting run_id from execution artifact filenames
# Matches: {run_id}-next-check-execution[-{index}].json
# The key is finding "-next-check-execution" as a suffix delimiter, not inside the run_id
_EXECUTION_MARKER_PATTERN = re.compile(r"^(.+?)(-next-check-execution(?:-\d+)?)\.json$")


class ExecutionArtifactRecord(TypedDict):
    """Rich record for execution artifacts - used by both index and worklist paths."""
    candidate_index: int
    status: str
    artifact_path: str
    timestamp: str | None


def _extract_run_id_from_filename(filename: str) -> str | None:
    """Extract run_id from an execution artifact filename.
    
    This handles the case where "-next-check-execution" appears in the filename.
    The marker should be at the END of the filename, not inside the run_id.
    
    For example:
    - "health-run-20260515T215749Z-next-check-execution-0.json" -> "health-run-20260515T215749Z"
    - "health-run-20260515T215749Z-next-check-execution.json" -> "health-run-20260515T215749Z"
    """
    match = _EXECUTION_MARKER_PATTERN.match(filename)
    if match:
        return match.group(1)
    return None


def collect_execution_artifacts_for_all_runs(
    external_analysis_dir: Path,
    health_root: Path | None = None,
) -> tuple[dict[str, dict[int, ExecutionArtifactRecord]], dict[str, object]]:
    """Collect full execution artifact records for all runs using a one-pass scan.
    
    This is the PRIMARY shared collector that returns rich records suitable for both:
    1. _build_recent_runs_summary() - derives indices from these records
    2. _scan_execution_artifacts_for_worklist() - builds overlays from these records
    
    The one-pass design is O(artifacts) instead of O(runs × artifacts).
    
    Artifact discovery rules (in priority order):
    1. Use artifact's own `run_id` field as the primary key
    2. Fall back to filename parsing only when run_id field is missing
    3. Skip artifacts where run_id cannot be determined
    4. Skip review artifacts (alertmanager/usefulness reviews)
    
    Args:
        external_analysis_dir: Path to the external-analysis directory
        health_root: Optional health root for computing relative artifact paths
    
    Returns:
        Tuple of (artifacts_by_run, diagnostics):
        - artifacts_by_run: run_id -> {candidate_index: ExecutionArtifactRecord}
        - diagnostics: dict with scan metadata and evidence
    """
    result: dict[str, dict[int, ExecutionArtifactRecord]] = {}
    
    # Track counters locally to avoid mypy dict[str, object] issues
    _total_found = 0
    _total_matched = 0
    _skipped_no_run_id = 0
    _skipped_purpose_mismatch = 0
    _skipped_parse_error = 0
    _run_ids_discovered: list[str] = []
    _sample_filenames: list[str] = []
    _sample_skipped_reasons: list[str] = []
    
    if not external_analysis_dir.is_dir():
        return result, {
            "total_execution_artifacts_found": 0,
            "total_execution_artifacts_matched": 0,
            "total_execution_artifacts_skipped_no_run_id": 0,
            "total_execution_artifacts_skipped_purpose_mismatch": 0,
            "total_execution_artifacts_skipped_parse_error": 0,
            "run_ids_discovered": [],
            "sample_filenames": [],
            "sample_skipped_reasons": [],
        }
    
    # One-pass scan: find all execution artifacts
    all_files: list[Path] = list(external_analysis_dir.glob("*-next-check-execution*.json"))
    _total_found = len(all_files)
    
    for artifact_file in sorted(all_files):
        try:
            raw = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                _skipped_parse_error += 1
                continue
            
            # Verify purpose
            purpose = raw.get("purpose")
            if purpose != "next-check-execution":
                _skipped_purpose_mismatch += 1
                if len(_sample_skipped_reasons) < 5:
                    _sample_skipped_reasons.append(f"{artifact_file.name}: purpose={purpose}")
                continue
            
            # Extract run_id: use artifact field as primary, filename as fallback
            artifact_run_id = raw.get("run_id")
            run_id: str | None = None
            if isinstance(artifact_run_id, str) and artifact_run_id:
                # Primary: use the artifact's own run_id field
                run_id = artifact_run_id
            else:
                # Fallback: extract from filename
                run_id = _extract_run_id_from_filename(artifact_file.name)
                if not run_id:
                    _skipped_no_run_id += 1
                    if len(_sample_skipped_reasons) < 5:
                        _sample_skipped_reasons.append(
                            f"{artifact_file.name}: no run_id field, filename parse failed"
                        )
                    continue
            
            # Validate run_id for security (skip artifacts with invalid run_ids)
            try:
                validate_run_id(run_id)
            except SecurityError:
                _skipped_no_run_id += 1
                if len(_sample_skipped_reasons) < 5:
                    _sample_skipped_reasons.append(
                        f"{artifact_file.name}: run_id validation failed for '{run_id}'"
                    )
                continue
            
            # Extract execution data
            exec_payload = raw.get("payload", {})
            if not isinstance(exec_payload, dict):
                _skipped_parse_error += 1
                continue
            
            candidate_index = exec_payload.get("candidateIndex")
            if not isinstance(candidate_index, int):
                _skipped_parse_error += 1
                if len(_sample_skipped_reasons) < 5:
                    _sample_skipped_reasons.append(
                        f"{artifact_file.name}: invalid candidateIndex type={type(candidate_index)}"
                    )
                continue
            
            # Extract status
            status = raw.get("status")
            if not isinstance(status, str):
                status = "unknown"
            
            # Compute artifact path relative to health_root
            if health_root is not None:
                try:
                    artifact_path = str(artifact_file.relative_to(health_root))
                except ValueError:
                    artifact_path = str(artifact_file)
            else:
                artifact_path = str(artifact_file)
            
            # Extract timestamp
            timestamp = raw.get("timestamp")
            if not isinstance(timestamp, str):
                timestamp = None
            
            # Store in result with rich record
            if run_id not in result:
                result[run_id] = {}
                _run_ids_discovered.append(run_id)
                if len(_sample_filenames) < 5:
                    _sample_filenames.append(artifact_file.name)
            
            result[run_id][candidate_index] = ExecutionArtifactRecord(
                candidate_index=candidate_index,
                status=status,
                artifact_path=artifact_path,
                timestamp=timestamp,
            )
            _total_matched += 1
            
        except (OSError, json.JSONDecodeError) as exc:
            _skipped_parse_error += 1
            if len(_sample_skipped_reasons) < 5:
                _sample_skipped_reasons.append(f"{artifact_file.name}: {exc}")
            continue
    
    return result, {
        "total_execution_artifacts_found": _total_found,
        "total_execution_artifacts_matched": _total_matched,
        "total_execution_artifacts_skipped_no_run_id": _skipped_no_run_id,
        "total_execution_artifacts_skipped_purpose_mismatch": _skipped_purpose_mismatch,
        "total_execution_artifacts_skipped_parse_error": _skipped_parse_error,
        "run_ids_discovered": _run_ids_discovered,
        "sample_filenames": _sample_filenames,
        "sample_skipped_reasons": _sample_skipped_reasons,
    }


def collect_execution_indices_for_all_runs(
    external_analysis_dir: Path,
    health_root: Path | None = None,
) -> tuple[dict[str, dict[int, str]], dict[str, object]]:
    """Collect execution indices for all runs using a one-pass scan.
    
    DEPRECATED: Use collect_execution_artifacts_for_all_runs() instead, which returns
    richer records that can be used by both the index and worklist paths.
    
    This function is kept for backward compatibility only.
    
    Returns:
        Tuple of (execution_indices, diagnostics):
        - execution_indices: run_id -> {candidate_index: status_string}
        - diagnostics: dict with scan metadata and evidence
    """
    artifacts_by_run, diagnostics = collect_execution_artifacts_for_all_runs(
        external_analysis_dir, 
        health_root=health_root
    )
    
    # Derive simple index from rich records
    indices: dict[str, dict[int, str]] = {}
    for run_id, run_artifacts in artifacts_by_run.items():
        indices[run_id] = {
            candidate_index: record["status"]
            for candidate_index, record in run_artifacts.items()
        }
    
    return indices, diagnostics


def collect_execution_indices_for_run(
    external_analysis_dir: Path,
    run_id: str,
) -> dict[int, str]:
    """Collect execution indices and statuses for a run.

    DEPRECATED: This function is kept for backward compatibility only.
    New code should use collect_execution_indices_for_all_runs() for O(artifacts)
    instead of O(runs × artifacts) complexity.

    This is now a thin wrapper around collect_execution_indices_for_all_runs()
    to ensure consistent artifact discovery between all paths.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        run_id: The run ID to filter by

    Returns:
        Dict mapping candidate_index (int) -> status (str)
        Empty dict if no execution artifacts found or directory doesn't exist.
    """
    if not external_analysis_dir.is_dir():
        return {}

    # Validate run_id first, preserving current invalid-run behavior
    try:
        validate_run_id(run_id)
    except SecurityError:
        return {}

    # Delegate to the shared all-runs collector for consistent discovery
    all_indices, _ = collect_execution_indices_for_all_runs(external_analysis_dir)
    return all_indices.get(run_id, {})
