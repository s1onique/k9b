"""Automatic diagnosis loop orchestrator for hypothesis-burst multipass diagnosis.

This module provides the main loop orchestrator that:
1. Runs hypothesis burst (Pass 0) - generates hypotheses from existing evidence
2. Runs evidence passes (Pass 1+) - executes discriminating checks
3. Reranks hypotheses based on evidence
4. Writes artifacts for each pass and final summary

Design constraints:
- Pure functions only for loop logic
- Uses existing fake runner for check execution
- Bounded budgets (max_passes, max_checks, time budget)
- Read-only checks only
- Writes artifacts to external_analysis_dir
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from .incident_diagnosis_pass_executor import (
    PassResult,
    StopDecision,
    execute_pass,
    select_checks_for_pass,
)
from .incident_hypothesis_burst import (
    HypothesisBurst,
    run_hypothesis_burst,
)

_logger = logging.getLogger(__name__)

# =============================================================================
# Schema Version
# =============================================================================

SCHEMA_VERSION = "1.0"

# =============================================================================
# Stop Reasons
# =============================================================================


class DiagnosisLoopStopReason(StrEnum):
    """Reasons for stopping the diagnosis loop."""

    CONFIDENCE_THRESHOLD = "confidence_threshold_reached"
    MAX_PASSES_REACHED = "max_passes_reached"
    ALL_HYPOTHESES_FALSIFIED = "all_hypotheses_falsified"
    NO_MORE_CHECKS = "no_discriminating_checks"
    CHECK_BUDGET_EXHAUSTED = "check_budget_exhausted"
    TIME_BUDGET_EXHAUSTED = "time_budget_exhausted"
    ERROR = "error"


# =============================================================================
# Result Models
# =============================================================================


@dataclass
class HypothesisLoopConfig:
    """Configuration for the hypothesis loop."""

    max_passes_per_incident: int = 2  # Pass 0 (burst) + Pass 1 (evidence) = 2
    max_checks_per_pass: int = 3
    max_total_checks: int = 6
    max_seconds_per_incident: int = 45
    min_confidence_to_stop: float = 0.78

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return {
            "max_passes_per_incident": self.max_passes_per_incident,
            "max_checks_per_pass": self.max_checks_per_pass,
            "max_total_checks": self.max_total_checks,
            "max_seconds_per_incident": self.max_seconds_per_incident,
            "min_confidence_to_stop": self.min_confidence_to_stop,
        }


@dataclass
class HypothesisLoopResult:
    """Result of running the hypothesis loop for one incident."""

    incident_id: str
    run_id: str  # Health run identity (from scheduler)
    collector_run_id: str  # Batch collector run ID
    started_at: str
    completed_at: str | None = None
    status: str = "running"  # running|success|failed
    stop_reason: str | None = None
    stop_reason_detail: str = ""
    pass_results: list[dict[str, Any]] = field(default_factory=list)
    final_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    total_passes_completed: int = 0
    total_checks_executed: int = 0
    hypothesis_burst_written: bool = False
    passes_written: int = 0
    summary_written: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "incident_id": self.incident_id,
            "run_id": self.run_id,
            "collector_run_id": self.collector_run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "stop_reason_detail": self.stop_reason_detail,
            "pass_results": self.pass_results,
            "final_hypotheses": self.final_hypotheses,
            "total_passes_completed": self.total_passes_completed,
            "total_checks_executed": self.total_checks_executed,
            "hypothesis_burst_written": self.hypothesis_burst_written,
            "passes_written": self.passes_written,
            "summary_written": self.summary_written,
            "error": self.error,
        }
        return result


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


# =============================================================================
# Main Loop
# =============================================================================


def run_automatic_diagnosis_hypothesis_loop(
    incident: dict[str, Any],
    case_file: dict[str, Any],
    external_analysis_dir: Path,
    run_id: str,  # Health run identity from scheduler
    collector_run_id: str,
    config: HypothesisLoopConfig | None = None,
    now: datetime | None = None,
) -> HypothesisLoopResult:
    """Run the hypothesis-burst multipass diagnosis loop.

    This is the main entry point for the hypothesis-burst diagnosis feature.

    Pass structure:
    - Pass 0: Hypothesis burst (generates hypotheses, no K8s reads)
    - Pass 1: Evidence checks (executes selected checks, reranks)
    - Pass 2+: Targeted follow-up (based on evidence, excludes executed checks)

    Args:
        incident: Incident data
        case_file: Case file with evidence
        external_analysis_dir: Directory for artifacts
        run_id: Health run identity (from scheduler, preserved in artifact names)
        collector_run_id: Batch collector run ID
        config: Loop configuration
        now: Optional datetime for deterministic timestamps

    Returns:
        HypothesisLoopResult with loop outcome
    """
    resolved_config = config or HypothesisLoopConfig()
    resolved_now = now if now is not None else datetime.now(UTC)
    incident_id = incident.get("incident_id", "unknown")

    result = HypothesisLoopResult(
        incident_id=incident_id,
        run_id=run_id,  # Preserve health run identity
        collector_run_id=collector_run_id,
        started_at=resolved_now.isoformat(),
    )

    _logger.info(
        "automatic-diagnosis-loop-start",
        extra={
            "incident_id": incident_id,
            "run_id": run_id,
            "collector_run_id": collector_run_id,
        },
    )

    try:
        # Pass 0: Hypothesis burst (no K8s reads)
        artifact_dir = _get_automatic_diagnosis_dir(external_analysis_dir, run_id)

        burst = run_hypothesis_burst(
            incident=incident,
            case_file=case_file,
            config=resolved_config.to_dict(),
            now=resolved_now,
        )

        # Write hypothesis burst artifact
        burst_write = write_hypothesis_burst_artifact(
            artifact_dir=artifact_dir,
            run_id=run_id,
            incident_id=incident_id,
            burst=burst,
        )
        result.hypothesis_burst_written = burst_write.get("written", False)

        if not burst.hypotheses:
            result.completed_at = datetime.now(UTC).isoformat()
            result.status = "success"
            result.stop_reason = DiagnosisLoopStopReason.NO_MORE_CHECKS.value
            result.stop_reason_detail = "no hypotheses generated"
            return result

        # Convert hypotheses to dicts for processing
        current_hypotheses = [h.to_dict() for h in burst.hypotheses]

        # Track executed checks across passes
        all_executed_check_ids: set[str] = set()
        all_evidence_deltas: list[dict[str, Any]] = []

        # Run evidence passes (Pass 1+)
        for pass_idx in range(1, resolved_config.max_passes_per_incident + 1):
            # Check time budget
            elapsed = (datetime.now(UTC) - resolved_now).total_seconds()
            if elapsed >= resolved_config.max_seconds_per_incident:
                result.stop_reason = DiagnosisLoopStopReason.TIME_BUDGET_EXHAUSTED.value
                result.stop_reason_detail = f"time budget exceeded: {elapsed:.1f}s"
                break

            # Check total check budget
            if result.total_checks_executed >= resolved_config.max_total_checks:
                result.stop_reason = DiagnosisLoopStopReason.CHECK_BUDGET_EXHAUSTED.value
                result.stop_reason_detail = f"check budget exhausted: {result.total_checks_executed}"
                break

            # Emit pass start event
            _logger.info(
                "automatic-diagnosis-pass-start",
                extra={
                    "incident_id": incident_id,
                    "run_id": run_id,
                    "pass_index": pass_idx,
                },
            )

            # Extract available identity from incident/case_file
            identity = _extract_identity(incident, case_file)

            # Select checks for this pass (targeted for pass_idx >= 2)
            selected_checks = select_checks_for_pass(
                hypotheses=current_hypotheses,
                available_identity=identity,
                pass_index=pass_idx,
                max_checks=resolved_config.max_checks_per_pass,
                executed_check_ids=all_executed_check_ids,
                evidence_deltas=all_evidence_deltas,
            )

            # Execute the pass
            pass_result = execute_pass(
                pass_index=pass_idx,
                incident=incident,
                hypotheses=current_hypotheses,
                selected_checks=selected_checks,
                available_identity=identity,
                config=resolved_config.to_dict(),
                now=resolved_now,
                prior_executed_check_ids=all_executed_check_ids,
                prior_evidence_deltas=all_evidence_deltas,
            )

            # Track executed checks and evidence
            for check_id in pass_result.executed_check_ids:
                all_executed_check_ids.add(check_id)
            all_evidence_deltas.extend(pass_result.evidence_deltas)

            # Update counts
            result.total_passes_completed += 1
            result.total_checks_executed += pass_result.checks_executed_count
            result.pass_results.append(pass_result.to_dict())

            # Write pass artifact
            pass_write = write_pass_artifact(
                artifact_dir=artifact_dir,
                run_id=run_id,
                incident_id=incident_id,
                pass_result=pass_result,
            )
            if pass_write.get("written"):
                result.passes_written += 1

            # Update hypotheses
            current_hypotheses = pass_result.hypotheses_after

            # Check stop conditions
            if pass_result.decision_action == StopDecision.STOP_CONFIDENCE_THRESHOLD:
                result.stop_reason = DiagnosisLoopStopReason.CONFIDENCE_THRESHOLD.value
                result.stop_reason_detail = pass_result.decision_reason
                break

            if pass_result.decision_action == StopDecision.STOP_ALL_HYPOTHESES_FALSIFIED:
                result.stop_reason = DiagnosisLoopStopReason.ALL_HYPOTHESES_FALSIFIED.value
                result.stop_reason_detail = pass_result.decision_reason
                break

            if pass_result.decision_action == StopDecision.STOP_NO_DISCRIMINATING_CHECKS:
                result.stop_reason = DiagnosisLoopStopReason.NO_MORE_CHECKS.value
                result.stop_reason_detail = pass_result.decision_reason
                break

            if pass_idx >= resolved_config.max_passes_per_incident:
                result.stop_reason = DiagnosisLoopStopReason.MAX_PASSES_REACHED.value
                result.stop_reason_detail = f"max passes ({resolved_config.max_passes_per_incident}) reached"
                break

        # Write final hypotheses
        write_final_hypotheses_artifact(
            artifact_dir=artifact_dir,
            run_id=run_id,
            incident_id=incident_id,
            hypotheses=current_hypotheses,
        )
        result.final_hypotheses = current_hypotheses

        # Set stop reason if not set
        if result.stop_reason is None:
            result.stop_reason = DiagnosisLoopStopReason.MAX_PASSES_REACHED.value
            result.stop_reason_detail = "loop completed without explicit stop"

        # Complete
        result.completed_at = datetime.now(UTC).isoformat()
        result.status = "success"

        _logger.info(
            "automatic-diagnosis-loop-complete",
            extra={
                "incident_id": incident_id,
                "run_id": run_id,
                "stop_reason": result.stop_reason,
                "total_passes": result.total_passes_completed,
                "total_checks": result.total_checks_executed,
            },
        )

    except Exception as exc:
        result.completed_at = datetime.now(UTC).isoformat()
        result.status = "failed"
        result.error = str(exc)[:500]
        result.stop_reason = DiagnosisLoopStopReason.ERROR.value
        result.stop_reason_detail = str(exc)
        _logger.exception("Automatic diagnosis loop failed")

    return result


def _extract_identity(
    incident: dict[str, Any],
    case_file: dict[str, Any],
) -> dict[str, str | None]:
    """Extract available identity parameters from incident/case_file.

    Args:
        incident: Incident data
        case_file: Case file

    Returns:
        Identity dict with namespace, object_name, pod_name, node_name
    """
    identity: dict[str, str | None] = {
        "namespace": None,
        "object_name": None,
        "pod_name": None,
        "node_name": None,
    }

    # Extract from incident signals
    signals = incident.get("signals", [])
    for signal in signals:
        if isinstance(signal, dict):
            if not identity["namespace"]:
                identity["namespace"] = signal.get("namespace")
            if not identity["object_name"]:
                identity["object_name"] = signal.get("object_name") or signal.get("pod_name")
            if not identity["pod_name"]:
                identity["pod_name"] = signal.get("pod_name")
            if not identity["node_name"]:
                identity["node_name"] = signal.get("node_name")

    # Extract from case_file
    if not identity["namespace"]:
        identity["namespace"] = case_file.get("namespace")
    if not identity["object_name"]:
        identity["object_name"] = case_file.get("object_name") or case_file.get("name")

    return identity


__all__ = [
    "SCHEMA_VERSION",
    "DiagnosisLoopStopReason",
    "HypothesisLoopConfig",
    "HypothesisLoopResult",
    "write_hypothesis_burst_artifact",
    "write_pass_artifact",
    "write_final_hypotheses_artifact",
    "write_summary_artifact",
    "run_automatic_diagnosis_hypothesis_loop",
]
