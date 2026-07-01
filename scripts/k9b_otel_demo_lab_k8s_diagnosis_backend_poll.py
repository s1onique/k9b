"""Backend polling helpers for P4c K8s diagnosis phase.

This module provides polling helpers for backend-targeted diagnosis:
1. poll_backend_diagnosis_state: Poll backend for diagnosis completion

Architecture:
- Uses kubectl exec against deploy/k9b-backend -c backend for backend-local HTTP
- Does NOT rely on scheduler periodic automatic diagnosis loop
"""

from __future__ import annotations

import time
from collections.abc import Callable

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
    TargetedDiagnosisPollResult,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
    fetch_backend_incident_detail,
)
from scripts.lab_common.constants import DEFAULT_K9B_BACKEND_PORT


def poll_backend_diagnosis_state(
    kubeconfig: str,
    namespace: str,
    incident_id: str,
    max_attempts: int = 12,
    poll_interval_seconds: float = 5.0,
    backend_port: int = DEFAULT_K9B_BACKEND_PORT,
    log_callback: Callable[[str], None] | None = None,
) -> TargetedDiagnosisPollResult:
    """Poll backend incident detail until diagnosis completes.

    Args:
        kubeconfig: Path to kubeconfig
        namespace: k9b namespace
        incident_id: Incident ID to poll
        max_attempts: Maximum poll attempts (default: 12 * 5s = 60s)
        poll_interval_seconds: Interval between polls (default: 5s)
        backend_port: Backend port (default: 8080)
        log_callback: Optional callback for logging each poll attempt

    Returns:
        TargetedDiagnosisPollResult with final state
    """
    for attempt in range(1, max_attempts + 1):
        # Fetch current incident detail
        detail = fetch_backend_incident_detail(
            kubeconfig=kubeconfig,
            namespace=namespace,
            incident_id=incident_id,
            backend_port=backend_port,
        )

        if detail is None:
            # Transport error - continue polling
            if log_callback:
                log_callback(
                    f"P4c diagnosis poll {attempt}/{max_attempts}: "
                    f"transport error fetching incident detail"
                )
        else:
            # Log compact status
            if log_callback:
                log_callback(
                    f"P4c diagnosis poll {attempt}/{max_attempts}: "
                    f"incident.status={detail.status} "
                    f"loop_summary.status={detail.loop_summary_status or 'null'} "
                    f"review_available={detail.review_available}"
                )

            # Check for completion
            loop_status = detail.loop_summary_status
            if loop_status == "completed":
                return TargetedDiagnosisPollResult(
                    success=True,
                    final_status=detail.status,
                    loop_summary_status=loop_status,
                    review_available=detail.review_available,
                    attempts=attempt,
                    max_attempts=max_attempts,
                    final_detail=detail,
                )

            # Also accept review_available as completion signal
            if detail.review_available:
                return TargetedDiagnosisPollResult(
                    success=True,
                    final_status=detail.status,
                    loop_summary_status=loop_status,
                    review_available=True,
                    attempts=attempt,
                    max_attempts=max_attempts,
                    final_detail=detail,
                )

        # Wait before next poll
        if attempt < max_attempts:
            time.sleep(poll_interval_seconds)

    # Timeout - return failure state
    final_detail = fetch_backend_incident_detail(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
        backend_port=backend_port,
    )

    return TargetedDiagnosisPollResult(
        success=False,
        final_status=final_detail.status if final_detail else "unknown",
        loop_summary_status=final_detail.loop_summary_status if final_detail else None,
        review_available=final_detail.review_available if final_detail else False,
        attempts=max_attempts,
        max_attempts=max_attempts,
        final_detail=final_detail,
        failure_reason=FAILURE_TARGETED_LOOP_NOT_COMPLETED,
        error_detail=f"Polling timeout after {max_attempts} attempts",
    )
