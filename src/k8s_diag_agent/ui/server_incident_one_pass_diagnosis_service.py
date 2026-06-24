"""Incident one-pass diagnosis service API handler.

This module handles POST /api/incidents/{incident_id}/one-pass-diagnosis
requests. It provides an authenticated manual API for running the incident
diagnosis service (run_incident_one_pass_diagnosis) with proper dependency injection.

Security guarantees:
- Protected by existing auth guard (requires authenticated session)
- No Kubernetes API calls
- No subprocess/shell execution
- Bounded request/response
- No raw artifact contents exposed
- Fail-closed on missing providers
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from ..collect.api_incident_one_pass_diagnosis_provider import (
    get_artifact_writer,
    get_diagnosis_provider,
    get_fake_handlers,
    get_golden_case_case_dir,
    get_golden_case_evidence_provider,
    get_golden_case_manifest,
    is_golden_case_mode,
)
from ..collect.api_incident_one_pass_diagnosis_service import (
    OnePassServiceRequest,
    handle_one_pass_diagnosis_service,
)
from .server_response import send_json_response

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)

# Route pattern for one-pass diagnosis service
# Pattern: /api/incidents/{incident_id}/one-pass-diagnosis
_DIAGNOSIS_SERVICE_PATTERN = re.compile(
    r"^/api/incidents/([^/]+)/one-pass-diagnosis$"
)


def handle_incident_one_pass_diagnosis_service_api(
    handler: HealthUIRequestHandler,
    incident_id: str,
) -> None:
    """Handle POST /api/incidents/{incident_id}/one-pass-diagnosis.

    Request body:
        {
            "incident_id": "incident-123",  // optional, defaults to URL incident_id
            "run_id": "manual-service-001"  // optional, auto-generated if not provided
        }

    Contract:
        - URL incident_id is authoritative
        - Body incident_id is optional; if present, must match URL incident_id
        - Mismatch between URL and body incident_id returns 400

    Response (success):
        {
            "schema_version": "1.0",
            "incident_id": "incident-123",
            "run_id": "manual-service-001",
            "category": "readiness_probe_failure",
            "root_cause": "readiness probe failure",
            "confidence": "high",
            "description": "Pod is not ready due to failing readiness probe",
            "evidence_refs": [...],
            "read_only": true,
            "allowed_actions": [],
            "forbidden_actions_observed": [],
            "mutation_proposals_observed": [],
            "decision": "run_allowed_read_only_checks",
            "checks_run": 3,
            "next_checks": [...],
            "artifact_written": true,
            "artifact_name": "incident-123-diagnosis.json",
            "error": null
        }

    Response (error):
        {
            "schema_version": "1.0",
            "incident_id": "incident-123",
            "run_id": "...",
            "error": "bounded error message",
            ...
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
        _logger.warning("Failed to parse one-pass diagnosis service request: %s", exc)
        send_json_response(
            handler,
            _make_error_response(incident_id, "", f"Invalid request body: {exc}"),
            code=400,
        )
        return

    # Step 2: Check URL/body incident_id mismatch (URL is authoritative)
    body_incident_id = body.get("incident_id")
    if body_incident_id is not None and body_incident_id != incident_id:
        _logger.warning(
            "incident_id mismatch: URL=%r, body=%r",
            incident_id,
            body_incident_id,
        )
        send_json_response(
            handler,
            _make_error_response(incident_id, "", "incident_id in body must match URL path"),
            code=400,
        )
        return

    # Step 3: If body is empty, use URL incident_id
    if content_length == 0 or "incident_id" not in body:
        # Body is optional; use URL incident_id
        body_with_incident_id = dict(body)
        body_with_incident_id["incident_id"] = incident_id
        body = body_with_incident_id

    # Step 4: Validate and parse request
    try:
        request = OnePassServiceRequest.from_dict(body)
    except ValueError as exc:
        _logger.warning("Invalid one-pass diagnosis service request: %s", exc)
        send_json_response(
            handler,
            _make_error_response(incident_id, request_run_id="", error=str(exc)),
            code=400,
        )
        return

    # Step 5: Compute external_analysis_dir from handler's health_root
    external_analysis_dir = handler._health_root / "external-analysis"

    # Step 6: Get injected dependencies from provider registry
    # Tests set these via set_* functions; production defaults to None (fail-closed)
    diagnosis_provider = get_diagnosis_provider()
    fake_handlers = get_fake_handlers()
    artifact_writer = get_artifact_writer()

    # Step 7: Get golden-case context if set (for ACT-local verification)
    golden_case_mode = is_golden_case_mode()
    golden_case_manifest = get_golden_case_manifest() if golden_case_mode else None
    golden_case_case_dir = get_golden_case_case_dir() if golden_case_mode else None
    golden_case_evidence_provider = get_golden_case_evidence_provider() if golden_case_mode else None

    # Step 8: Handle the request with injected dependencies
    response = handle_one_pass_diagnosis_service(
        incident_id=incident_id,
        external_analysis_dir=external_analysis_dir,
        request=request,
        diagnosis_provider=diagnosis_provider,
        fake_handlers=fake_handlers,
        artifact_writer=artifact_writer,
        golden_case_mode=golden_case_mode,
        golden_case_manifest=golden_case_manifest,
        golden_case_case_dir=golden_case_case_dir,
        golden_case_evidence_provider=golden_case_evidence_provider,
    )

    # Step 9: Determine response code
    code = 404 if response.error == "Incident not found" else 200
    if response.error and "not found" in response.error.lower():
        code = 404
    elif response.error:
        # Service errors return 500 (internal error)
        code = 500

    # Step 10: Send response
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


def match_diagnosis_service_route(path: str) -> str | None:
    """Match a path against the diagnosis service route pattern.

    Args:
        path: The request path to match

    Returns:
        The incident_id if the path matches, None otherwise
    """
    match = _DIAGNOSIS_SERVICE_PATTERN.match(path)
    if match:
        return match.group(1)
    return None


__all__ = [
    "handle_incident_one_pass_diagnosis_service_api",
    "match_diagnosis_service_route",
]