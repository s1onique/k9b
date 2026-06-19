"""Incident diagnosis loop one-pass API handler.

This module handles POST /api/incidents/{incident_id}/diagnosis-loop/one-pass
requests. It provides an authenticated manual API for running exactly one
deterministic read-only diagnosis loop pass.

Security guarantees:
- Protected by existing auth guard (requires authenticated session)
- No Kubernetes API calls
- No subprocess/shell execution
- Bounded request/response
- No raw artifact contents exposed
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from ..collect.api_incident_diagnosis_loop import (
    DiagnosisLoopOnePassRequest,
    handle_diagnosis_loop_one_pass,
)
from .server_response import send_json_response

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)

# Route pattern for diagnosis loop one-pass
# Pattern: /api/incidents/{incident_id}/diagnosis-loop/one-pass
_DIAGNOSIS_LOOP_PATTERN = re.compile(
    r"^/api/incidents/([^/]+)/diagnosis-loop/one-pass$"
)


def handle_incident_diagnosis_loop_one_pass_api(
    handler: HealthUIRequestHandler,
    incident_id: str,
) -> None:
    """Handle POST /api/incidents/{incident_id}/diagnosis-loop/one-pass.

    Request body:
        {
            "run_id": "manual-loop-001",
            "diagnosis_report": {
                "diagnosis": {
                    "recommended_investigations": [
                        {
                            "check_id": "pod_logs",
                            "title": "Check pod logs",
                            "read_only": true,
                            "source": "manual"
                        }
                    ]
                }
            }
        }

    Response (success):
        {
            "schema_version": "1.0",
            "incident_id": "incident-123",
            "run_id": "manual-loop-001",
            "read_only": true,
            "allowed_actions": [],
            "decision": "run_allowed_read_only_checks",
            "checks_requested": 1,
            "checks_run": 1,
            "checks_skipped": 0,
            "checks_rejected": 0,
            "artifacts": {
                "read_only_check_results": {
                    "written": true,
                    "name": "manual-loop-001-read-only-check-results.json"
                },
                "diagnosis_loop_pass": {
                    "written": true,
                    "name": "manual-loop-001-diagnosis-loop-pass.json"
                }
            },
            "case_file_linked_artifact": true,
            "safety_metadata": {...}
        }

    Response (error):
        {
            "schema_version": "1.0",
            "incident_id": "incident-123",
            "run_id": "...",
            "error": "bounded error message"
        }

    Args:
        handler: The HTTP request handler instance
        incident_id: The incident ID from the URL path
    """
    # Step 1: Parse request body
    try:
        content_length = int(handler.headers.get("Content-Length", 0))

        # Enforce maximum body size
        if content_length > 64 * 1024:  # 64KB
            send_json_response(
                handler,
                _make_error_response(incident_id, "", "Request body too large"),
                code=400,
            )
            return

        if content_length == 0:
            body: dict[str, object] = {}
        else:
            body_bytes = handler.rfile.read(content_length)
            body = json.loads(body_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to parse diagnosis loop request: %s", exc)
        send_json_response(
            handler,
            _make_error_response(incident_id, "", f"Invalid request body: {exc}"),
            code=400,
        )
        return

    # Step 2: Validate and parse request
    try:
        request = DiagnosisLoopOnePassRequest.from_dict(body)
    except ValueError as exc:
        _logger.warning("Invalid diagnosis loop request: %s", exc)
        send_json_response(
            handler,
            _make_error_response(incident_id, request_run_id="", error=str(exc)),
            code=400,
        )
        return

    # Step 3: Compute external_analysis_dir from handler's health_root
    external_analysis_dir = handler._health_root / "external-analysis"

    # Step 4: Handle the request
    response = handle_diagnosis_loop_one_pass(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        request=request,
    )

    # Step 5: Determine response code
    code = 404 if response.error == "Incident not found" else 200

    # Step 6: Send response
    send_json_response(
        handler,
        response.to_dict(),
        code=code,
    )


def _make_error_response(
    incident_id: str,
    request_run_id: str,
    error: str,
) -> dict[str, object]:
    """Create a bounded error response.

    Args:
        incident_id: The incident ID
        request_run_id: The run_id from request (may be empty)
        error: Error message to include

    Returns:
        Bounded error response dict
    """
    result: dict[str, object] = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "read_only": True,
        "allowed_actions": [],
        "error": error,
    }
    if request_run_id:
        result["run_id"] = request_run_id
    return result


def match_diagnosis_loop_route(path: str) -> str | None:
    """Match a path against the diagnosis loop route pattern.

    Args:
        path: The request path to match

    Returns:
        The incident_id if the path matches, None otherwise
    """
    match = _DIAGNOSIS_LOOP_PATTERN.match(path)
    if match:
        return match.group(1)
    return None


__all__ = [
    "handle_incident_diagnosis_loop_one_pass_api",
    "match_diagnosis_loop_route",
]