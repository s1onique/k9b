"""Shared test helpers for backend contracts tests.

This module provides fixtures and builders for testing the backend-targeted
diagnosis contracts (BackendIncidentDetail, TargetedDiagnosisInvocationResult,
TargetedDiagnosisPollResult, BackendIncidentFetchResult).
"""

from __future__ import annotations

from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
    FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
    FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
    FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
    FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
    FAILURE_TARGETED_INVOCATION_INVALID_JSON,
    FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
    FAILURE_TARGETED_LOOP_NOT_COMPLETED,
    BackendIncidentDetail,
    BackendIncidentFetchResult,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
)

# =============================================================================
# BackendIncidentDetail helpers
# =============================================================================


def build_complete_incident_data(
    incident_id: str = "inc-123",
    status: str = "collecting_evidence",
    evidence_count: int = 5,
    review_packet_status: str = "ready",
    loop_summary_status: str = "completed",
    review_available: bool = True,
) -> dict[str, Any]:
    """Build a complete incident API response payload.

    Args:
        incident_id: The incident ID (used in docstrings only)
        status: Incident status
        evidence_count: Number of evidence items
        review_packet_status: Review packet status
        loop_summary_status: Loop summary status
        review_available: Whether review is available

    Returns:
        Complete incident API response dict
    """
    return {
        "status": status,
        "evidence_count": evidence_count,
        "review_packet": {"status": review_packet_status},
        "automatic_diagnosis_loop_summary": {"status": loop_summary_status},
        "automatic_diagnosis_review": {"available": review_available},
    }


def build_minimal_incident_data(incident_id: str = "inc-456") -> dict[str, Any]:
    """Build a minimal (empty) incident API response payload.

    Args:
        incident_id: The incident ID (used in docstrings only)

    Returns:
        Empty dict for minimal incident
    """
    return {}


def build_incident_detail(incident_id: str, data: dict[str, Any]) -> BackendIncidentDetail:
    """Parse incident data into BackendIncidentDetail.

    Args:
        incident_id: The incident ID
        data: Incident API response data

    Returns:
        BackendIncidentDetail instance
    """
    return BackendIncidentDetail.from_dict(incident_id, data)


# =============================================================================
# TargetedDiagnosisInvocationResult helpers
# =============================================================================


def build_success_invocation(
    http_status: int = 200,
    response_data: dict[str, Any] | None = None,
    body: str | None = None,
) -> TargetedDiagnosisInvocationResult:
    """Build a successful invocation result.

    Args:
        http_status: HTTP status code
        response_data: Response data dict
        body: Optional custom body string

    Returns:
        Successful TargetedDiagnosisInvocationResult
    """
    return TargetedDiagnosisInvocationResult(
        success=True,
        http_status=http_status,
        body=body or '{"status": "ok"}',
        json_parsed=True,
        response_data=response_data or {"status": "ok"},
    )


def build_http_error_invocation(
    http_status: int = 500,
    error_detail: str = "HTTP 500",
) -> TargetedDiagnosisInvocationResult:
    """Build an HTTP error invocation result.

    Args:
        http_status: HTTP status code
        error_detail: Error detail message

    Returns:
        HTTP error TargetedDiagnosisInvocationResult
    """
    return TargetedDiagnosisInvocationResult(
        success=False,
        http_status=http_status,
        body="Internal Server Error",
        json_parsed=False,
        error_class=FAILURE_TARGETED_INVOCATION_HTTP_ERROR,
        error_detail=error_detail,
    )


def build_transport_error_invocation(
    curl_rc: int = 7,
    error_detail: str = "Transport error",
) -> TargetedDiagnosisInvocationResult:
    """Build a transport error invocation result.

    Args:
        curl_rc: Curl return code
        error_detail: Error detail message

    Returns:
        Transport error TargetedDiagnosisInvocationResult
    """
    return TargetedDiagnosisInvocationResult(
        success=False,
        http_status=0,
        body="",
        json_parsed=False,
        error_class=FAILURE_TARGETED_INVOCATION_TRANSPORT_ERROR,
        error_detail=error_detail,
        curl_rc=curl_rc,
    )


