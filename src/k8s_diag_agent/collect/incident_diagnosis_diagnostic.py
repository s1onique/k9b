"""Diagnostic utilities for automatic diagnosis loop.

This module provides helper functions for debugging and diagnostics.
"""

from __future__ import annotations

import logging

from .incident_diagnosis_auto_loop_config import AutomaticDiagnosisLoopConfig
from .incident_diagnosis_dispatch import _get_dispatch_config, list_incidents_for_diagnosis
from .incident_lifecycle import IncidentStatus
from .incident_store_provider import get_incident_store


def log_zero_incidents_diagnostic(config: AutomaticDiagnosisLoopConfig) -> None:
    """Log diagnostic info when no incidents are found.

    This helps diagnose the incidents_eligible=0 case by providing
    context about what was checked and why nothing was found.

    Args:
        config: The collector configuration
    """
    dispatch_config = _get_dispatch_config()
    resolved_mode = dispatch_config.resolved_mode()

    # Get total incident count for diagnostic
    total_incidents = 0
    incident_statuses: dict[str, int] = {}

    try:
        # Try to get incident counts for diagnostic
        if resolved_mode == "local":
            store = get_incident_store()
            all_incidents = store.list_incidents(status=None)
            total_incidents = len(all_incidents)
            for inc in all_incidents:
                status = inc.status.value
                incident_statuses[status] = incident_statuses.get(status, 0) + 1
        else:
            # Backend API mode - try to get counts
            backend_incidents, success, _ = list_incidents_for_diagnosis(active_only=False, limit=1000)
            if success:
                total_incidents = len(backend_incidents)
                for inc in backend_incidents:  # type: ignore[assignment]
                    inc_status = str(inc.status)
                    incident_statuses[inc_status] = incident_statuses.get(inc_status, 0) + 1
    except Exception:
        pass

    # Log the diagnostic
    _logger_diag = logging.getLogger(__name__)
    _logger_diag.warning(
        "Automatic diagnosis loop found 0 eligible incidents",
        extra={
            "event": "diagnosis-zero-incidents-diagnostic",
            "dispatch_mode": resolved_mode,
            "total_incidents_found": total_incidents,
            "incident_statuses": incident_statuses,
            "active_statuses": [s.value for s in [
                IncidentStatus.OPEN,
                IncidentStatus.COLLECTING_EVIDENCE,
                IncidentStatus.INVESTIGATING,
            ]],
            "max_incidents_per_run": config.max_incidents_per_run,
            "note": "This may indicate backend-api mode but incidents exist in local store, "
                    "or incidents exist but are not in active status (open, collecting_evidence, investigating).",
        },
    )
