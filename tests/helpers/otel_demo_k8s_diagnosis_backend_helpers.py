"""Shared test helpers for backend helpers tests.

This module provides fixtures and builders for testing the backend-targeted
diagnosis helpers.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_helpers import (
    BackendIncidentDetail,
    TargetedDiagnosisInvocationResult,
    TargetedDiagnosisPollResult,
)


def make_backend_incident_detail(
    incident_id: str = "inc-123",
    status: str = "collecting_evidence",
    evidence_count: int = 5,
    review_packet_status: str | None = "ready",
    loop_summary_status: str | None = "completed",
    review_available: bool = True,
    raw: dict[str, Any] | None = None,
) -> BackendIncidentDetail:
    """Create a BackendIncidentDetail for testing.

    Args:
        incident_id: The incident ID
        status: Incident status
        evidence_count: Number of evidence items
        review_packet_status: Review packet status
        loop_summary_status: Loop summary status
        review_available: Whether review is available
        raw: Raw API response data

    Returns:
        BackendIncidentDetail instance
    """
    return BackendIncidentDetail(
        incident_id=incident_id,
        status=status,
        evidence_count=evidence_count,
        review_packet_status=review_packet_status,
        loop_summary_status=loop_summary_status,
        review_available=review_available,
        raw=raw or {},
    )


def make_successful_invocation_result(
    incident_id: str = "inc-123",
    http_status: int = 200,
    response_data: dict[str, Any] | None = None,
) -> TargetedDiagnosisInvocationResult:
    """Create a successful invocation result for testing.

    Args:
        incident_id: The incident ID
        http_status: HTTP status code
        response_data: Response data

    Returns:
        Successful TargetedDiagnosisInvocationResult
    """
    return TargetedDiagnosisInvocationResult(
        success=True,
        http_status=http_status,
        body='{"status": "diagnosis_pass_completed"}',
        json_parsed=True,
        response_data=response_data or {"status": "diagnosis_pass_completed"},
    )


def make_failed_invocation_result(
    error_class: str = "targeted_automatic_diagnosis_invocation_http_error",
    http_status: int = 500,
    error_detail: str = "HTTP 500",
    curl_rc: int | None = 0,
) -> TargetedDiagnosisInvocationResult:
    """Create a failed invocation result for testing.

    Args:
        error_class: Error class constant
        http_status: HTTP status code
        error_detail: Error detail message
        curl_rc: Curl return code

    Returns:
        Failed TargetedDiagnosisInvocationResult
    """
    return TargetedDiagnosisInvocationResult(
        success=False,
        http_status=http_status,
        body="Internal Server Error",
        json_parsed=False,
        error_class=error_class,
        error_detail=error_detail,
        curl_rc=curl_rc,
    )


def make_successful_poll_result(
    final_status: str = "diagnosed",
    loop_summary_status: str = "completed",
    review_available: bool = True,
    attempts: int = 5,
    max_attempts: int = 12,
) -> TargetedDiagnosisPollResult:
    """Create a successful poll result for testing.

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


def make_failed_poll_result(
    final_status: str = "diagnosing",
    loop_summary_status: str | None = "running",
    failure_reason: str = "targeted_automatic_diagnosis_loop_not_completed",
    attempts: int = 12,
    max_attempts: int = 12,
) -> TargetedDiagnosisPollResult:
    """Create a failed poll result for testing.

    Args:
        final_status: Final incident status
        loop_summary_status: Loop summary status
        failure_reason: Failure reason constant
        attempts: Number of poll attempts
        max_attempts: Maximum allowed attempts

    Returns:
        Failed TargetedDiagnosisPollResult
    """
    return TargetedDiagnosisPollResult(
        success=False,
        final_status=final_status,
        loop_summary_status=loop_summary_status,
        review_available=False,
        attempts=attempts,
        max_attempts=max_attempts,
        failure_reason=failure_reason,
        error_detail=f"Polling timeout after {attempts} attempts",
    )


def make_mock_curl_result(
    http_code: int = 200,
    body: str = '{"status": "ok"}',
    curl_rc: int = 0,
    success: bool = True,
) -> MagicMock:
    """Create a mock CurlResult for testing.

    Args:
        http_code: HTTP status code
        body: Response body
        curl_rc: Curl return code
        success: Whether the request was successful

    Returns:
        Mock CurlResult
    """
    return MagicMock(
        http_code=http_code,
        body=body,
        curl_rc=curl_rc,
        success=success,
        stderr="",
    )
