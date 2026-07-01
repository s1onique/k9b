"""Backend incident HTTP contracts for OTel demo lab.

This module contains contracts (dataclasses, typed aliases) extracted from
k9b_otel_demo_lab_k8s_diagnosis_backend_http.py for better organization.
"""

from __future__ import annotations

from dataclasses import dataclass

from scripts.lab_common.provider_curl_helpers import CurlResult


@dataclass
class BackendIncidentFetchContext:
    """Shared context for backend fetch operations.

    Used by parse and classify helpers to avoid repeated parameter passing.
    """

    url: str
    api_path: str
    encoded_incident_id: str
    body_prefix: str = ""
    stderr_prefix: str = ""
    json_error: str | None = None


def make_fetch_context(
    url: str,
    api_path: str,
    encoded_incident_id: str,
    curl_result: CurlResult,
) -> BackendIncidentFetchContext:
    """Create a fetch context from a curl result.

    Args:
        url: Full URL that was fetched
        api_path: API path component
        encoded_incident_id: URL-encoded incident ID
        curl_result: Result from curl operation

    Returns:
        BackendIncidentFetchContext with bounded diagnostics
    """
    body_prefix = curl_result.body[:200] if curl_result.body else ""
    stderr_prefix = curl_result.stderr[:200] if curl_result.stderr else ""
    return BackendIncidentFetchContext(
        url=url,
        api_path=api_path,
        encoded_incident_id=encoded_incident_id,
        body_prefix=body_prefix,
        stderr_prefix=stderr_prefix,
    )


__all__ = [
    "BackendIncidentFetchContext",
    "make_fetch_context",
]