def build_invalid_json_invocation(
    body: str = "not valid json",
    error_detail: str = "JSON parse error",
) -> TargetedDiagnosisInvocationResult:
    """Build an invalid JSON invocation result.

    Args:
        body: Response body that failed JSON parsing
        error_detail: Error detail message

    Returns:
        Invalid JSON TargetedDiagnosisInvocationResult
    """
    return TargetedDiagnosisInvocationResult(
        success=False,
        http_status=200,
        body=body,
        json_parsed=False,
        error_class=FAILURE_TARGETED_INVOCATION_INVALID_JSON,
        error_detail=error_detail,
    )


# =============================================================================
# TargetedDiagnosisPollResult helpers
# =============================================================================


def build_success_poll(
    final_status: str = "diagnosed",
    loop_summary_status: str = "completed",
    review_available: bool = True,
    attempts: int = 5,
    max_attempts: int = 12,
) -> TargetedDiagnosisPollResult:
    """Build a successful poll result.

    Args:
        final_status: Final incident status
        loop_summary_status: Loop summary status
        review_available: Whether review is available
        attempts: Number of poll attempts
        max_attempts: Maximum allowed attempts

    Returns:
        Successful TargetedDiagnosisPollResult
    """
    return TargetedDiagnosisPollResult(
        success=True,
        final_status=final_status,
        loop_summary_status=loop_summary_status,
        review_available=review_available,
        attempts=attempts,
        max_attempts=max_attempts,
    )


def build_timeout_poll(
    attempts: int = 12,
    max_attempts: int = 12,
) -> TargetedDiagnosisPollResult:
    """Build a polling timeout result.

    Args:
        attempts: Number of poll attempts
        max_attempts: Maximum allowed attempts

    Returns:
        Timeout TargetedDiagnosisPollResult
    """
    return TargetedDiagnosisPollResult(
        success=False,
        final_status="diagnosing",
        loop_summary_status="running",
        review_available=False,
        attempts=attempts,
        max_attempts=max_attempts,
        failure_reason=FAILURE_TARGETED_LOOP_NOT_COMPLETED,
        error_detail=f"Polling timeout after {attempts} attempts",
    )


# =============================================================================
# BackendIncidentFetchResult helpers
# =============================================================================


def build_success_fetch(
    incident_id: str = "inc-123",
    status: str = "ok",
) -> BackendIncidentFetchResult:
    """Build a successful fetch result.

    Args:
        incident_id: The incident ID
        status: Incident status

    Returns:
        Successful BackendIncidentFetchResult
    """
    return BackendIncidentFetchResult(
        success=True,
        incident=BackendIncidentDetail.from_dict(incident_id, {"status": status}),
        http_status=200,
        curl_rc=0,
        url=f"http://localhost:8080/api/incidents/{incident_id}",
        api_path=f"/api/incidents/{incident_id}",
        encoded_incident_id=incident_id,
    )


def build_transport_error_fetch(
    incident_id: str = "inc-123",
    curl_rc: int = 7,
    error_detail: str = "Transport error: curl_rc=7",
) -> BackendIncidentFetchResult:
    """Build a transport error fetch result.

    Args:
        incident_id: The incident ID
        curl_rc: Curl return code
        error_detail: Error detail message

    Returns:
        Transport error BackendIncidentFetchResult
    """
    return BackendIncidentFetchResult(
        success=False,
        error_class=FAILURE_BACKEND_INCIDENT_FETCH_TRANSPORT_ERROR,
        error_detail=error_detail,
        http_status=0,
        curl_rc=curl_rc,
        url=f"http://localhost:8080/api/incidents/{incident_id}",
        api_path=f"/api/incidents/{incident_id}",
        encoded_incident_id=incident_id,
        stderr_prefix="Connection refused",
    )


