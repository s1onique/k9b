"""Evidence collection functions for automatic diagnosis loop.

This is a leaf module that contains the shared evidence-collection
functions. It MUST NOT import from:
- incident_diagnosis_auto_loop
- incident_diagnosis_auto_loop_entrypoints

Design constraints:
- No LLM calls, no Kubernetes calls, no subprocess/shell/kubectl
- No remediation, no mutation, no execution
- No unbounded loops
- No imports from orchestration siblings

The aggregate eligibility summary event is emitted via
``emit_structured_log`` so it reaches the same JSON log stream the
scheduler uses.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .incident_automatic_diagnosis_loop import run_automatic_diagnosis_hypothesis_loop
from .incident_case_file import build_incident_case_file

# Re-export for backward compatibility with existing tests that patch at this location
from .incident_diagnosis_auto_loop_batch import _process_incident, process_incident_batch
from .incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    check_incident_eligibility,
    is_automatic_diagnosis_loop_enabled,
)
from .incident_diagnosis_auto_loop_cursor_ops import handle_cursor_disposition
from .incident_diagnosis_auto_loop_eligibility import (
    build_eligibility_summary_payload,
)
from .incident_diagnosis_auto_loop_eligibility import (
    emit_eligibility_summary as _emit_eligibility_summary,
)
from .incident_diagnosis_auto_loop_evidence_processor import _write_loop_summary
from .incident_diagnosis_auto_loop_listing import (
    list_incidents_with_pagination,
    load_cursor_for_scan,
)
from .incident_diagnosis_auto_loop_models import (
    _COLLECTOR_SAFETY_METADATA,
    AutoLoopCollectorResult,
    AutoLoopIncidentResult,
)
from .incident_diagnosis_cursor_disposition import decide_cursor_disposition
from .incident_diagnosis_diagnostic import log_zero_incidents_diagnostic
from .incident_diagnosis_dispatch import (
    fetch_incident_for_diagnosis,
)
from .incident_diagnosis_dispatch_page import IncidentDiagnosisPage
from .incident_diagnosis_disposition import (
    SCHEMA_VERSION,
    DiagnosisDispositionSummary,
    empty_disposition_summary,
)
from .incident_diagnosis_loop_runtime_single_pass import run_policy_enforced_loop_pass
from .incident_diagnosis_pagination_types import OpaqueCursorToken
from .incident_diagnosis_review_packet import write_diagnosis_review_packet
from .incident_read_only_check_artifacts import is_safe_run_id
from .incident_store_provider import get_incident_store

_logger = logging.getLogger(__name__)


def _emit_summary_and_artifact(
    *,
    result: AutoLoopCollectorResult,
    summary: DiagnosisDispositionSummary,
    stop_reason: str,
    external_analysis_dir: Path,
    scheduler_run_id: str | None,
    incidents_seen: int,
    total_passes_completed: int,
    total_checks_executed: int,
    hypothesis_bursts_written: int,
    first_incident_run_id: str | None,
    incidents_with_errors: int = 0,
) -> None:
    """Single finalization boundary: emit the summary event and write artifact.

    This replaces the previous pattern of emitting/writing at each return
    site in ``run_automatic_diagnosis_loop_evidence_collection``.
    """
    result.disposition_summary = summary
    _emit_eligibility_summary(
        collector_run_id=result.run_id,
        summary=summary,
        stop_reason=stop_reason,
        scheduler_run_id=scheduler_run_id,
        incidents_with_errors_override=incidents_with_errors,
    )
    _write_loop_summary(
        external_analysis_dir=external_analysis_dir,
        collector_run_id=result.run_id,
        incidents_seen=incidents_seen,
        incidents_eligible=summary.eligible,
        incidents_processed=summary.processed,
        hypothesis_bursts_written=hypothesis_bursts_written,
        total_passes_completed=total_passes_completed,
        total_checks_executed=total_checks_executed,
        stop_reason=stop_reason,
        incident_results=list(result.incident_results),
        run_id=first_incident_run_id,
        skip_reasons={k.value: v for k, v in summary.skip_reasons.items()},
        ineligible_reasons={k.value: v for k, v in summary.ineligible_reasons.items()},
        error_reasons={k.value: v for k, v in summary.error_reasons.items()},
        incidents_skipped=summary.skipped,
        incidents_ineligible=summary.ineligible,
        incidents_with_errors=incidents_with_errors,
        eligibility_schema_version=SCHEMA_VERSION,
    )


def run_automatic_diagnosis_loop_evidence_collection(
    *,
    external_analysis_dir: Path,
    config: AutomaticDiagnosisLoopConfig | None = None,
    incident_ids: list[str] | None = None,
    now: datetime | None = None,
    scheduler_run_id: str | None = None,
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
            "eligibility_schema_version": SCHEMA_VERSION,
        }]
        result.disposition_summary = empty_disposition_summary()
        _emit_summary_and_artifact(
            result=result,
            summary=empty_disposition_summary(),
            stop_reason="loop_disabled",
            external_analysis_dir=external_analysis_dir,
            scheduler_run_id=scheduler_run_id,
            incidents_seen=0,
            total_passes_completed=0,
            total_checks_executed=0,
            hypothesis_bursts_written=0,
            first_incident_run_id=None,
        )
        return result

    # Derive runs_dir from external_analysis_dir
    runs_dir = external_analysis_dir.parent.parent

    # Phase 1: Get candidates - cursor only loaded for automatic discovery
    max_diagnoses = resolved_config.max_incidents_per_run
    page: IncidentDiagnosisPage | None = None
    page_has_more = False
    scan_cursor: OpaqueCursorToken | None = None
    cursor_was_present = False

    if incident_ids is not None:
        scan_bound = max_diagnoses
        all_scanned_ids = incident_ids[:scan_bound]
    else:
        scan_cursor, cursor_was_present = load_cursor_for_scan(runs_dir)
        scan_bound = max_diagnoses * 3
        page_result = list_incidents_with_pagination(scan_cursor, scan_bound)

        from .incident_diagnosis_pagination_results import (
            AutomaticPageCursorRejected,
            AutomaticPageListed,
            AutomaticPageListingFailed,
        )

        match page_result:
            case AutomaticPageListed(page=listed_page):
                page = listed_page
                all_scanned_ids = [inc.incident_id for inc in page.incidents]
                page_has_more = page.has_more
            case AutomaticPageCursorRejected(failure=failure):
                result.incident_results = [{
                    "note": f"Cursor decode error: {failure.error_message}",
                    "eligibility_schema_version": SCHEMA_VERSION,
                }]
                result.disposition_summary = empty_disposition_summary()
                _emit_summary_and_artifact(
                    result=result,
                    summary=empty_disposition_summary(),
                    stop_reason="cursor_error",
                    external_analysis_dir=external_analysis_dir,
                    scheduler_run_id=scheduler_run_id,
                    incidents_seen=0,
                    total_passes_completed=0,
                    total_checks_executed=0,
                    hypothesis_bursts_written=0,
                    first_incident_run_id=None,
                )
                return result
            case AutomaticPageListingFailed(failure=failure):
                result.incident_results = [{
                    "note": f"Failed to list incidents: {failure.message}",
                    "eligibility_schema_version": SCHEMA_VERSION,
                }]
                result.disposition_summary = empty_disposition_summary()
                _emit_summary_and_artifact(
                    result=result,
                    summary=empty_disposition_summary(),
                    stop_reason="incident_listing_failed",
                    external_analysis_dir=external_analysis_dir,
                    scheduler_run_id=scheduler_run_id,
                    incidents_seen=0,
                    total_passes_completed=0,
                    total_checks_executed=0,
                    hypothesis_bursts_written=0,
                    first_incident_run_id=None,
                )
                return result

    if len(all_scanned_ids) == 0:
        if incident_ids is None:
            disposition = decide_cursor_disposition(
                automatic_selection=True,
                examined_rows=0,
                page_rows=0,
                has_more=False,
                last_examined_cursor=None,
                listing_failed=False,
                cursor_was_present=cursor_was_present,
            )
            handle_cursor_disposition(disposition, runs_dir)
        log_zero_incidents_diagnostic(resolved_config)
        result.incident_results = []
        result.disposition_summary = empty_disposition_summary()
        _emit_summary_and_artifact(
            result=result,
            summary=empty_disposition_summary(),
            stop_reason="no_eligible_incidents",
            external_analysis_dir=external_analysis_dir,
            scheduler_run_id=scheduler_run_id,
            incidents_seen=0,
            total_passes_completed=0,
            total_checks_executed=0,
            hypothesis_bursts_written=0,
            first_incident_run_id=None,
        )
        return result

    # Process incident batch
    batch_outcome = process_incident_batch(
        all_scanned_ids=all_scanned_ids,
        page=page,
        scan_bound=scan_bound,
        max_diagnoses=max_diagnoses,
        resolved_config=resolved_config,
        collector_run_id=collector_run_id,
        external_analysis_dir=external_analysis_dir,
        resolved_now=resolved_now,
        scheduler_run_id=scheduler_run_id,
    )

    # Update result from typed batch outcome
    result.incident_results = list(batch_outcome.incident_results)
    result.dispositions = batch_outcome.dispositions
    result.disposition_summary = batch_outcome.disposition_summary
    summary = batch_outcome.disposition_summary
    result.incidents_seen = len(batch_outcome.incident_results)
    result.incidents_processed = summary.processed
    result.incidents_skipped = summary.skipped
    result.incidents_with_errors = batch_outcome.incidents_with_errors
    result.incidents_eligible = summary.eligible
    result.incidents_ineligible = summary.ineligible
    result.total_checks_run = batch_outcome.total_checks_run
    result.total_review_packets_written = batch_outcome.total_review_packets_written
    overall_stop_reason = batch_outcome.stop_reason.value
    first_incident_run_id = batch_outcome.first_incident_run_id
    last_processed_cursor = batch_outcome.last_examined_cursor

    _emit_summary_and_artifact(
        result=result,
        summary=summary,
        stop_reason=overall_stop_reason,
        external_analysis_dir=external_analysis_dir,
        scheduler_run_id=scheduler_run_id,
        incidents_seen=result.incidents_processed,
        total_passes_completed=batch_outcome.total_passes_completed,
        total_checks_executed=batch_outcome.total_checks_executed,
        hypothesis_bursts_written=batch_outcome.hypothesis_bursts_written,
        first_incident_run_id=first_incident_run_id,
        incidents_with_errors=batch_outcome.incidents_with_errors,
    )

    # Cursor disposition using pure state machine
    if incident_ids is None:
        disposition = decide_cursor_disposition(
            automatic_selection=True,
            examined_rows=result.incidents_processed,
            page_rows=len(all_scanned_ids),
            has_more=page_has_more,
            last_examined_cursor=last_processed_cursor,
            listing_failed=False,
            cursor_was_present=cursor_was_present,
        )
        handle_cursor_disposition(disposition, runs_dir)

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
    "build_eligibility_summary_payload",
    "check_incident_eligibility",
    "collect_automatic_diagnosis_evidence",
    "fetch_incident_for_diagnosis",
    "get_incident_store",
    "is_safe_run_id",
    "run_automatic_diagnosis_hypothesis_loop",
    "run_automatic_diagnosis_loop_evidence_collection",
    "run_policy_enforced_loop_pass",
    "write_diagnosis_review_packet",
    # Backward-compatible re-export for test patches
    "_process_incident",
]
