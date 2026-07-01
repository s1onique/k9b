"""Shared test helpers for backend HTTP tests.

This module provides fixtures and builders for testing the backend-targeted
diagnosis HTTP helpers.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

# =============================================================================
# Mock curl result builders
# =============================================================================


def make_curl_mock(
    http_code: int = 200,
    body: str = '{"status": "ok"}',
    curl_rc: int = 0,
    success: bool = True,
    stderr: str = "",
) -> MagicMock:
    """Create a mock CurlResult for testing.

    Args:
        http_code: HTTP status code
        body: Response body
        curl_rc: Curl return code
        success: Whether the request was successful
        stderr: Standard error output

    Returns:
        Mock CurlResult
    """
    return MagicMock(
        http_code=http_code,
        body=body,
        curl_rc=curl_rc,
        success=success,
        stderr=stderr,
    )


def make_success_curl_mock(
    body: str | dict[str, Any] = '{"status": "ok"}',
    http_code: int = 200,
) -> MagicMock:
    """Create a mock successful curl result.

    Args:
        body: Response body (string or dict to be JSON-encoded)
        http_code: HTTP status code

    Returns:
        Mock successful CurlResult
    """
    body_str = body if isinstance(body, str) else json.dumps(body)
    return make_curl_mock(
        http_code=http_code,
        body=body_str,
        curl_rc=0,
        success=True,
        stderr="",
    )


def make_transport_error_curl_mock(
    curl_rc: int = 7,
    stderr: str = "Connection refused",
) -> MagicMock:
    """Create a mock transport error curl result.

    Args:
        curl_rc: Curl return code
        stderr: Error message

    Returns:
        Mock transport error CurlResult
    """
    return make_curl_mock(
        http_code=0,
        body="",
        curl_rc=curl_rc,
        success=False,
        stderr=stderr,
    )


def make_http_error_curl_mock(
    http_code: int = 404,
    body: str = '{"error": "not found"}',
) -> MagicMock:
    """Create a mock HTTP error curl result.

    Args:
        http_code: HTTP status code
        body: Error response body

    Returns:
        Mock HTTP error CurlResult
    """
    return make_curl_mock(
        http_code=http_code,
        body=body,
        curl_rc=0,
        success=http_code < 400,
        stderr="",
    )


def make_html_body_curl_mock() -> MagicMock:
    """Create a mock curl result with HTML body (simulates proxy redirect).

    Returns:
        Mock CurlResult with HTML body
    """
    html_body = "<!doctype html><html><body>Login Page</body></html>"
    return make_curl_mock(
        http_code=200,
        body=html_body,
        curl_rc=0,
        success=True,
        stderr="",
    )


# =============================================================================
# Incident data builders
# =============================================================================


def build_incident_data(
    status: str = "collecting_evidence",
    evidence_count: int = 5,
    review_packet_status: str | None = "ready",
    loop_summary_status: str | None = "completed",
    review_available: bool = True,
) -> dict[str, Any]:
    """Build incident API response data.

    Args:
        status: Incident status
        evidence_count: Number of evidence items
        review_packet_status: Review packet status (None to omit)
        loop_summary_status: Loop summary status (None to omit)
        review_available: Whether review is available

    Returns:
        Incident API response dict
    """
    data: dict[str, Any] = {
        "status": status,
        "evidence_count": evidence_count,
    }
    if review_packet_status is not None:
        data["review_packet"] = {"status": review_packet_status}
    if loop_summary_status is not None:
        data["automatic_diagnosis_loop_summary"] = {"status": loop_summary_status}
    data["automatic_diagnosis_review"] = {"available": review_available}
    return data


def make_incident_curl_mock(
    status: str = "collecting_evidence",
    evidence_count: int = 5,
    **kwargs: Any,
) -> MagicMock:
    """Create a curl mock with incident data.

    Args:
        status: Incident status
        evidence_count: Number of evidence items
        **kwargs: Additional kwargs passed to build_incident_data

    Returns:
        Mock CurlResult with incident JSON body
    """
    data = build_incident_data(status=status, evidence_count=evidence_count, **kwargs)
    return make_success_curl_mock(body=data)


# =============================================================================
# Test constants
# =============================================================================


KUBECONFIG = "/path/to/kubeconfig"
NAMESPACE = "k9b"
BASE_URL = "http://localhost:8080"


def incident_url(incident_id: str) -> str:
    """Build incident URL.

    Args:
        incident_id: The incident ID

    Returns:
        Full incident URL
    """
    return f"{BASE_URL}/api/incidents/{incident_id}"


def diagnosis_loop_url(incident_id: str) -> str:
    """Build diagnosis loop invocation URL.

    Args:
        incident_id: The incident ID

    Returns:
        Full diagnosis loop URL
    """
    return f"{BASE_URL}/api/automatic-diagnosis-loop/one-pass"
