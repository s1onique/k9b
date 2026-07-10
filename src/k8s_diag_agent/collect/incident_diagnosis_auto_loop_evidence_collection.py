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

# Re-export from sibling for test compatibility (patches expect it here)
from .incident_automatic_diagnosis_loop import run_automatic_diagnosis_hypothesis_loop
from .incident_case_file import build_incident_case_file
from .incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    check_incident_eligibility,
    is_automatic_diagnosis_loop_enabled,
)
from .incident_diagnosis_auto_loop_evidence_processor import (
    _process_incident,
    _write_loop_summary,
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
from .incident_diagnosis_loop_runtime import run_policy_enforced_loop_pass
from .incident_diagnosis_review_packet import write_diagnosis_review_packet
from .incident_read_only_check_artifacts import is_safe_run_id
from .incident_store_provider import get_incident_store

_logger = logging.getLogger(__name__)


def run_automatic_diagnosis_loop_evidence_collection(
    *,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig | None = None,
    incident_ids: list[str] | None = None,
    now: datetime | None = None,
) -> AutoLoopCollectorResult:
    """Run automatic diagnosis loop evidence collection for eligible incidents."""
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
        # Restore zero-incident diagnostic
        log_zero_incidents_diagnostic(resolved_config)
        result.incident_results = []
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

    total_passes_completed = 0
    total_checks_executed = 0
    hypothesis_bursts_written = 0
    overall_stop_reason = "loop_completed"
    first_incident_run_id: str | None = None

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
            # Structured logging for skipped incidents - reveals WHY incidents are skipped
            _logger.info(
                "incident_skipped_from_auto_loop",
                extra={
                    "event": "incident-skipped",
                    "incident_id": incident_id,
                    "eligible": False,
                    "eligibility_reason": incident_result.eligibility_reason,
                    "skip_reason": incident_result.skip_reason,
                    "budget_diagnostics": [
                        d.to_dict() for d in (incident_result.budget_diagnostics or [])
                    ],
                },
            )
        elif incident_result.error is not None:
            result.incidents_with_errors += 1
            overall_stop_reason = "incident_error"
        elif incident_result.eligible:
            result.incidents_eligible += 1
            if first_incident_run_id is None and incident_result.run_id:
                first_incident_run_id = incident_result.run_id
            if incident_result.review_packet_written:
                result.total_review_packets_written += 1
            result.total_checks_run += incident_result.checks_run

            if hasattr(incident_result, "hypothesis_loop_result") and incident_result.hypothesis_loop_result:
                loop_result = incident_result.hypothesis_loop_result
                total_passes_completed += loop_result.get("total_passes_completed", 0)
                total_checks_executed += loop_result.get("total_checks_executed", 0)
                if loop_result.get("hypothesis_burst_written"):
                    hypothesis_bursts_written += 1
        else:
            result.incidents_ineligible += 1

    # Aggregate skip reasons for operator diagnostics
    skip_reason_counts: dict[str, int] = {}
    for ir in result.incident_results:
        if ir.get("skipped"):
            reason = ir.get("eligibility_reason") or ir.get("skip_reason") or "unknown"
            skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1

    # Emit aggregate eligibility summary
    _logger.info(
        "automatic_diagnosis_eligibility_summary",
        extra={
            "event": "automatic-diagnosis-eligibility-summary",
            "collector_run_id": collector_run_id,
            "eligibility_version": 1,
            "incidents_processed": result.incidents_processed,
            "incidents_eligible": result.incidents_eligible,
            "incidents_skipped": result.incidents_skipped,
            "incidents_ineligible": result.incidents_ineligible,
            "incidents_with_errors": result.incidents_with_errors,
            "skip_reasons": skip_reason_counts,
        },
    )

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


def collect_automatic_diagnosis_evidence(
    incident_id: str,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig | None = None,
) -> AutoLoopIncidentResult:
    """Collect automatic diagnosis evidence for a single incident.

    Returns AutoLoopIncidentResult for single-incident API compatibility.
    """
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
        # Return the first incident result (single-incident API) - preserve all fields
        first = result.incident_results[0]
        return AutoLoopIncidentResult(**first)

    return AutoLoopIncidentResult(
        incident_id=incident_id,
        eligible=False,
        eligibility_reason="no_incidents_processed",
        skipped=True,
        skip_reason="No incidents were processed",
    )


__all__ = [
    "build_incident_case_file",
    "check_incident_eligibility",
    "collect_automatic_diagnosis_evidence",
    "fetch_incident_for_diagnosis",
    "get_incident_store",
    "is_safe_run_id",
    "run_automatic_diagnosis_hypothesis_loop",
    "run_automatic_diagnosis_loop_evidence_collection",
    "run_policy_enforced_loop_pass",
    "write_diagnosis_review_packet",
]
