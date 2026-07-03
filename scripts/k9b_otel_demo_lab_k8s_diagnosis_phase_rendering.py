"""Phase failure message rendering helpers.

Responsibility: Build human-readable failure messages for diagnosis phase failures.
This module is purely presentational - no orchestration, IO, or business logic.
"""

from __future__ import annotations

from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers import (
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
)


def render_backend_targeted_invocation_failure(
    failure_reason: str,
    invocation_result: dict[str, Any],
    incident_id: str,
) -> str:
    """Build failure message for backend-targeted invocation HTTP error."""
    return (
        f"{failure_reason}: "
        f"Backend targeted endpoint returned non-2xx. "
        f"HTTP status: {invocation_result.get('http_status', 'unknown')}. "
        f"Body preview: {invocation_result.get('body', '')[:200]}. "
        f"incident_id={incident_id}"
    )


def render_backend_targeted_invocation_invalid_json(
    failure_reason: str,
    invocation_result: dict[str, Any],
    incident_id: str,
) -> str:
    """Build failure message for backend-targeted invocation invalid JSON."""
    return (
        f"{failure_reason}: "
        f"Backend targeted endpoint returned invalid JSON. "
        f"HTTP status: {invocation_result.get('http_status', 'unknown')}. "
        f"Body preview: {invocation_result.get('body', '')[:200]}. "
        f"incident_id={incident_id}"
    )


def render_backend_targeted_invocation_transport_error(
    failure_reason: str,
    invocation_result: dict[str, Any],
    incident_id: str,
) -> str:
    """Build failure message for backend-targeted invocation transport error."""
    return (
        f"{failure_reason}: "
        f"Backend targeted endpoint unreachable. "
        f"curl_rc: {invocation_result.get('curl_rc', 'unknown')}. "
        f"HTTP status: {invocation_result.get('http_status', 'unknown')}. "
        f"incident_id={incident_id}"
    )


def render_loop_not_completed_failure(
    failure_reason: str,
    poll_result: dict[str, Any],
    incident_id: str,
) -> str:
    """Build failure message for diagnosis loop not completing within timeout."""
    return (
        f"{failure_reason}: "
        f"Diagnosis did not complete within poll timeout. "
        f"Attempts: {poll_result.get('attempts', 'unknown')}/{poll_result.get('max_attempts', 'unknown')}. "
        f"Final status: {poll_result.get('final_status', 'unknown')}. "
        f"Loop summary: {poll_result.get('loop_summary_status', 'unknown')}. "
        f"Review available: {poll_result.get('review_available', False)}. "
        f"incident_id={incident_id}"
    )


def render_backend_incident_fetch_failed(
    failure_reason: str,
    fetch_result: dict[str, Any],
    incident_id: str,
) -> str:
    """Build failure message for backend incident fetch failure."""
    return (
        f"{failure_reason}: "
        f"Could not fetch incident from backend. "
        f"Check backend health and incident existence. "
        f"incident_id={incident_id}. "
        f"backend_url={fetch_result.get('url', 'N/A')}. "
        f"http_code={fetch_result.get('http_status', 'N/A')}. "
        f"curl_rc={fetch_result.get('curl_rc', 'N/A')}. "
        f"stderr={fetch_result.get('stderr_prefix', 'N/A')[:100]}"
    )


def render_kubeconfig_required_failure(
    failure_reason: str,
    incident_id: str,
) -> str:
    """Build failure message for missing kubeconfig."""
    return (
        f"{failure_reason}: "
        f"kubeconfig is required for backend-targeted diagnosis. "
        f"incident_id={incident_id}"
    )


def render_rbac_denied_failure(
    failure_reason: str,
    loop_enabled_check_error: str | None,
) -> str:
    """Build failure message for RBAC denied on scheduler deployment."""
    return (
        f"{failure_reason}: "
        "Cannot read k9b-scheduler deployment to verify loop config. "
        "The GitHub runner identity lacks 'get' permission on deployments.apps in namespace k9b. "
        f"Check error: {loop_enabled_check_error or 'N/A'}"
    )


