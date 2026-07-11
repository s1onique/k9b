"""Batch processing for automatic diagnosis loop.

This module handles incident batch processing logic.
It is a leaf module that MUST NOT import from:
- incident_diagnosis_auto_loop
- incident_diagnosis_auto_loop_entrypoints

The batch processor now derives all counters and reason maps directly from
typed per-incident dispositions via ``reduce_disposition``. It no longer
inspects serialized result dictionaries.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from ..structured_logging import emit_structured_log
from .incident_diagnosis_auto_loop_config import AutomaticDiagnosisLoopConfig
from .incident_diagnosis_auto_loop_evidence_processor import _process_incident
from .incident_diagnosis_auto_loop_models import (
    BatchStopReason,
    IncidentBatchOutcome,
)
from .incident_diagnosis_dispatch_page import IncidentDiagnosisPage
from .incident_diagnosis_disposition import (
    AutomaticDiagnosisEvaluationFailed,
    DiagnosisDispositionSummary,
    IncidentDiagnosisDisposition,
    disposition_from_legacy_result,
    empty_disposition_summary,
    per_incident_disposition_event,
    reduce_disposition,
)
from .incident_diagnosis_keyset_cursor import IncidentDiagnosisCursor, cursor_after_page_incident

_logger = logging.getLogger(__name__)


def _emit_per_incident_disposition(
    *,
    disposition: IncidentDiagnosisDisposition,
    collector_run_id: str,
    incident_id: str,
    scheduler_run_id: str | None,
) -> None:
    """Emit one ``automatic-diagnosis-incident-disposition`` event.

    The event is emitted through ``emit_structured_log`` so it shares the
    same JSON log stream the scheduler uses. The legacy Python-logger path
    is kept as a compatibility fallback for log shippers that watch
    ``logging.getLogger()``.
    """
    payload = per_incident_disposition_event(
        disposition=disposition,
        run_id=scheduler_run_id,
        collector_run_id=collector_run_id,
        incident_id=incident_id,
    )
    _logger.info(
        "Automatic diagnosis incident disposition",
        extra=payload,
    )
    emit_structured_log(
        component="automatic-diagnosis",
        message="Automatic diagnosis incident disposition",
        run_label="automatic-diagnosis",
        severity="INFO",
        run_id=scheduler_run_id,
        metadata=payload,
    )


def process_incident_batch(
    all_scanned_ids: list[str],
    page: IncidentDiagnosisPage | None,
    scan_bound: int,
    max_diagnoses: int,
    resolved_config: AutomaticDiagnosisLoopConfig,
    collector_run_id: str,
    external_analysis_dir: Path,
    resolved_now: datetime,
    scheduler_run_id: str | None = None,
) -> IncidentBatchOutcome:
    """Process a batch of incidents and return aggregated results.

    Returns an ``IncidentBatchOutcome`` containing:

    * ``incident_results``: legacy projection tuple (kept for API compatibility)
    * ``disposition_summary``: typed reduction over per-incident dispositions
    * ``dispositions``: tuple of typed per-incident dispositions
    * scalar counters (kept for backward compatibility)
    * ``stop_reason``
    * ``first_incident_run_id``, ``last_examined_cursor``
    """
    incident_results: list[dict[str, object]] = []
    summary: DiagnosisDispositionSummary = empty_disposition_summary()
    dispositions: list[IncidentDiagnosisDisposition] = []
    # Compatibility accounting: pre-ADT batches incremented
    # incidents_with_errors for ANY legacy result with a non-null error,
    # even when the legacy result also had eligible=True. The new disposition
    # reducer does NOT increment summary.errors for an
    # EligibleForAutomaticDiagnosis carrying an execution error; track
    # those separately so incidents_with_errors stays truthful until the
    # typed-outcome ACT removes this compatibility branch.
    execution_errors = 0
    total_checks_run = 0
    total_review_packets_written = 0
    total_passes_completed = 0
    total_checks_executed = 0
    hypothesis_bursts_written = 0
    stop_reason = BatchStopReason.LOOP_COMPLETED
    first_incident_run_id: str | None = None
    last_processed_cursor: IncidentDiagnosisCursor | None = None

    for i, incident_id in enumerate(all_scanned_ids):
        if page is not None and i < len(page.incidents):
            incident = page.incidents[i]
            last_processed_cursor = cursor_after_page_incident(incident)

        incident_result = _process_incident(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            config=resolved_config,
            collector_run_id=collector_run_id,
            now=resolved_now,
        )

        # Reduce the typed disposition first; counters/derived fields follow.
        disposition = disposition_from_legacy_result(incident_result)
        dispositions.append(disposition)
        summary = reduce_disposition(summary, disposition)
        incident_results.append(incident_result.to_dict())

        # Emit per-incident disposition event exactly once per examined incident.
        _emit_per_incident_disposition(
            disposition=disposition,
            collector_run_id=collector_run_id,
            incident_id=incident_id,
            scheduler_run_id=scheduler_run_id,
        )

        # Downstream-execution bookkeeping: eligible incidents run the loop.
        if incident_result.eligible and not incident_result.skipped:
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

            if summary.eligible >= max_diagnoses:
                stop_reason = BatchStopReason.DIAGNOSIS_BUDGET_EXHAUSTED
                break

        if incident_result.error is not None:
            # Per the ACT contract: do not retroactively classify execution
            # failures as eligibility evaluation errors. The disposition
            # already recorded the evaluation outcome; here we just observe
            # that an error was set and may stop early. If the typed
            # disposition was NOT an evaluation failure, the legacy error
            # was a downstream execution failure that the reducer did not
            # count - tally it here so incidents_with_errors stays
            # truthful for the observability ACT.
            if not isinstance(disposition, AutomaticDiagnosisEvaluationFailed):
                execution_errors += 1
            stop_reason = BatchStopReason.INCIDENT_ERROR
            if summary.eligible >= max_diagnoses or len(incident_results) >= scan_bound:
                break

        if len(incident_results) >= scan_bound:
            stop_reason = BatchStopReason.SCAN_BOUND_REACHED
            break

    return IncidentBatchOutcome(
        incident_results=tuple(incident_results),
        disposition_summary=summary,
        dispositions=tuple(dispositions),
        incidents_skipped=summary.skipped,
        incidents_with_errors=summary.errors + execution_errors,
        incidents_eligible=summary.eligible,
        incidents_ineligible=summary.ineligible,
        total_checks_run=total_checks_run,
        total_review_packets_written=total_review_packets_written,
        total_passes_completed=total_passes_completed,
        total_checks_executed=total_checks_executed,
        hypothesis_bursts_written=hypothesis_bursts_written,
        stop_reason=stop_reason,
        first_incident_run_id=first_incident_run_id,
        last_examined_cursor=last_processed_cursor,
    )
