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

This module is a facade that re-exports from specialized modules:
- incident_automatic_diagnosis_loop_state: HypothesisLoopConfig, HypothesisLoopResult, etc.
- incident_automatic_diagnosis_loop_artifacts: Artifact writer functions
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .incident_automatic_diagnosis_loop_artifacts import (
    write_final_hypotheses_artifact,
    write_hypothesis_burst_artifact,
    write_pass_artifact,
    write_summary_artifact,
)
from .incident_automatic_diagnosis_loop_state import (
    DiagnosisLoopStopReason,
    HypothesisLoopConfig,
    HypothesisLoopResult,
)
from .incident_diagnosis_pass_executor import (
    StopDecision,
    execute_pass,
    select_checks_for_pass,
)
from .incident_hypothesis_burst import (
    run_hypothesis_burst,
)

_logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


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
    from .incident_automatic_diagnosis_loop_artifacts import _get_automatic_diagnosis_dir

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
