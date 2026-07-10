"""Batch processing for automatic diagnosis loop.

This module handles incident batch processing logic.
It is a leaf module that MUST NOT import from:
- incident_diagnosis_auto_loop
- incident_diagnosis_auto_loop_entrypoints
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .incident_diagnosis_auto_loop_config import AutomaticDiagnosisLoopConfig
from .incident_diagnosis_auto_loop_evidence_processor import _process_incident
from .incident_diagnosis_auto_loop_models import (
    BatchStopReason,
    IncidentBatchOutcome,
)
from .incident_diagnosis_dispatch_page import IncidentDiagnosisPage
from .incident_diagnosis_keyset_cursor import IncidentDiagnosisCursor, cursor_after_page_incident

_logger = logging.getLogger(__name__)


def process_incident_batch(
    all_scanned_ids: list[str],
    page: IncidentDiagnosisPage | None,
    scan_bound: int,
    max_diagnoses: int,
    resolved_config: AutomaticDiagnosisLoopConfig,
    collector_run_id: str,
    external_analysis_dir: Path,
    resolved_now: datetime,
) -> IncidentBatchOutcome:
    """Process a batch of incidents and return aggregated results.

    Returns an IncidentBatchOutcome containing:
    - incident_results: Tuple of incident result dictionaries
    - incidents_skipped: Number of incidents skipped
    - incidents_with_errors: Number of incidents that errored
    - incidents_eligible: Number of eligible incidents processed
    - incidents_ineligible: Number of ineligible incidents
    - total_checks_run: Total checks run across all incidents
    - total_review_packets_written: Total review packets written
    - total_passes_completed: Total passes completed
    - total_checks_executed: Total checks executed
    - hypothesis_bursts_written: Number of hypothesis bursts written
    - stop_reason: Why batch processing stopped (BatchStopReason enum)
    - first_incident_run_id: Run ID of first eligible incident
    - last_examined_cursor: Cursor after last examined incident
    """
    incident_results: list[dict[str, object]] = []
    incidents_skipped = 0
    incidents_with_errors = 0
    incidents_eligible = 0
    incidents_ineligible = 0
    total_checks_run = 0
    total_review_packets_written = 0
    total_passes_completed = 0
    total_checks_executed = 0
    hypothesis_bursts_written = 0
    stop_reason = "loop_completed"
    first_incident_run_id: str | None = None
    last_processed_cursor: IncidentDiagnosisCursor | None = None

    for i, incident_id in enumerate(all_scanned_ids):
        if page is not None and i < len(page.incidents):
            incident = page.incidents[i]
            # Use cursor_after_page_incident for exact cursor construction
            last_processed_cursor = cursor_after_page_incident(incident)

        incident_result = _process_incident(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            config=resolved_config,
            collector_run_id=collector_run_id,
            now=resolved_now,
        )
        incident_results.append(incident_result.to_dict())

        if incident_result.skipped:
            incidents_skipped += 1
            _logger.info(
                "incident_skipped_from_auto_loop",
                extra={
                    "event": "incident-skipped",
                    "collector_run_id": collector_run_id,
                    "incident_id": incident_id,
                    "eligible": False,
                    "eligibility_reason": incident_result.eligibility_reason,
                    "skip_reason": incident_result.skip_reason,
                    "budget_diagnostics": [
                        d.to_dict() for d in (incident_result.budget_diagnostics or [])
                    ],
                },
            )
            if len(incident_results) >= scan_bound:
                stop_reason = "scan_bound_reached"
                break
            continue
        elif incident_result.error is not None:
            incidents_with_errors += 1
            stop_reason = "incident_error"
            eligible_count = incidents_eligible
            if eligible_count >= max_diagnoses or len(incident_results) >= scan_bound:
                break
            continue
        elif incident_result.eligible:
            incidents_eligible += 1
            if first_incident_run_id is None and incident_result.run_id:
                first_incident_run_id = incident_result.run_id
            if incident_result.review_packet_written:
                total_review_packets_written += 1
            total_checks_run += incident_result.checks_run

            if hasattr(incident_result, "hypothesis_loop_result") and incident_result.hypothesis_loop_result:
                loop_result = incident_result.hypothesis_loop_result
                total_passes_completed += loop_result.get("total_passes_completed", 0)
                total_checks_executed += loop_result.get("total_checks_executed", 0)
                if loop_result.get("hypothesis_burst_written"):
                    hypothesis_bursts_written += 1

            if incidents_eligible >= max_diagnoses:
                stop_reason = "diagnosis_budget_exhausted"
                break
        else:
            incidents_ineligible += 1

        if len(incident_results) >= scan_bound:
            stop_reason = "scan_bound_reached"
            break

    return IncidentBatchOutcome(
        incident_results=tuple(incident_results),
        incidents_skipped=incidents_skipped,
        incidents_with_errors=incidents_with_errors,
        incidents_eligible=incidents_eligible,
        incidents_ineligible=incidents_ineligible,
        total_checks_run=total_checks_run,
        total_review_packets_written=total_review_packets_written,
        total_passes_completed=total_passes_completed,
        total_checks_executed=total_checks_executed,
        hypothesis_bursts_written=hypothesis_bursts_written,
        stop_reason=BatchStopReason(stop_reason),
        first_incident_run_id=first_incident_run_id,
        last_examined_cursor=last_processed_cursor,
    )
