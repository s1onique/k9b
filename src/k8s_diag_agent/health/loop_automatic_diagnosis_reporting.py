"""Reporting projections and structured events for the automatic diagnosis loop.

This module contains no diagnosis dispatch, incident mutation, or remediation.
It only projects typed selections and collector results into the established
bounded summaries and emits the existing structured event payloads.
"""

from __future__ import annotations

from typing import Any

from ..collect.diagnosis_selection import (
    DiagnosisSelection,
    DiagnosisSelectionFromPromotion,
    DiagnosisSelectionUnavailable,
)
from ..collect.diagnosis_selection import selection_source as _selection_source
from ..collect.diagnosis_selection import (
    store_scan_performed as _store_scan_performed,
)
from ..collect.promotion_outcomes import (
    PromotionCommitUnknown,
    PromotionRejected,
)
from ..collect.promotion_outcomes import (
    consistency_error_recorded as _consistency_error_recorded,
)


def projection_from_result(result: Any) -> dict[str, Any]:
    """Project typed collector reason maps into the bounded wire shape."""
    summary = getattr(result, "disposition_summary", None)
    if summary is None:
        return {
            "skip_reasons": {},
            "ineligible_reasons": {},
            "error_reasons": {},
            "eligibility_schema_version": 2,
        }
    return {
        "skip_reasons": {key.value: value for key, value in summary.skip_reasons.items()},
        "ineligible_reasons": {
            key.value: value for key, value in summary.ineligible_reasons.items()
        },
        "error_reasons": {
            key.value: value for key, value in summary.error_reasons.items()
        },
        "eligibility_schema_version": 2,
    }


def _legacy_selection_mode(selection: DiagnosisSelection) -> str:
    """Map a typed selection to the established legacy mode field."""
    if isinstance(selection, DiagnosisSelectionFromPromotion):
        if selection.incident_ids:
            return "explicit_incident_ids"
        return "current_run_empty"
    if isinstance(selection, DiagnosisSelectionUnavailable):
        if isinstance(selection.outcome, PromotionCommitUnknown):
            return "commit_unknown"
        return "blocked"
    return "store_scan"


def selection_projection(
    selection: DiagnosisSelection,
    *,
    access_mode: str,
) -> dict[str, Any]:
    """Project selection provenance and compatibility booleans."""
    explicit_count = 0
    selected_incident_count = 0
    if isinstance(selection, DiagnosisSelectionFromPromotion):
        explicit_count = len(selection.incident_ids)
        selected_incident_count = len(selection.incident_ids)
    reconciliation_required = (
        isinstance(selection, DiagnosisSelectionUnavailable)
        and isinstance(selection.outcome, PromotionCommitUnknown)
    )
    propagated = (
        isinstance(selection, DiagnosisSelectionFromPromotion)
        and bool(selection.incident_ids)
    )
    if isinstance(selection, DiagnosisSelectionFromPromotion):
        consistency_error = False
    elif isinstance(selection, DiagnosisSelectionUnavailable):
        consistency_error = _consistency_error_recorded(selection.outcome)
    else:
        consistency_error = False
    return {
        "selection_source": _selection_source(selection).value,
        "selection_mode": _legacy_selection_mode(selection),
        "explicit_canonical_id_count": explicit_count,
        "selected_incident_count": selected_incident_count,
        "store_scan_performed": _store_scan_performed(selection),
        "reconciliation_required": reconciliation_required,
        "promotion_propagated_to_diagnosis": propagated,
        "promotion_consistency_error_recorded": consistency_error,
        "incident_access_mode": access_mode,
    }


def resolve_access_mode(
    *,
    backend_endpoint_identity: dict[str, Any] | None,
    promotion_result_summary: dict[str, Any] | None,
) -> str:
    """Project the access mode from endpoint metadata or promotion summary."""
    access_mode = "no_promotion_run"
    if isinstance(backend_endpoint_identity, dict):
        candidate_mode = backend_endpoint_identity.get("incident_access_mode")
        if isinstance(candidate_mode, str) and candidate_mode:
            access_mode = candidate_mode
    if access_mode == "no_promotion_run" and isinstance(
        promotion_result_summary, dict
    ):
        candidate_mode = promotion_result_summary.get("incident_access_mode")
        if isinstance(candidate_mode, str) and candidate_mode:
            access_mode = candidate_mode
    return access_mode


def blocked_reason(selection: DiagnosisSelection) -> str | None:
    """Return the bounded reason for an unavailable selection."""
    if not isinstance(selection, DiagnosisSelectionUnavailable):
        return None
    if isinstance(selection.outcome, PromotionCommitUnknown):
        return "promotion_commit_unknown"
    if isinstance(selection.outcome, PromotionRejected):
        return "promotion_rejected"
    return "promotion_unavailable"


def build_selection_unavailable_summary(
    *,
    projection: dict[str, Any],
    promotion_result_summary: dict[str, Any] | None,
    backend_endpoint_identity: dict[str, Any] | None,
    selection: DiagnosisSelection,
) -> dict[str, Any]:
    """Build the unchanged terminal result for blocked diagnosis selection."""
    return {
        "automatic_diagnosis_enabled": True,
        "collector_run_id": None,
        "incidents_processed": 0,
        "incidents_eligible": 0,
        "incidents_skipped": 0,
        "incidents_with_errors": 0,
        "total_review_packets_written": 0,
        "skip_reasons": {},
        "ineligible_reasons": {},
        "error_reasons": {},
        "eligibility_schema_version": 2,
        **projection,
        "promotion_summary_propagated": (
            dict(promotion_result_summary) if promotion_result_summary else {}
        ),
        "backend_endpoint_identity": backend_endpoint_identity,
        "blocked_reason": blocked_reason(selection),
    }


