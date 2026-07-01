"""Incident automatic diagnosis loop one-pass API handler.

This module handles POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
requests. It provides an authenticated manual API for running exactly one pass of the
automatic diagnosis loop collector for a specific incident.

This endpoint wraps collect_automatic_diagnosis_evidence() and must NOT be confused
with the separate /diagnosis-loop/one-pass endpoint which uses fake-runner semantics.

Security guarantees:
- Protected by existing auth guard (requires authenticated session)
- No raw artifact contents exposed
- Bounded request/response
- Read-only: no mutation, no remediation, no kubectl
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from ..collect.incident_diagnosis_auto_loop import collect_automatic_diagnosis_evidence
from .server_response import send_json_response

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)

# Route pattern for automatic diagnosis loop one-pass
# Pattern: /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
_AUTOMATIC_DIAGNOSIS_LOOP_PATTERN = re.compile(
    r"^/api/incidents/([^/]+)/automatic-diagnosis-loop/one-pass$"
)


def handle_incident_automatic_diagnosis_loop_one_pass_api(
    handler: HealthUIRequestHandler,
    incident_id: str,
) -> None:
    """Handle POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass.

    This endpoint wraps collect_automatic_diagnosis_evidence() to provide a
    targeted incident-specific trigger for the automatic diagnosis loop.

    Unlike /diagnosis-loop/one-pass which uses fake-runner semantics,
    this endpoint runs the REAL automatic diagnosis loop collector.

    Request body: None or empty (incident_id from URL)

    Response (success):
        {
            "schema_version": "1.0",
            "incident_id": "incident-123",
            "eligible": true,
            "run_id": "auto-incident-123-20240101...",
            "collector_run_id": "collector-...",
            "checks_run": 3,
            "review_packet_name": "auto-incident-123-...-diagnosis-review-packet.json",
            "loop_summary_status": "completed",
            "automatic_diagnosis_review_available": true,
            "no_remediation_attempted": true,
            "read_only": true
        }

    Response (not eligible):
        {
            "schema_version": "1.0",
            "incident_id": "incident-123",
            "eligible": false,
            "eligibility_reason": "...",
            "skipped": true
        }

    Response (error):
        {
            "schema_version": "1.0",
            "incident_id": "incident-123",
            "error": "bounded error message",
            "error_class": "..."
        }

    Args:
        handler: The HTTP request handler instance
        incident_id: The incident ID from the URL path
    """
    # Step 1: Validate method
    if handler.command != "POST":
        send_json_response(
            handler,
            _make_error_response(incident_id, "Method not allowed", error_class="method_not_allowed"),
            code=405,
        )
        return

    # Step 2: Compute external_analysis_dir from handler's health_root
    external_analysis_dir = handler._health_root / "external-analysis"

    # Step 3: Invoke the automatic diagnosis loop collector
    try:
        result = collect_automatic_diagnosis_evidence(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
        )
    except Exception as exc:
        error_class = exc.__class__.__name__
        _logger.exception(
            "Automatic diagnosis loop failed for incident_id=%s error_class=%s",
            incident_id,
            error_class,
        )
        send_json_response(
            handler,
            _make_error_response(
                incident_id,
                "collector_error",
                error_class=error_class,
            ),
            code=500,
        )
        return

    # Step 4: Build response based on result
    if result.skipped:
        response = {
            "schema_version": "1.0",
            "incident_id": incident_id,
            "eligible": result.eligible,
            "eligibility_reason": result.eligibility_reason,
            "skipped": True,
            "skip_reason": result.skip_reason,
        }
        send_json_response(handler, response, code=200)
        return

    # Success or error with partial results
    incident_result = result.incident_results.get(incident_id)

    if incident_result is None:
        send_json_response(
            handler,
            _make_error_response(incident_id, "No result for incident", error_class="no_result"),
            code=500,
        )
        return

    if incident_result.error:
        response = {
            "schema_version": "1.0",
            "incident_id": incident_id,
            "eligible": incident_result.eligible,
            "run_id": incident_result.run_id,
            "collector_run_id": result.collector_run_id,
            "error": incident_result.error,
            "error_class": "collector_incident_error",
            "read_only": True,
            "no_remediation_attempted": True,
        }
        send_json_response(handler, response, code=200)
        return

    # Success
    review_packet_name = None
    if incident_result.review_packet_path:
        review_packet_name = incident_result.review_packet_path.name

    response = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "eligible": incident_result.eligible,
        "eligibility_reason": incident_result.eligibility_reason,
        "run_id": incident_result.run_id,
        "collector_run_id": result.collector_run_id,
        "checks_run": incident_result.checks_run,
        "checks_skipped": incident_result.checks_skipped,
        "checks_rejected": incident_result.checks_rejected,
        "review_packet_name": review_packet_name,
        "loop_summary_status": "completed" if incident_result.run_id else "not_run",
        "automatic_diagnosis_review_available": incident_result.review_packet_path is not None,
        "no_remediation_attempted": True,
        "read_only": True,
    }
    send_json_response(handler, response, code=200)


def _make_error_response(
    incident_id: str,
    error: str,
    error_class: str | None = None,
) -> dict:
    """Create a bounded error response.

    Args:
        incident_id: The incident ID
        error: Error message to include
        error_class: Optional error classification

    Returns:
        Bounded error response dict
    """
    result: dict = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "read_only": True,
        "no_remediation_attempted": True,
        "error": error,
    }
    if error_class:
        result["error_class"] = error_class
    return result


def match_automatic_diagnosis_loop_route(path: str) -> str | None:
    """Match a path against the automatic diagnosis loop route pattern.

    Args:
        path: The request path to match

    Returns:
        The incident_id if the path matches, None otherwise
    """
    match = _AUTOMATIC_DIAGNOSIS_LOOP_PATTERN.match(path)
    if match:
        return match.group(1)
    return None


__all__ = [
    "handle_incident_automatic_diagnosis_loop_one_pass_api",
    "match_automatic_diagnosis_loop_route",
]
