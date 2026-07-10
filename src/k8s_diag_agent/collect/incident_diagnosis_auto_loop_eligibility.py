"""Eligibility summary functions for automatic diagnosis loop.

This module contains the shared eligibility-summary functions used by the
automatic diagnosis loop evidence collection.

These functions aggregate incident processing outcomes into structured summaries
for observability and monitoring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_diagnosis_auto_loop_models import AutoLoopCollectorResult

import logging

_logger = logging.getLogger(__name__)

# Current eligibility summary schema version
_ELIGIBILITY_VERSION = 1


def build_eligibility_summary_payload(
    *,
    collector_run_id: str,
    result: AutoLoopCollectorResult,
    eligibility_version: int = _ELIGIBILITY_VERSION,
) -> dict[str, Any]:
    """Build the aggregate eligibility summary payload.

    Args:
        collector_run_id: Unique identifier for this collector run
        result: The collector result containing incident processing outcomes
        eligibility_version: Schema version for the eligibility summary format

    Returns:
        Dictionary containing the aggregate eligibility summary with:
        - collector_run_id
        - eligibility_version
        - incidents_processed
        - incidents_eligible
        - incidents_skipped
        - incidents_ineligible
        - incidents_with_errors
        - skip_reasons (aggregate counts, no incident IDs)
        - error_reasons (aggregate counts, no incident IDs)
    """
    # Aggregate skip reasons from incident results
    skip_reason_counts: dict[str, int] = {}
    error_reason_counts: dict[str, int] = {}

    for ir in result.incident_results:
        if ir.get("skipped"):
            # Prefer eligibility_reason over skip_reason
            reason = ir.get("eligibility_reason") or ir.get("skip_reason") or "unknown"
            skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1
        if ir.get("error") is not None:
            error = ir.get("error")
            if isinstance(error, str):
                # Extract the error type/class from the error message
                error_type = error.split(":")[0] if ":" in error else error
                error_reason_counts[error_type] = error_reason_counts.get(error_type, 0) + 1

    return {
        "event": "automatic-diagnosis-eligibility-summary",
        "collector_run_id": collector_run_id,
        "eligibility_version": eligibility_version,
        "incidents_processed": result.incidents_processed,
        "incidents_eligible": result.incidents_eligible,
        "incidents_skipped": result.incidents_skipped,
        "incidents_ineligible": result.incidents_ineligible,
        "incidents_with_errors": result.incidents_with_errors,
        "skip_reasons": skip_reason_counts,
        "error_reasons": error_reason_counts,
    }


def emit_eligibility_summary(
    *,
    collector_run_id: str,
    result: AutoLoopCollectorResult,
    scheduler_run_id: str | None = None,
) -> None:
    """Emit the aggregate eligibility summary log event.

    This must be called on every exit path to ensure operators can always
    see why incidents were skipped, even when the loop exits early.

    Args:
        collector_run_id: Unique identifier for this collector run
        result: The collector result containing incident processing outcomes
        scheduler_run_id: Optional scheduler run ID for correlation
    """
    payload = build_eligibility_summary_payload(
        collector_run_id=collector_run_id,
        result=result,
    )
    if scheduler_run_id:
        payload["run_id"] = scheduler_run_id

    _logger.info(
        "Automatic diagnosis eligibility summary",
        extra=payload,
    )


__all__ = [
    "build_eligibility_summary_payload",
    "emit_eligibility_summary",
    "_ELIGIBILITY_VERSION",
]
