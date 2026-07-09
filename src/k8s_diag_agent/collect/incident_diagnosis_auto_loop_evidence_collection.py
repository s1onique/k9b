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

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
            return result

        candidates = [inc.incident_id for inc in incidents]

    result.incidents_processed = len(candidates)

    if len(candidates) == 0:
        log_zero_incidents_diagnostic(resolved_config)

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
        elif incident_result.eligible:
            result.incidents_eligible += 1
            if incident_result.review_packet_written:
                result.total_review_packets_written += 1
            result.total_checks_run += incident_result.checks_run
        else:
            result.incidents_ineligible += 1

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
