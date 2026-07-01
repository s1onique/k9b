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
    FAILURE_TARGETED_LOOP_NOT_STARTED,
    TargetedDiagnosisPollResult,
)
from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_http import (
    fetch_backend_incident_detail,
)
from scripts.lab_common.constants import DEFAULT_K9B_BACKEND_PORT

# Terminal states for diagnosis loop
TERMINAL_SUCCESS = {"completed", "success", "ready_for_review"}
TERMINAL_FAILURE = {"failed", "error", "budget_exhausted", "not_eligible", "provider_unavailable"}
NON_TERMINAL = {"not_run", "running", "collecting_evidence", "pending"}


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
            # Classify loop status
            loop_status = detail.loop_summary_status

            # Check for terminal success states
            if loop_status in TERMINAL_SUCCESS:
                return TargetedDiagnosisPollResult(
                    success=True,
                    final_status=detail.status,
                    loop_summary_status=loop_status,
                    review_available=detail.review_available,
                    attempts=attempt,
                    max_attempts=max_attempts,
                    final_detail=detail,
                )

            # Check for terminal failure states
            if loop_status in TERMINAL_FAILURE:
                return TargetedDiagnosisPollResult(
                    success=False,
                    final_status=detail.status,
                    loop_summary_status=loop_status,
                    review_available=detail.review_available,
                    attempts=attempt,
                    max_attempts=max_attempts,
                    final_detail=detail,
                    failure_reason=loop_status,
                    error_detail=f"Diagnosis loop reached terminal failure state: {loop_status}",
                )

            # Handle not_run as a specific failure - this means the loop was never started
            # This is the PRIMARY bug: HTTP 200 was returned but no pass actually ran
            if loop_status == "not_run" or loop_status is None:
                if log_callback:
                    log_callback(
                        f"P4c diagnosis poll {attempt}/{max_attempts}: "
                        f"WARNING: loop_summary.status=not_run - diagnosis loop never started! "
                        f"This indicates the targeted invocation returned HTTP 200 but no pass ran."
                    )
                # Do NOT treat not_run as completion - continue polling or fail
                # The loop may be disabled, not eligible, or the backend returned 200 without running

            # Non-terminal states: continue polling
            # (running, collecting_evidence, pending)

        # Wait before next poll
        if attempt < max_attempts:
            time.sleep(poll_interval_seconds)

    # Timeout - return failure state with specific failure reason
    final_detail = fetch_backend_incident_detail(
        kubeconfig=kubeconfig,
        namespace=namespace,
        incident_id=incident_id,
        backend_port=backend_port,
    )

    final_loop_status = final_detail.loop_summary_status if final_detail else None

    # Determine specific failure reason based on final state
    if final_loop_status == "not_run" or final_loop_status is None:
        failure_reason = FAILURE_TARGETED_LOOP_NOT_STARTED
        error_detail = (
            "Diagnosis loop never started (loop_summary.status=not_run). "
            "The targeted invocation returned HTTP 200 but no pass was recorded. "
            "Possible causes: loop disabled, provider unhealthy, or endpoint no-op path."
        )
    else:
        failure_reason = FAILURE_TARGETED_LOOP_NOT_COMPLETED
        error_detail = f"Polling timeout after {max_attempts} attempts. Final loop status: {final_loop_status}"

    return TargetedDiagnosisPollResult(
        success=False,
        final_status=final_detail.status if final_detail else "unknown",
        loop_summary_status=final_loop_status,
        review_available=final_detail.review_available if final_detail else False,
        attempts=max_attempts,
        max_attempts=max_attempts,
        final_detail=final_detail,
        failure_reason=failure_reason,
        error_detail=error_detail,
    )