def build_disabled_summary(projection: dict[str, Any]) -> dict[str, Any]:
    """Build the unchanged terminal result for a disabled diagnosis loop."""
    return {
        "automatic_diagnosis_enabled": False,
        "collector_run_id": None,
        "incidents_processed": 0,
        "incidents_eligible": 0,
        "incidents_skipped": 0,
        "incidents_with_errors": 0,
        "total_review_packets_written": 0,
        "skip_reasons": {},
        "ineligible_reasons": {},
        "error_reasons": {},
        "eligibility_schema_version": 2,
        **projection,
    }


def build_no_trigger_summary(projection: dict[str, Any]) -> dict[str, Any]:
    """Build the result for an enabled loop with no trigger/authority.
    
    This is the "no trigger" path where the integration is enabled but no
    promotion outcome or explicit authority was provided. The loop returns
    enabled=True with 0 incidents processed.
    """
    return {
        "automatic_diagnosis_enabled": True,
        "collector_run_id": None,
        "incidents_processed": 0,
        "incidents_eligible": 0,
        "incidents_skipped": 0,
        "incidents_with_errors": 0,
        "total_review_packets_written": 0,
        "skip_reasons": {},
        "ineligible_reasons": {},
        "error_reasons": {},
        "eligibility_schema_version": 2,
        **projection,
    }


def build_completed_summary(
    *,
    result: Any,
    scheduler_run_id: str | None,
    projection: dict[str, Any],
    backend_endpoint_identity: dict[str, Any] | None,
    promotion_summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the completed result and its reason-map projection."""
    reason_projection = projection_from_result(result)
    summary = {
        "automatic_diagnosis_enabled": True,
        "collector_run_id": result.run_id,
        "run_id": scheduler_run_id,
        "incidents_processed": result.incidents_processed,
        "incidents_eligible": result.incidents_eligible,
        "incidents_skipped": result.incidents_skipped,
        "incidents_ineligible": result.incidents_ineligible,
        "incidents_with_errors": result.incidents_with_errors,
        "total_review_packets_written": result.total_review_packets_written,
        **projection,
        "backend_endpoint_identity": backend_endpoint_identity,
        "promotion_summary_propagated": promotion_summary,
        **reason_projection,
    }
    return summary, reason_projection


def build_error_summary(
    *,
    projection: dict[str, Any],
    backend_endpoint_identity: dict[str, Any] | None,
    promotion_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build the unchanged bounded terminal result for collector errors."""
    return {
        "automatic_diagnosis_enabled": True,
        "collector_run_id": None,
        "incidents_processed": 0,
        "incidents_eligible": 0,
        "incidents_skipped": 0,
        "incidents_with_errors": 1,
        "total_review_packets_written": 0,
        "skip_reasons": {},
        "ineligible_reasons": {},
        "error_reasons": {"eligibility_evaluation_failed": 1},
        "eligibility_schema_version": 2,
        **projection,
        "backend_endpoint_identity": backend_endpoint_identity,
        "promotion_summary_propagated": promotion_summary,
    }


def emit_selection_unavailable(
    log_event_fn: Any | None,
    *,
    projection: dict[str, Any],
    access_mode: str,
) -> None:
    """Emit the established unavailable-selection event, when configured."""
    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "INFO",
            "Automatic diagnosis selection unavailable",
            event="automatic_diagnosis_selection_unavailable",
            selection_source=projection["selection_source"],
            selection_mode=projection["selection_mode"],
            reconciliation_required=projection["reconciliation_required"],
            promotion_consistency_error_recorded=projection[
                "promotion_consistency_error_recorded"
            ],
            incident_access_mode=access_mode,
        )


def emit_disabled(log_event_fn: Any | None, projection: dict[str, Any]) -> None:
    """Emit the established disabled event, when configured."""
    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "INFO",
            "Automatic diagnosis loop is disabled",
            event="disabled",
            **projection,
        )


def emit_start(log_event_fn: Any | None, projection: dict[str, Any]) -> None:
    """Emit the established start event, when configured."""
    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "INFO",
            "Starting automatic diagnosis loop evidence collection",
            event="start",
            **projection,
        )


def emit_complete(
    log_event_fn: Any | None,
    *,
    result: Any,
    scheduler_run_id: str | None,
    projection: dict[str, Any],
    reason_projection: dict[str, Any],
) -> None:
    """Emit the established completion event, when configured."""
    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "INFO",
            "Automatic diagnosis loop completed",
            event="complete",
            collector_run_id=result.run_id,
            run_id=scheduler_run_id,
            incidents_processed=result.incidents_processed,
            incidents_eligible=result.incidents_eligible,
            incidents_skipped=result.incidents_skipped,
            incidents_ineligible=result.incidents_ineligible,
            incidents_with_errors=result.incidents_with_errors,
            total_review_packets_written=result.total_review_packets_written,
            **projection,
            **reason_projection,
        )


def emit_error(
    log_event_fn: Any | None,
    *,
    projection: dict[str, Any],
    exc: Exception,
) -> None:
    """Emit the bounded error event without swallowing extra failures."""
    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "WARNING",
            "Automatic diagnosis loop failed with error",
            event="error",
            error=str(type(exc).__name__),
            **projection,
        )
