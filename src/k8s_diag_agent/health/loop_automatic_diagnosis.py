"""Automatic diagnosis loop evidence collection integration for health loop.

This module provides integration between the health loop and the automatic
diagnosis evidence collector, enabling opt-in automatic evidence collection
for eligible incidents.

Design constraints:
- Opt-in via K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED=false by default
- Read-only only: no mutation, no remediation, no kubectl
- Bounded: max incidents, passes, and checks per run
- Idempotent: budget tracking prevents repeated passes
- Failure isolation: collector errors do not crash the health loop

The completion event now includes ``skip_reasons`` / ``ineligible_reasons``
/ ``error_reasons`` projected from the typed disposition summary, plus
``eligibility_schema_version``. Operators who already inspect the
"Automatic diagnosis loop completed" event now also see why incidents
were skipped without having to read a separate aggregate event.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    is_automatic_diagnosis_loop_enabled,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "run_automatic_diagnosis_loop",
]


def _projection_from_result(result: Any) -> dict[str, Any]:
    """Project reason maps from a typed ``disposition_summary`` (or fall back).

    Falls back to empty maps when the collector did not produce a typed
    summary (e.g. when invoked through compatibility shims that only
    return scalar counters).
    """
    summary = getattr(result, "disposition_summary", None)
    if summary is None:
        return {
            "skip_reasons": {},
            "ineligible_reasons": {},
            "error_reasons": {},
            "eligibility_schema_version": 2,
        }
    return {
        "skip_reasons": {k.value: v for k, v in summary.skip_reasons.items()},
        "ineligible_reasons": {k.value: v for k, v in summary.ineligible_reasons.items()},
        "error_reasons": {k.value: v for k, v in summary.error_reasons.items()},
        "eligibility_schema_version": 2,
    }


def run_automatic_diagnosis_loop(
    *,
    external_analysis_dir: Path,
    log_event_fn: Any | None = None,
    scheduler_run_id: str | None = None,
) -> dict[str, Any]:
    """Run automatic diagnosis loop evidence collection.

    This is the health loop integration point for automatic evidence collection.
    It is gated by K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED environment variable.
    """
    enabled = is_automatic_diagnosis_loop_enabled()

    if not enabled:
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "INFO",
                "Automatic diagnosis loop is disabled",
                event="disabled",
            )
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
        }

    # Log start of automatic diagnosis phase
    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "INFO",
            "Starting automatic diagnosis loop evidence collection",
            event="start",
        )

    config = AutomaticDiagnosisLoopConfig(
        max_incidents_per_run=10,
        max_passes_per_incident=1,
        max_checks_per_pass=5,
        write_stop_path_packets=True,
        write_ineligible_packets=False,
    )

    from ..collect.incident_diagnosis_auto_loop import run_automatic_diagnosis_loop_evidence_collection

    try:
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=external_analysis_dir,
            config=config,
            scheduler_run_id=scheduler_run_id,
        )

        projection = _projection_from_result(result)
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
        }

        # Log completion with full eligibility summary for operator diagnostics.
        # Operators already inspect this event; we include the reason maps
        # directly so they do not need to cross-reference a separate aggregate.
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
            )

        return summary

    except Exception as exc:
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "WARNING",
                "Automatic diagnosis loop failed with error",
                event="error",
                error=str(type(exc).__name__),
            )

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
            "error_reasons": {
                "eligibility_evaluation_failed": 1,
            },
            "eligibility_schema_version": 2,
        }
