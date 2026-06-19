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

This module does NOT:
- Execute real Kubernetes collectors
- Call kubectl/helm/subprocess/shell
- Perform remediation or mutation
- Run unbounded loops
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..collect.incident_diagnosis_auto_loop import run_automatic_diagnosis_loop_evidence_collection
from ..collect.incident_diagnosis_auto_loop_config import (
    AutomaticDiagnosisLoopConfig,
    is_automatic_diagnosis_loop_enabled,
)

if TYPE_CHECKING:
    pass

__all__ = [
    "run_automatic_diagnosis_loop",
]


def run_automatic_diagnosis_loop(
    *,
    external_analysis_dir: Path,
    log_event_fn: Any | None = None,
) -> dict[str, Any]:
    """Run automatic diagnosis loop evidence collection.

    This is the health loop integration point for automatic evidence collection.
    It is gated by K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED environment variable.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        log_event_fn: Optional callback for logging events

    Returns:
        Bounded result summary dict with:
        - automatic_diagnosis_enabled: bool
        - collector_run_id: str | None
        - incidents_processed: int
        - incidents_eligible: int
        - incidents_skipped: int
        - incidents_with_errors: int
        - total_review_packets_written: int

    Safety guarantees:
    - read_only: True
    - no_kubectl: True
    - no_shell: True
    - no_remediation: True
    - bounded: True
    """
    # Check if automatic diagnosis is enabled
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
        }

    # Log start of automatic diagnosis phase
    if log_event_fn:
        log_event_fn(
            "automatic-diagnosis",
            "INFO",
            "Starting automatic diagnosis loop evidence collection",
            event="start",
        )

    # Use safe default config with hard bounds
    config = AutomaticDiagnosisLoopConfig(
        max_incidents_per_run=10,
        max_passes_per_incident=1,
        max_checks_per_pass=5,
        write_stop_path_packets=True,
        write_ineligible_packets=False,
    )

    # Run the collector with bounded error handling
    try:
        result = run_automatic_diagnosis_loop_evidence_collection(
            external_analysis_dir=external_analysis_dir,
            config=config,
        )

        # Extract bounded summary
        summary = {
            "automatic_diagnosis_enabled": True,
            "collector_run_id": result.run_id,
            "incidents_processed": result.incidents_processed,
            "incidents_eligible": result.incidents_eligible,
            "incidents_skipped": result.incidents_skipped,
            "incidents_with_errors": result.incidents_with_errors,
            "total_review_packets_written": result.total_review_packets_written,
        }

        # Log completion
        if log_event_fn:
            log_event_fn(
                "automatic-diagnosis",
                "INFO",
                "Automatic diagnosis loop completed",
                event="complete",
                collector_run_id=result.run_id,
                incidents_processed=result.incidents_processed,
                incidents_eligible=result.incidents_eligible,
                incidents_skipped=result.incidents_skipped,
                incidents_with_errors=result.incidents_with_errors,
                total_review_packets_written=result.total_review_packets_written,
            )

        return summary

    except Exception as exc:
        # Catch any unexpected errors to prevent health loop crash
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
        }
