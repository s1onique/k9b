"""Backend HTTP response parsing for OTel demo lab.

This module extracts JSON parsing and response body normalization from
k9b_otel_demo_lab_k8s_diagnosis_backend_http.py.
"""

from __future__ import annotations

import json
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    BackendIncidentDetail,
)


def extract_backend_incident_detail_json(
    body: str,
    incident_id: str,
) -> tuple[BackendIncidentDetail | None, str | None, str | None]:
    """Extract and parse incident detail JSON from backend response.

    This function handles:
    - JSON parsing with error reporting
    - Body type validation (must be dict, not array/string/etc.)
    - BackendIncidentDetail object construction

    Args:
        body: Raw response body string
        incident_id: Incident ID for context in errors

    Returns:
        Tuple of (incident, json_error, contract_error)
        - incident: Parsed BackendIncidentDetail if successful
        - json_error: Error message if JSON parsing failed
        - contract_error: Error message if contract validation failed
        Only one of the three will be non-None on failure.
    """
    # Parse JSON
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        return (None, f"JSON parse error: {e}", None)

    # JSON must be an object (dict), not array/string/etc.
    if not isinstance(data, dict):
        body_type = type(data).__name__
        return (None, None, f"Expected JSON object, got {body_type}")

    # Try to parse into BackendIncidentDetail
    try:
        incident = BackendIncidentDetail.from_dict(incident_id, data)
        return (incident, None, None)
    except (ValueError, TypeError, KeyError) as e:
        return (None, None, f"Contract error: {e}")


def safe_json_loads(body: str) -> tuple[dict[str, Any] | None, str | None]:
    """Safely parse JSON from body with bounded error reporting.

    Args:
        body: Raw response body string

    Returns:
        Tuple of (parsed_data, error_message)
        parsed_data is None if parsing failed
    """
    try:
        return (json.loads(body), None)
    except json.JSONDecodeError as e:
        return (None, str(e))


def bound_body_prefix(body: str, max_len: int = 200) -> str:
    """Bound body string for diagnostics display.

    Args:
        body: Raw body string
        max_len: Maximum length to return

    Returns:
        Bounded body prefix with ellipsis if truncated
    """
    if not body:
        return ""
    if len(body) <= max_len:
        return body
    return body[:max_len]


__all__ = [
    "extract_backend_incident_detail_json",
    "safe_json_loads",
    "bound_body_prefix",
]
