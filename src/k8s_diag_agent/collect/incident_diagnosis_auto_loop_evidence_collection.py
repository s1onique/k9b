"""Evidence collection functions for automatic diagnosis loop.

This is a leaf module that contains the shared evidence-collection
functions. It MUST NOT import from:
- incident_diagnosis_auto_loop
- incident_diagnosis_auto_loop_entrypoints

This module may import from models, config, store, case file, etc.,
but not from either orchestration sibling.

Design constraints:
- No LLM calls, no Kubernetes calls, no subprocess/shell/kubectl
- No remediation, no mutation, no execution
- No unbounded loops
- No imports from orchestration siblings
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .incident_automatic_diagnosis_loop import (
    write_summary_artifact,
)
from .incident_case_file import build_incident_case_file
from .incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    check_incident_eligibility,
    is_automatic_diagnosis_loop_enabled,
)
from .incident_diagnosis_auto_loop_models import (
    _COLLECTOR_SAFETY_METADATA,
    AutoLoopCollectorResult,
    AutoLoopIncidentResult,
)
from .incident_diagnosis_diagnostic import log_zero_incidents_diagnostic
from .incident_diagnosis_dispatch import (
    fetch_incident_for_diagnosis,
    list_incidents_for_diagnosis,
)
from .incident_diagnosis_loop_models import LoopDecision
from .incident_diagnosis_loop_runtime import run_policy_enforced_loop_pass
from .incident_diagnosis_review_packet import (
    write_diagnosis_review_packet,
)
from .incident_read_only_check_artifacts import is_safe_run_id
from .incident_store import IncidentStore
from .incident_store_provider import get_incident_store

__all__ = [
    "collect_automatic_diagnosis_evidence",
    "run_automatic_diagnosis_loop_evidence_collection",
]

_logger = logging.getLogger(__name__)


def run_automatic_diagnosis_loop_evidence_collection(
    *,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig | None = None,
    incident_ids: list[str] | None = None,
    now: datetime | None = None,
) -> AutoLoopCollectorResult:
    """Run automatic diagnosis loop evidence collection for eligible incidents.

    This is the main entry point for automatic evidence collection.
    """
    resolved_config = config or AutomaticDiagnosisLoopConfig()
    resolved_now = now if now is not None else datetime.now(UTC)
    collector_run_id = f"auto-diagnosis-{resolved_now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    enabled = is_automatic_diagnosis_loop_enabled()

    result = AutoLoopCollectorResult(
        run_id=collector_run_id,
        generated_at=resolved_now.isoformat(),
        enabled=enabled,
        config=resolved_config.to_dict(),
        safety_metadata=dict(_COLLECTOR_SAFETY_METADATA),
    )

    if not enabled:
        result.incident_results = [{
            "note": "Automatic diagnosis loop is disabled. Set K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=true to enable.",
        }]
        # Write summary artifact even when disabled
        _write_loop_summary(
            external_analysis_dir=external_analysis_dir,
            collector_run_id=collector_run_id,
            incidents_seen=0,
            incidents_eligible=0,
            incidents_processed=0,
            hypothesis_bursts_written=0,
            total_passes_completed=0,
            total_checks_executed=0,
            stop_reason="loop_disabled",
            incident_results=result.incident_results,
        )
        return result

    if incident_ids is not None:
        candidates = incident_ids[:resolved_config.max_incidents_per_run]
    else:
        incidents, success, error = list_incidents_for_diagnosis(
            active_only=True,
            limit=resolved_config.max_incidents_per_run,
        )

        if not success:
            result.incident_results = [{
                "note": f"Failed to list incidents: {error}",
            }]
            # Write failure summary
            _write_loop_summary(
                external_analysis_dir=external_analysis_dir,
                collector_run_id=collector_run_id,
                incidents_seen=0,
                incidents_eligible=0,
                incidents_processed=0,
                hypothesis_bursts_written=0,
                total_passes_completed=0,
                total_checks_executed=0,
                stop_reason="incident_listing_failed",
                incident_results=result.incident_results,
            )
            return result

        candidates = [inc.incident_id for inc in incidents]

    result.incidents_processed = len(candidates)
    result.incidents_seen = len(candidates)

    if len(candidates) == 0:
        log_zero_incidents_diagnostic(resolved_config)
        _write_loop_summary(
            external_analysis_dir=external_analysis_dir,
            collector_run_id=collector_run_id,
            incidents_seen=len(candidates),
            incidents_eligible=0,
            incidents_processed=0,
            hypothesis_bursts_written=0,
            total_passes_completed=0,
            total_checks_executed=0,
            stop_reason="no_eligible_incidents",
            incident_results=result.incident_results,
        )
        return result

    # Track hypothesis loop metrics
    total_passes_completed = 0
    total_checks_executed = 0
    hypothesis_bursts_written = 0
    overall_stop_reason = "loop_completed"
    first_incident_run_id: str | None = None  # R3: Track first incident's run_id for summary

    for incident_id in candidates:
        incident_result = _process_incident(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            config=resolved_config,
            collector_run_id=collector_run_id,
            now=resolved_now,
        )
        result.incident_results.append(incident_result.to_dict())

        if incident_result.skipped:
            result.incidents_skipped += 1
        elif incident_result.error is not None:
            result.incidents_with_errors += 1
            overall_stop_reason = "incident_error"
        elif incident_result.eligible:
            result.incidents_eligible += 1
            # R3: Capture first incident's run_id for summary artifact identity
            if first_incident_run_id is None and incident_result.run_id:
                first_incident_run_id = incident_result.run_id
            if incident_result.review_packet_written:
                result.total_review_packets_written += 1
            result.total_checks_run += incident_result.checks_run

            # Aggregate hypothesis loop metrics from the incident result
            if hasattr(incident_result, "hypothesis_loop_result") and incident_result.hypothesis_loop_result:
                loop_result = incident_result.hypothesis_loop_result
                total_passes_completed += loop_result.get("total_passes_completed", 0)
                total_checks_executed += loop_result.get("total_checks_executed", 0)
                if loop_result.get("hypothesis_burst_written"):
                    hypothesis_bursts_written += 1
        else:
            result.incidents_ineligible += 1

    # Write summary artifact for every loop run (R3: use first incident's real run_id)
    _write_loop_summary(
        external_analysis_dir=external_analysis_dir,
        collector_run_id=collector_run_id,
        incidents_seen=len(candidates),
        incidents_eligible=result.incidents_eligible,
        incidents_processed=result.incidents_processed,
        hypothesis_bursts_written=hypothesis_bursts_written,
        total_passes_completed=total_passes_completed,
        total_checks_executed=total_checks_executed,
        stop_reason=overall_stop_reason,
        incident_results=result.incident_results,
        run_id=first_incident_run_id,
    )

    return result


def _process_incident(
    incident_id: str,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig,
    collector_run_id: str,
    now: datetime,
) -> AutoLoopIncidentResult:
    """Process a single incident in the automatic diagnosis loop."""
    incident, fetch_success, fetch_error = fetch_incident_for_diagnosis(incident_id)

    if not fetch_success:
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=False,
            eligibility_reason=f"fetch_failed: {fetch_error}",
            skipped=True,
            skip_reason=f"fetch_failed: {fetch_error}",
        )

    if incident is None:
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=False,
            eligibility_reason="not_found",
            skipped=True,
            skip_reason="incident_not_found",
        )

    store: IncidentStore = get_incident_store()

    eligibility = check_incident_eligibility(
        incident_id=incident_id,
        config=config,
        external_analysis_dir=external_analysis_dir,
    )

    if not eligibility.eligible:
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=False,
            eligibility_reason=eligibility.reason,
            skipped=True,
            skip_reason=f"not_eligible: {eligibility.reason}",
            budget_diagnostics=eligibility.budget_diagnostics,
        )

    run_id = f"auto-{incident_id}-{now.strftime('%Y%m%d%H%M%S')}"

    if not is_safe_run_id(run_id):
        store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="unsafe_run_id",
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error=f"Unsafe run_id generated: {run_id}",
        )

    store.mark_diagnosis_loop_started(
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
    )

    try:
        case_file = build_incident_case_file(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            incident=incident,
        )
    except (OSError, ValueError, KeyError):
        store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="case_file_error",
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error="Failed to build case file",
        )

    if case_file is None:
        store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="case_file_none",
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error="Case file is None",
        )

    # R3: Run hypothesis burst multipass loop
    # This is the core production path for automatic diagnosis
    hypothesis_loop_result: dict[str, Any] | None = None
    try:
        from .incident_automatic_diagnosis_loop import HypothesisLoopConfig, run_automatic_diagnosis_hypothesis_loop

        # Build hypothesis loop config from collector config
        loop_config = HypothesisLoopConfig(
            max_passes_per_incident=min(config.max_passes_per_incident, 2),  # Cap at 2 passes
            max_checks_per_pass=config.max_checks_per_pass,
            max_total_checks=config.max_checks_per_pass * 2,
            max_seconds_per_incident=config.max_seconds_per_incident,
            min_confidence_to_stop=0.78,
        )

        # Run the hypothesis burst loop
        # Ensure incident is always a dict for run_automatic_diagnosis_hypothesis_loop
        incident_dict: dict[str, Any] = incident.to_dict() if hasattr(incident, "to_dict") else incident  # type: ignore[assignment]
        loop_result = run_automatic_diagnosis_hypothesis_loop(
            incident=incident_dict,
            case_file=case_file,
            external_analysis_dir=external_analysis_dir,
            run_id=run_id,  # R3: Real health run_id preserved
            collector_run_id=collector_run_id,
            config=loop_config,
            now=now,
        )
        hypothesis_loop_result = loop_result.to_dict()

    except Exception as e:
        # Hypothesis loop failure is non-fatal - continue with policy-enforced path
        _logger.warning(
            "Hypothesis loop failed, continuing with policy-enforced path",
            extra={
                "event": "hypothesis-loop-failed",
                "incident_id": incident_id,
                "run_id": run_id,
                "error": str(e),
            },
        )

    diagnosis_report = _build_minimal_diagnosis_report(case_file, config.max_checks_per_pass)

    try:
        orchestrator_result = run_policy_enforced_loop_pass(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            case_file=case_file,
            diagnosis_report=diagnosis_report,
            run_id=run_id,
            now=now,
        )
    except (ValueError, RuntimeError, KeyError):
        store.mark_diagnosis_loop_failed(
            incident_id=incident_id,
            run_id=run_id,
            collector_run_id=collector_run_id,
            unavailable_reason="orchestrator_error",
        )
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=True,
            eligibility_reason=eligibility.reason,
            run_id=run_id,
            error="Orchestrator error",
        )

    decision = str(orchestrator_result.get("decision", ""))
    runner_result = orchestrator_result.get("runner_result")
    artifact = orchestrator_result.get("artifact")
    loop_pass_artifact = orchestrator_result.get("loop_pass_artifact")

    checks_requested = 0
    checks_run = 0
    checks_skipped = 0
    checks_rejected = 0

    if runner_result and isinstance(runner_result, dict):
        checks_requested = runner_result.get("checks_requested", 0)
        checks_run = runner_result.get("checks_run", 0)
        checks_skipped = runner_result.get("checks_skipped", 0)
        checks_rejected = runner_result.get("checks_rejected", 0)

    is_stop_path = decision in (
        LoopDecision.STOP_ROOT_CAUSE_FOUND.value,
        LoopDecision.STOP_NO_SAFE_CHECKS.value,
        LoopDecision.STOP_NO_CHECKS_PROPOSED.value,
        LoopDecision.STOP_BUDGET_EXHAUSTED.value,
    )

    review_packet_written = False
    review_packet_name = None

    should_write_packet = not is_stop_path or config.write_stop_path_packets

    if should_write_packet:
        try:
            review_packet_meta = write_diagnosis_review_packet(
                external_analysis_dir=external_analysis_dir,
                incident_id=incident_id,
                collector_run_id=collector_run_id,
                run_id=run_id,
                decision=decision,
                checks_requested=checks_requested,
                checks_run=checks_run,
                checks_skipped=checks_skipped,
                checks_rejected=checks_rejected,
                eligible=True,
                eligibility_reason=eligibility.reason,
                config=config,
                now=now,
                case_file=case_file,
                orchestrator_result=orchestrator_result,
            )
            if review_packet_meta.get("written"):
                review_packet_written = True
                review_packet_name = str(review_packet_meta.get("name")) if review_packet_meta.get("name") else None
        except (OSError, ValueError):
            pass

    store.mark_diagnosis_loop_completed(
        incident_id=incident_id,
        run_id=run_id,
        collector_run_id=collector_run_id,
        review_packet_name=review_packet_name,
        checks_requested=checks_requested,
        checks_run=checks_run,
        checks_rejected=checks_rejected,
        decision=decision if decision else None,
    )

    read_only_check_artifact_written = (
        artifact is not None
        and isinstance(artifact, dict)
        and artifact.get("written", False)
    )
    loop_pass_artifact_written = (
        loop_pass_artifact is not None
        and isinstance(loop_pass_artifact, dict)
        and loop_pass_artifact.get("written", False)
    )

    return AutoLoopIncidentResult(
        incident_id=incident_id,
        eligible=True,
        eligibility_reason=eligibility.reason,
        run_id=run_id,
        decision=decision,
        checks_requested=checks_requested,
        checks_run=checks_run,
        checks_skipped=checks_skipped,
        checks_rejected=checks_rejected,
        review_packet_written=review_packet_written,
        review_packet_name=review_packet_name,
        read_only_check_artifact_written=read_only_check_artifact_written,
        loop_pass_artifact_written=loop_pass_artifact_written,
        hypothesis_loop_result=hypothesis_loop_result,
    )


def _build_minimal_diagnosis_report(
    case_file: dict[str, Any],
    max_checks: int,
) -> dict[str, Any]:
    """Build a minimal diagnosis report from case file suggested checks."""
    suggested_checks = case_file.get("suggested_checks", [])
    if not isinstance(suggested_checks, list):
        suggested_checks = []

    recommended_investigations = []
    for check in suggested_checks[:max_checks]:
        if not isinstance(check, dict):
            continue

        check_id = check.get("check_id") or check.get("id")
        title = check.get("title") or check.get("name") or check_id

        if check_id:
            recommended_investigations.append({
                "check_id": check_id,
                "title": str(title),
                "read_only": True,
                "source": "automatic_suggested_check",
            })

    return {
        "diagnosis": {
            "recommended_investigations": recommended_investigations,
        },
        "metadata": {
            "source": "automatic_diagnosis_loop",
            "case_file_generated_at": case_file.get("generated_at"),
        },
    }


def _write_loop_summary(
    external_analysis_dir: Path,
    collector_run_id: str,
    incidents_seen: int,
    incidents_eligible: int,
    incidents_processed: int,
    hypothesis_bursts_written: int,
    total_passes_completed: int,
    total_checks_executed: int,
    stop_reason: str,
    incident_results: list[dict[str, Any]],
    run_id: str | None = None,
) -> dict[str, Any]:
    """Write loop summary artifact.

    The summary artifact is written for every loop run including failure cases.
    Uses the first incident's real health run_id for identity when available.
    """

    artifact_dir = external_analysis_dir / "automatic-diagnosis"

    # Use real health run_id when available, fallback to collector-based run_id
    effective_run_id = run_id if run_id else f"collector-{collector_run_id}"

    return write_summary_artifact(
        artifact_dir=artifact_dir,
        run_id=effective_run_id,
        collector_run_id=collector_run_id,
        incidents_seen=incidents_seen,
        incidents_eligible=incidents_eligible,
        incidents_processed=incidents_processed,
        hypothesis_bursts_written=hypothesis_bursts_written,
        total_passes_completed=total_passes_completed,
        total_checks_executed=total_checks_executed,
        stop_reason=stop_reason,
        incident_results=incident_results,
    )


def collect_automatic_diagnosis_evidence(
    incident_id: str,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig | None = None,
) -> AutoLoopIncidentResult:
    """Collect automatic diagnosis evidence for a single incident."""
    if not is_automatic_diagnosis_loop_enabled():
        return AutoLoopIncidentResult(
            incident_id=incident_id,
            eligible=False,
            eligibility_reason="automatic_collector_disabled",
            skipped=True,
            skip_reason="K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED is not set to true",
        )

    result = run_automatic_diagnosis_loop_evidence_collection(
        external_analysis_dir=external_analysis_dir,
        config=config,
        incident_ids=[incident_id],
    )

    if result.incident_results:
        return AutoLoopIncidentResult(
            **result.incident_results[0]
        )

    return AutoLoopIncidentResult(
        incident_id=incident_id,
        eligible=False,
        eligibility_reason="no_incidents_processed",
        skipped=True,
        skip_reason="No incidents were processed",
    )