def build_not_found_fetch(
    incident_id: str = "inc-missing",
) -> BackendIncidentFetchResult:
    """Build a not found (404) fetch result.

    Args:
        incident_id: The incident ID

    Returns:
        Not found BackendIncidentFetchResult
    """
    return BackendIncidentFetchResult(
        success=False,
        error_class=FAILURE_BACKEND_INCIDENT_FETCH_NOT_FOUND,
        error_detail="Incident not found: HTTP 404",
        http_status=404,
        curl_rc=0,
        url=f"http://localhost:8080/api/incidents/{incident_id}",
        api_path=f"/api/incidents/{incident_id}",
        encoded_incident_id=incident_id,
        body_prefix='{"error": "not found"}',
    )


def build_invalid_json_fetch(
    incident_id: str = "inc-123",
    body_prefix: str = "<!doctype html>",
    json_error: str = "Expecting value",
) -> BackendIncidentFetchResult:
    """Build an invalid JSON fetch result.

    Args:
        incident_id: The incident ID
        body_prefix: Response body prefix
        json_error: JSON parsing error message

    Returns:
        Invalid JSON BackendIncidentFetchResult
    """
    return BackendIncidentFetchResult(
        success=False,
        error_class=FAILURE_BACKEND_INCIDENT_FETCH_INVALID_JSON,
        error_detail=f"JSON parse error: {json_error}",
        http_status=200,
        curl_rc=0,
        url=f"http://localhost:8080/api/incidents/{incident_id}",
        api_path=f"/api/incidents/{incident_id}",
        encoded_incident_id=incident_id,
        body_prefix=body_prefix,
        json_error=json_error,
    )


def build_http_error_fetch(
    incident_id: str = "inc-123",
    http_status: int = 500,
) -> BackendIncidentFetchResult:
    """Build an HTTP error fetch result.

    Args:
        incident_id: The incident ID
        http_status: HTTP status code

    Returns:
        HTTP error BackendIncidentFetchResult
    """
    return BackendIncidentFetchResult(
        success=False,
        error_class=FAILURE_BACKEND_INCIDENT_FETCH_HTTP_ERROR,
        error_detail=f"HTTP error: {http_status}",
        http_status=http_status,
        curl_rc=0,
        url=f"http://localhost:8080/api/incidents/{incident_id}",
        api_path=f"/api/incidents/{incident_id}",
        encoded_incident_id=incident_id,
        body_prefix="Internal Server Error",
    )


# =============================================================================
# Assertion helpers
# =============================================================================


def assert_incident_detail_fields(
    detail: BackendIncidentDetail,
    *,
    incident_id: str,
    status: str | None = None,
    evidence_count: int | None = None,
    review_packet_status: str | None = None,
    loop_summary_status: str | None = None,
    review_available: bool | None = None,
) -> None:
    """Assert BackendIncidentDetail has expected field values.

    Args:
        detail: BackendIncidentDetail to check
        incident_id: Expected incident ID
        status: Expected status (None to skip check)
        evidence_count: Expected evidence count (None to skip check)
        review_packet_status: Expected review packet status (None to skip check)
        loop_summary_status: Expected loop summary status (None to skip check)
        review_available: Expected review availability (None to skip check)
    """
    assert detail.incident_id == incident_id
    if status is not None:
        assert detail.status == status
    if evidence_count is not None:
        assert detail.evidence_count == evidence_count
    if review_packet_status is not None:
        assert detail.review_packet_status == review_packet_status
    if loop_summary_status is not None:
        assert detail.loop_summary_status == loop_summary_status
    if review_available is not None:
        assert detail.review_available == review_available


def assert_success_result(result: Any) -> None:
    """Assert a result is successful.

    Args:
        result: Result object with success attribute
    """
    assert result.success is True
    assert result.error_class is None


def assert_failure_result(result: Any, expected_error_class: str) -> None:
    """Assert a result is a failure with expected error class.

    Args:
        result: Result object with success and error_class attributes
        expected_error_class: Expected error class constant
    """
    assert result.success is False
    assert result.error_class == expected_error_class