def render_read_failed_failure(
    failure_reason: str,
    loop_enabled_check_error: str | None,
) -> str:
    """Build failure message for scheduler deployment read failure."""
    return (
        f"{failure_reason}: "
        "Cannot read k9b-scheduler deployment (network/timeout/not found). "
        "Verify the k9b namespace and scheduler deployment exist. "
        f"Check error: {loop_enabled_check_error or 'N/A'}"
    )


def render_loop_disabled_failure(
    failure_reason: str,
) -> str:
    """Build failure message for diagnosis loop disabled."""
    return (
        f"{failure_reason}: "
        "K9B_AUTOMATIC_DIAGNOSIS_LOOP_ENABLED must be set to true "
        "on the k9b-scheduler deployment (not backend). "
        "Ensure scheduler deployment has this env var configured."
    )


def render_premature_terminal_failure(
    failure_reason: str,
    pass_count: int,
    min_required_passes: int,
    incident_id: str,
) -> str:
    """Build failure message for premature terminal decision."""
    return (
        f"{failure_reason}: observed {pass_count} targeted diagnosis pass(es), "
        f"required {min_required_passes}. "
        f"The diagnosis loop was invoked and reached a terminal no-checks decision, "
        f"but lab-strict multipass evidence was not satisfied before the terminal decision. "
        f"incident_id={incident_id}"
    )


def render_generic_failure(
    failure_reason: str,
    incident_id: str,
    backend_detail: str,
) -> str:
    """Build generic failure message for unknown failure reasons."""
    return (
        f"{failure_reason}: "
        f"Automatic diagnosis loop was not invoked. "
        f"incident_id={incident_id}. "
        f"backend_detail={backend_detail}"
    )


def render_phase_failure(
    failure_reason: str,
    evidence: dict[str, Any],
    incident_id: str,
    min_required_passes: int,
) -> str:
    """Build the appropriate failure message based on failure reason.

    Args:
        failure_reason: The specific failure reason code
        evidence: The diagnosis evidence dict
        incident_id: The incident ID
        min_required_passes: Minimum required passes for lab-strict mode

    Returns:
        Human-readable failure message
    """
    invocation_result = evidence.get("targeted_invocation_result") or {}
    poll_result = evidence.get("targeted_poll_result") or {}
    backend_detail = evidence.get("backend_incident_detail") or ""

    if failure_reason == FAILURE_TARGETED_INVOCATION_HTTP_ERROR:
        return render_backend_targeted_invocation_failure(
            failure_reason, invocation_result, incident_id
        )
    elif failure_reason == FAILURE_TARGETED_INVOCATION_INVALID_JSON:
        return render_backend_targeted_invocation_invalid_json(
            failure_reason, invocation_result, incident_id
        )
    elif failure_reason == FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR:
        return render_backend_targeted_invocation_transport_error(
            failure_reason, invocation_result, incident_id
        )
    elif failure_reason == FAILURE_TARGETED_LOOP_NOT_COMPLETED:
        return render_loop_not_completed_failure(
            failure_reason, poll_result, incident_id
        )
    elif failure_reason == "backend_incident_fetch_failed":
        return render_backend_incident_fetch_failed(
            failure_reason,
            evidence.get("backend_incident_fetch_result") or {},
            incident_id,
        )
    elif failure_reason == "kubeconfig_required":
        return render_kubeconfig_required_failure(failure_reason, incident_id)
    elif failure_reason == "automatic_loop_env_rbac_denied":
        return render_rbac_denied_failure(
            failure_reason,
            evidence.get("loop_enabled_check_error"),
        )
    elif failure_reason == "automatic_loop_env_read_failed":
        return render_read_failed_failure(
            failure_reason,
            evidence.get("loop_enabled_check_error"),
        )
    elif failure_reason == "automatic_diagnosis_loop_disabled":
        return render_loop_disabled_failure(failure_reason)
    elif failure_reason == "premature_terminal_no_checks":
        return render_premature_terminal_failure(
            failure_reason,
            evidence.get("pass_count", 0),
            min_required_passes,
            incident_id,
        )
    else:
        return render_generic_failure(failure_reason, incident_id, backend_detail)
