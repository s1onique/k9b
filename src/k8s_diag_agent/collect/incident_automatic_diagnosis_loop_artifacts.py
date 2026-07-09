"""Automatic diagnosis loop artifact functions.

This module contains:
- Artifact path helpers
- Artifact write functions for hypothesis burst, pass, final hypotheses, and summary

These functions handle artifact persistence for the automatic diagnosis loop.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .incident_diagnosis_pass_contracts import PassResult
from .incident_hypothesis_burst import HypothesisBurst

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


# =============================================================================
# Artifact Paths
# =============================================================================


def _get_automatic_diagnosis_dir(external_analysis_dir: Path, run_id: str) -> Path:
    """Get the automatic-diagnosis artifact directory.

    Uses the health run_id for artifact naming to preserve health run identity.
    """
    return external_analysis_dir / "automatic-diagnosis" / run_id


def _hypothesis_burst_path(artifact_dir: Path, run_id: str, incident_id: str) -> Path:
    """Get path for hypothesis burst artifact."""
    return artifact_dir / f"{run_id}-{incident_id}-hypothesis-burst.json"


def _pass_artifact_path(artifact_dir: Path, run_id: str, incident_id: str, pass_index: int) -> Path:
    """Get path for pass artifact."""
    return artifact_dir / f"{run_id}-{incident_id}-pass-{pass_index:03d}.json"


def _final_hypotheses_path(artifact_dir: Path, run_id: str, incident_id: str) -> Path:
    """Get path for final hypotheses artifact."""
    return artifact_dir / f"{run_id}-{incident_id}-final-hypotheses.json"


def _summary_path(artifact_dir: Path, run_id: str) -> Path:
    """Get path for loop summary artifact."""
    return artifact_dir / f"{run_id}-summary.json"


# =============================================================================
# Artifact Writers
# =============================================================================


def write_hypothesis_burst_artifact(
    artifact_dir: Path,
    run_id: str,
    incident_id: str,
    burst: HypothesisBurst,
) -> dict[str, Any]:
    """Write hypothesis burst artifact.

    Args:
        artifact_dir: Directory for automatic-diagnosis artifacts
        run_id: Health run identity (from scheduler)
        incident_id: Incident ID
        burst: Hypothesis burst result

    Returns:
        Write result dict with 'written' and 'path'
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = _hypothesis_burst_path(artifact_dir, run_id, incident_id)

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "automatic-diagnosis-hypothesis-burst",
        "run_id": run_id,
        "incident_id": incident_id,
        "generated_at": datetime.now(UTC).isoformat(),
        **burst.to_dict(),
    }

    try:
        path.write_text(json.dumps(artifact, indent=2, default=str))
        _logger.info(
            "automatic-diagnosis-hypothesis-burst-written",
            extra={
                "run_id": run_id,
                "incident_id": incident_id,
                "path": str(path),
                "hypothesis_count": len(burst.hypotheses),
            },
        )
        return {"written": True, "path": str(path)}
    except Exception as exc:
        _logger.exception("Failed to write hypothesis burst artifact")
        return {"written": False, "path": str(path), "error": str(exc)}


def write_pass_artifact(
    artifact_dir: Path,
    run_id: str,
    incident_id: str,
    pass_result: PassResult,
) -> dict[str, Any]:
    """Write pass artifact.

    Args:
        artifact_dir: Directory for automatic-diagnosis artifacts
        run_id: Health run identity (from scheduler)
        incident_id: Incident ID
        pass_result: Pass result

    Returns:
        Write result dict with 'written' and 'path'
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = _pass_artifact_path(artifact_dir, run_id, incident_id, pass_result.pass_index)

    artifact = pass_result.to_dict()

    try:
        path.write_text(json.dumps(artifact, indent=2, default=str))
        _logger.info(
            "automatic-diagnosis-pass-written",
            extra={
                "run_id": run_id,
                "incident_id": incident_id,
                "pass_index": pass_result.pass_index,
                "path": str(path),
                "checks_executed": len(pass_result.checks_executed),
                "decision": pass_result.decision_action,
            },
        )
        return {"written": True, "path": str(path)}
    except Exception as exc:
        _logger.exception("Failed to write pass artifact")
        return {"written": False, "path": str(path), "error": str(exc)}


def write_final_hypotheses_artifact(
    artifact_dir: Path,
    run_id: str,
    incident_id: str,
    hypotheses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write final hypotheses artifact.

    Args:
        artifact_dir: Directory for automatic-diagnosis artifacts
        run_id: Health run identity (from scheduler)
        incident_id: Incident ID
        hypotheses: Final hypothesis list

    Returns:
        Write result dict with 'written' and 'path'
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = _final_hypotheses_path(artifact_dir, run_id, incident_id)

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "automatic-diagnosis-final-hypotheses",
        "run_id": run_id,
        "incident_id": incident_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "hypotheses": hypotheses,
    }

    try:
        path.write_text(json.dumps(artifact, indent=2, default=str))
        _logger.info(
            "automatic-diagnosis-final-hypotheses-written",
            extra={
                "run_id": run_id,
                "incident_id": incident_id,
                "path": str(path),
                "hypothesis_count": len(hypotheses),
            },
        )
        return {"written": True, "path": str(path)}
    except Exception as exc:
        _logger.exception("Failed to write final hypotheses artifact")
        return {"written": False, "path": str(path), "error": str(exc)}


def write_summary_artifact(
    artifact_dir: Path,
    run_id: str,
    collector_run_id: str,
    incidents_seen: int,
    incidents_eligible: int,
    incidents_processed: int,
    hypothesis_bursts_written: int,
    total_passes_completed: int,
    total_checks_executed: int,
    stop_reason: str,
    incident_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write loop summary artifact.

    Args:
        artifact_dir: Directory for automatic-diagnosis artifacts
        run_id: Health run identity (from scheduler)
        collector_run_id: Batch collector run ID
        incidents_seen: Number of incidents seen
        incidents_eligible: Number of eligible incidents
        incidents_processed: Number of incidents processed
        hypothesis_bursts_written: Number of hypothesis bursts written
        total_passes_completed: Total passes completed
        total_checks_executed: Total checks executed
        stop_reason: Overall stop reason
        incident_results: Per-incident results

    Returns:
        Write result dict with 'written' and 'path'
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = _summary_path(artifact_dir, run_id)

    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "automatic-diagnosis-summary",
        "run_id": run_id,
        "collector_run_id": collector_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "incidents_seen": incidents_seen,
            "incidents_eligible": incidents_eligible,
            "incidents_processed": incidents_processed,
            "hypothesis_bursts_written": hypothesis_bursts_written,
            "total_passes_completed": total_passes_completed,
            "total_checks_executed": total_checks_executed,
            "stop_reason": stop_reason,
        },
        "incident_results": incident_results,
    }

    try:
        path.write_text(json.dumps(artifact, indent=2, default=str))
        _logger.info(
            "automatic-diagnosis-summary-written",
            extra={
                "run_id": run_id,
                "collector_run_id": collector_run_id,
                "path": str(path),
                "incidents_processed": incidents_processed,
                "total_passes_completed": total_passes_completed,
                "total_checks_executed": total_checks_executed,
            },
        )
        return {"written": True, "path": str(path)}
    except Exception as exc:
        _logger.exception("Failed to write summary artifact")
        return {"written": False, "path": str(path), "error": str(exc)}


__all__ = [
    "write_hypothesis_burst_artifact",
    "write_pass_artifact",
    "write_final_hypotheses_artifact",
    "write_summary_artifact",
]
