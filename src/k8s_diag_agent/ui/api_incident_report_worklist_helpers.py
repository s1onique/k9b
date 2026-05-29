"""Execution artifact overlay helpers for worklist derivation.

These helpers scan external-analysis artifacts to derive execution state
for worklist items. They are worklist-specific and do not participate in
incident report building.

This module is an extraction from api_incident_report.py to reduce its
LLM-friendly file size while preserving backward-compatible re-exports.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .execution_index_utils import (
    collect_execution_artifacts_for_all_runs,
)

# =============================================================================
# Execution Artifact Overlay for Worklist
# =============================================================================


@dataclass(frozen=True)
class ExecutionArtifactOverlay:
    """Overlay data from an execution artifact for worklist derivation."""
    candidate_id: str | None
    candidate_index: int | None
    command_family: str | None
    target_cluster: str | None
    artifact_path: str | None
    status: str | None  # success | failed | timed-out
    timestamp: str | None


def _scan_execution_artifacts_for_worklist(
    health_root: Path,
    run_id: str,
) -> tuple[Sequence[ExecutionArtifactOverlay], dict[str, int]]:
    """Scan external-analysis directory for execution artifacts matching this run.
    
    Returns tuple of (overlays, telemetry) where overlays can be used to derive
    execution state for worklist items.
    
    This function uses the shared one-pass collector from execution_index_utils.py
    to ensure consistency with the index-backed path. Both paths now use identical
    artifact discovery logic.
    
    CRITICAL: This function uses collect_execution_artifacts_for_all_runs() which
    finds artifacts by their run_id field first, then falls back to filename matching.
    This ensures worklist path matches index path even when artifact filenames differ
    from the run_id field (e.g., filename="old-run-next-check-execution-0.json" but
    artifact field run_id="current-run").
    
    Matching criteria (all non-None fields must match):
    - candidate_index AND command_family AND target_cluster (primary)
    - OR candidate_id AND target_cluster (fallback)
    
    Telemetry tracks scan performance and match statistics.
    """
    telemetry: dict[str, int] = {
        "execution_artifacts_found": 0,
        "execution_artifacts_matched": 0,
        "execution_artifacts_skipped_mismatch": 0,
        "execution_artifacts_parse_failed": 0,
    }
    
    overlays: list[ExecutionArtifactOverlay] = []
    
    external_analysis_dir = health_root / "external-analysis"
    if not external_analysis_dir.exists():
        return overlays, telemetry
    
    # Use the rich record collector for exact artifact matching
    # This returns ExecutionArtifactRecord with artifact_path, status, timestamp
    # The collector uses run_id field as primary key, ensuring we find artifacts
    # even when their filenames differ from the run_id field
    artifacts_by_run, exec_diagnostics = collect_execution_artifacts_for_all_runs(
        external_analysis_dir,
        health_root=health_root,
    )
    
    # Get execution records for this specific run
    run_artifacts = artifacts_by_run.get(run_id, {})
    telemetry["execution_artifacts_found"] = cast(int, exec_diagnostics.get("total_execution_artifacts_found", 0))
    telemetry["execution_artifacts_matched"] = len(run_artifacts)
    
    # Build overlays from the exact records found by the shared collector
    # Each record has: candidate_index, status, artifact_path, timestamp
    # We need to read the artifact to get additional fields (candidate_id, command_family, target_cluster)
    # This is a targeted read of only the artifacts already matched by the collector
    for candidate_index, record in run_artifacts.items():
        artifact_path = record.get("artifact_path")
        if not artifact_path:
            continue
        
        # Resolve artifact path relative to health_root
        # The artifact_path in the record is relative to health_root
        artifact_file = health_root / artifact_path if not Path(artifact_path).is_absolute() else Path(artifact_path)
        
        if not artifact_file.exists():
            # Try constructing from external_analysis_dir directly
            artifact_file = external_analysis_dir / Path(artifact_path).name
        
        if not artifact_file.exists():
            # Skip if we can't find the artifact file
            telemetry["execution_artifacts_parse_failed"] += 1
            continue
        
        try:
            raw = json.loads(artifact_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                telemetry["execution_artifacts_parse_failed"] += 1
                continue
            
            payload = raw.get("payload", {})
            if not isinstance(payload, dict):
                telemetry["execution_artifacts_parse_failed"] += 1
                continue
            
            # Extract enrichment fields from the artifact
            candidate_id = payload.get("candidateId") or payload.get("candidate_id")
            command_family = payload.get("commandFamily") or payload.get("command_family")
            if not command_family:
                tool_name = payload.get("tool_name") or ""
                if isinstance(tool_name, str) and "-" in tool_name:
                    command_family = tool_name.split("-", 1)[1] if "-" in tool_name else tool_name
            target_cluster = payload.get("clusterLabel") or payload.get("cluster_label") or payload.get("targetCluster")
            
            overlay = ExecutionArtifactOverlay(
                candidate_id=str(candidate_id) if candidate_id else None,
                candidate_index=candidate_index,
                command_family=str(command_family) if command_family else None,
                target_cluster=str(target_cluster) if target_cluster else None,
                artifact_path=artifact_path,
                status=record.get("status"),
                timestamp=record.get("timestamp"),
            )
            overlays.append(overlay)
            
        except (OSError, json.JSONDecodeError):
            telemetry["execution_artifacts_parse_failed"] += 1
            continue
    
    telemetry["execution_artifacts_matched"] = len(overlays)
    return overlays, telemetry


def _match_execution_overlay_to_queue_item(
    overlay: ExecutionArtifactOverlay,
    queue_item_candidate_id: str | None,
    queue_item_candidate_index: int | None,
    queue_item_command_family: str | None,
    queue_item_target_cluster: str | None,
) -> bool:
    """Check if an execution artifact overlay matches a queue item.
    
    Matching rules (all non-None overlay fields must match):
    1. Primary: candidate_index + command_family + target_cluster (all required)
    2. Fallback: candidate_id + target_cluster (all required)
    
    Returns True if overlay should be applied to this queue item.
    """
    # Primary match: candidate_index + command_family + target_cluster
    if overlay.candidate_index is not None and overlay.command_family is not None and overlay.target_cluster is not None:
        index_match = overlay.candidate_index == queue_item_candidate_index
        family_match = overlay.command_family.lower() == queue_item_command_family.lower() if queue_item_command_family else False
        cluster_match = overlay.target_cluster == queue_item_target_cluster
        
        if index_match and family_match and cluster_match:
            return True
    
    # Fallback match: candidate_id + target_cluster
    if overlay.candidate_id and overlay.target_cluster:
        id_match = overlay.candidate_id == queue_item_candidate_id
        cluster_match = overlay.target_cluster == queue_item_target_cluster
        
        if id_match and cluster_match:
            return True
    
    return False


def _derive_execution_state_from_artifact(status: str | None) -> str:
    """Derive execution_state string from artifact status.
    
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
        # Any other status means execution completed (artifact was created)
        return "executed-success"
