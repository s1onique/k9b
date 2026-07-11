"""Eligibility summary functions for automatic diagnosis loop.

This module contains the shared eligibility-summary functions used by the
automatic diagnosis loop evidence collection.

These functions aggregate incident processing outcomes into structured
summaries for observability and monitoring.

The summary is emitted via ``emit_structured_log`` so it reaches the same
JSON log stream that the health scheduler writes to (see
``k8s_diag_agent.structured_logging``). The previous implementation called
``logging.getLogger().info(extra=...)`` which routed the event to the
standard Python logger only; production scheduler logs did not pick it up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .incident_diagnosis_disposition import DiagnosisDispositionSummary

import logging

from ..structured_logging import emit_structured_log
from .incident_diagnosis_disposition import (
    SCHEMA_VERSION,
    aggregate_summary_event,
)

_logger = logging.getLogger(__name__)

# Re-export the canonical schema version for callers that still expect the
# ``_ELIGIBILITY_VERSION`` symbol.
_ELIGIBILITY_VERSION = SCHEMA_VERSION


def build_eligibility_summary_payload(
    *,
    collector_run_id: str | None = None,
    summary: DiagnosisDispositionSummary | None = None,
    stop_reason: str | None = None,
    run_id: str | None = None,
    schema_version: int = SCHEMA_VERSION,
    result: Any = None,
    eligibility_version: int | None = None,
    incidents_with_errors_override: int | None = None,
) -> dict[str, Any]:
    """Build the aggregate eligibility summary payload.

    New canonical signature accepts a typed ``summary``. Legacy callers
    that pass an ``AutoLoopCollectorResult`` via ``result=`` still work:
    the function will prefer ``result.disposition_summary`` if present
    and otherwise fall back to scanning ``result.incident_results``
    dictionaries (the original pre-ADT behaviour, kept for test
    compatibility).

    Args:
        collector_run_id: Unique identifier for this collector run.
        summary: Typed disposition summary; counters and reason maps are
            projected directly (no rescanning of serialized dicts).
        stop_reason: Why the collector stopped (``loop_completed``,
            ``listing_failed``, etc.).
        run_id: Optional scheduler run ID for correlation.
        schema_version: Schema version for the eligibility summary format.
        result: Legacy ``AutoLoopCollectorResult`` parameter (kept for
            backward compatibility with pre-ADT tests).
        eligibility_version: Legacy ``eligibility_version`` alias for
            callers that still set it explicitly.
    """
    if summary is not None:
        if stop_reason is None:
            stop_reason = "loop_completed"
        if collector_run_id is None:
            collector_run_id = "unknown"
        payload = aggregate_summary_event(
            summary=summary,
            collector_run_id=collector_run_id,
            stop_reason=stop_reason,
            run_id=run_id,
        )
        # Compatibility: pre-ADT ``incidents_with_errors`` summed BOTH
        # evaluation failures (already in ``summary.errors``) AND
        # execution failures on eligible incidents (tracked
        # separately by the batch processor). Let callers inject the
        # combined total here so the aggregate event reports the
        # pre-ADT truth until R2 introduces typed execution counters.
        if incidents_with_errors_override is not None:
            payload["incidents_with_errors"] = incidents_with_errors_override
    elif result is not None:
        cid: str = (
            collector_run_id
            if collector_run_id is not None
            else getattr(result, "run_id", None) or "unknown"
        )
        return _legacy_build_from_result(
            result=result,
            collector_run_id=cid,
            run_id=run_id,
            schema_version=eligibility_version if eligibility_version is not None else schema_version,
        )
    else:
        raise TypeError(
            "build_eligibility_summary_payload requires either summary= or result="
        )

    # Preserve legacy ``eligibility_version`` alias for compatibility with
    # older consumers. ``schema_version`` is the canonical field.
    payload["eligibility_version"] = (
        eligibility_version if eligibility_version is not None else schema_version
    )
    return payload


def _legacy_build_from_result(
    *,
    result: Any,
    collector_run_id: str,
    run_id: str | None,
    schema_version: int,
) -> dict[str, Any]:
    """Legacy ``build_eligibility_summary_payload`` path.

    Re-scans serialized ``incident_results`` dicts to compute reason
    counts. This is the pre-ADT behaviour and is retained only so existing
    tests that build an ``AutoLoopCollectorResult`` and pass it as
    ``result=`` continue to function.
    """
    skip_reason_counts: dict[str, int] = {}
    error_reason_counts: dict[str, int] = {}
    for ir in getattr(result, "incident_results", []) or []:
        if ir.get("skipped"):
            reason = ir.get("eligibility_reason") or ir.get("skip_reason") or "unknown"
            skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1
        if ir.get("error") is not None:
            error = ir.get("error")
            if isinstance(error, str):
                error_type = error.split(":")[0] if ":" in error else error
                error_reason_counts[error_type] = error_reason_counts.get(error_type, 0) + 1

    payload: dict[str, Any] = {
        "event": "automatic-diagnosis-eligibility-summary",
        "collector_run_id": collector_run_id,
        "eligibility_version": schema_version,
        "schema_version": SCHEMA_VERSION,
        "incidents_processed": getattr(result, "incidents_processed", 0),
        "incidents_eligible": getattr(result, "incidents_eligible", 0),
        "incidents_skipped": getattr(result, "incidents_skipped", 0),
        "incidents_ineligible": getattr(result, "incidents_ineligible", 0),
        "incidents_with_errors": getattr(result, "incidents_with_errors", 0),
        "skip_reasons": skip_reason_counts,
        "error_reasons": error_reason_counts,
        "ineligible_reasons": {},
        "stop_reason": "loop_completed",
    }
    if run_id:
        payload["run_id"] = run_id
    return payload


def emit_eligibility_summary(
    *,
    collector_run_id: str,
    summary: DiagnosisDispositionSummary,
    stop_reason: str,
    scheduler_run_id: str | None = None,
    run_label: str = "automatic-diagnosis",
    log_path: Any = None,
    writer: Any = None,
    incidents_with_errors_override: int | None = None,
) -> None:
    """Emit the aggregate eligibility summary event.

    This MUST be called on every collector exit path so operators can always
    see why incidents were skipped, even when the loop exits early. The
    event is emitted via ``emit_structured_log`` so it shares the same
    JSON log destination the scheduler uses.

    Args:
        collector_run_id: Unique identifier for this collector run.
        summary: Typed disposition summary.
        stop_reason: Why the collector stopped.
        scheduler_run_id: Optional scheduler run ID for correlation.
        run_label: Run label forwarded to ``emit_structured_log``.
        log_path: Optional file path for the scheduler log.
        writer: Optional stream writer (used in tests).
    """
    payload = build_eligibility_summary_payload(
        collector_run_id=collector_run_id,
        summary=summary,
        stop_reason=stop_reason,
        run_id=scheduler_run_id,
        incidents_with_errors_override=incidents_with_errors_override,
    )

    # The structured logger is the canonical JSON sink the scheduler reads.
    # We also keep the standard-logger INFO path so existing log shippers
    # that watch ``logging.getLogger()`` still see the event. The standard
    # logger receives the same payload via ``extra=`` so any custom
    # ``Formatter`` (e.g. JSONFormatter) that reads ``record.__dict__``
    # still gets the nested reason maps.
    _logger.info(
        "Automatic diagnosis eligibility summary",
        extra=payload,
    )

    emit_structured_log(
        component="automatic-diagnosis",
        message="Automatic diagnosis eligibility summary",
        run_label=run_label,
        severity="INFO",
        run_id=scheduler_run_id,
        log_path=log_path,
        writer=writer,
        metadata=payload,
    )


__all__ = [
    "build_eligibility_summary_payload",
    "emit_eligibility_summary",
    "_ELIGIBILITY_VERSION",
]
