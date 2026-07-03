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
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

from ..collect.incident_diagnosis_auto_loop_config import AutomaticDiagnosisLoopConfig
from ..collect.incident_diagnosis_auto_loop_entrypoints import (
    _positive_int,
    collect_automatic_diagnosis_evidence,
)
from ..collect.incident_diagnosis_auto_loop_models import (
    AutoLoopCollectorResult,
    AutoLoopIncidentResult,
)
from .server_response import send_json_response


def _serialize_value(value: object) -> Any:
    """Serialize a value to a JSON-compatible dict or primitive.

    Handles dict, object with .to_dict(), dataclass, and primitive types.
    Recursively processes dicts to handle nested dataclasses/lists/tuples.
    This prevents AttributeError when backend returns dict instead of
    expected dataclass instances.
    """
    if isinstance(value, dict):
        # Recursively serialize dict values to handle nested dataclasses/lists
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        # Always recurse so .to_dict() results follow the same rules as everything else
        return _serialize_value(to_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    return value


def _serialize_diagnostic_list(diagnostics: object) -> list[Any]:
    """Serialize a list of diagnostics, handling both dict and dataclass items."""
    if not diagnostics:
        return []
    if isinstance(diagnostics, (list, tuple)):
        return [_serialize_value(item) for item in diagnostics]
    return [_serialize_value(diagnostics)]

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

_logger = logging.getLogger(__name__)

# Route pattern for automatic diagnosis loop one-pass
# Pattern: /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass
_AUTOMATIC_DIAGNOSIS_LOOP_PATTERN = re.compile(
    r"^/api/incidents/([^/]+)/automatic-diagnosis-loop/one-pass$"
)


def _extract_incident_result_from_collector(
    result: AutoLoopCollectorResult | AutoLoopIncidentResult,
    incident_id: str,
) -> AutoLoopIncidentResult | None:
    """Extract incident result from collector result or return as-is if already an incident result.

    The targeted one-pass endpoint calls collect_automatic_diagnosis_evidence() which
    returns AutoLoopIncidentResult directly (not AutoLoopCollectorResult).
    This helper safely handles both cases to prevent AttributeError when accessing
    result.incident_results on an AutoLoopIncidentResult object.

    Note:
        AutoLoopIncidentResult does NOT have an incident_results attribute.
        Only AutoLoopCollectorResult has incident_results (a list of dicts).
        The collector's run_automatic_diagnosis_loop_evidence_collection() returns
        AutoLoopCollectorResult, but the convenience wrapper collect_automatic_diagnosis_evidence()
        extracts the single incident result from the list and returns AutoLoopIncidentResult.

    Args:
        result: Either AutoLoopCollectorResult or AutoLoopIncidentResult
        incident_id: The incident ID to look up (unused since result is already the target)

    Returns:
        AutoLoopIncidentResult if found, None otherwise
    """
    # AutoLoopIncidentResult is the direct return type from collect_automatic_diagnosis_evidence
    if hasattr(result, "incident_results"):
        # This is AutoLoopCollectorResult - extract from list
        incident_results = getattr(result, "incident_results", [])
        for item in incident_results:
            if isinstance(item, dict) and item.get("incident_id") == incident_id:
                # Reconstruct AutoLoopIncidentResult from dict
                return AutoLoopIncidentResult(**item)
        return None
    else:
        # This is already AutoLoopIncidentResult
        return result


def _read_request_body(handler: object) -> bytes:
    """Read request body from handler using standard HTTP primitives.

    This function provides compatibility between:
    1. Fakes/tests that provide a direct `.body` attribute
    2. Real HealthUIRequestHandler which uses rfile + Content-Length

    BaseHTTPRequestHandler does not define a `.body` attribute. It exposes
    the request payload via rfile (input stream) and Content-Length header.

    Args:
        handler: HTTP request handler instance (HealthUIRequestHandler or mock)

    Returns:
        Raw request body as bytes, or empty bytes if unavailable
    """
    # Priority 1: Check for explicit .body attribute (for test fakes)
    existing_body = getattr(handler, "body", None)
    if existing_body is not None:
        if isinstance(existing_body, bytes):
            return existing_body
        if isinstance(existing_body, str):
            return existing_body.encode("utf-8")
        try:
            return bytes(existing_body)
        except (TypeError, ValueError):
            return b""

    # Priority 2: Read from rfile using Content-Length (real HTTP handler)
    headers = getattr(handler, "headers", None)
    if headers is None:
        return b""

    raw_content_length = headers.get("Content-Length", "0")
    try:
        content_length = int(raw_content_length or "0")
    except ValueError:
        content_length = 0

    if content_length <= 0:
        return b""

    rfile = getattr(handler, "rfile", None)
    if rfile is None:
        return b""

    data = rfile.read(content_length)
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    return b""


def _parse_request_config(handler: HealthUIRequestHandler) -> AutomaticDiagnosisLoopConfig | None:
    """Parse optional config from request body.

    Uses _positive_int() to validate budget fields, rejecting booleans,
    strings, zero, and negative values in favor of safe defaults.

    Args:
        handler: The HTTP request handler instance

    Returns:
        AutomaticDiagnosisLoopConfig if config fields are present in request body, None otherwise.
    """
    import json

    body = _read_request_body(handler)
    if not body:
        return None

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None

    # Check if any config fields are present
    config_fields = [
        "max_passes_per_incident",
        "max_checks_per_pass",
        "max_incidents_per_run",
        "require_complete_root_cause_before_stop",
    ]
    if not any(field in parsed for field in config_fields):
        return None

    # Build config from request body with semantic validation.
    # _positive_int() rejects booleans, non-integers, zero, and negatives.
    # require_complete_root_cause_before_stop is a boolean for P4c lab-strict mode.
    require_complete = parsed.get("require_complete_root_cause_before_stop")
    if not isinstance(require_complete, bool):
        require_complete = False

    return AutomaticDiagnosisLoopConfig(
        max_incidents_per_run=_positive_int(parsed.get("max_incidents_per_run"), 10),
        max_passes_per_incident=_positive_int(parsed.get("max_passes_per_incident"), 1),
        max_checks_per_pass=_positive_int(parsed.get("max_checks_per_pass"), 5),
        write_stop_path_packets=parsed.get("write_stop_path_packets", True),
        write_ineligible_packets=parsed.get("write_ineligible_packets", False),
        require_complete_root_cause_before_stop=require_complete,
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

    Request body (optional):
        {
            "max_passes_per_incident": 5,  // Override default (1) for lab scenarios
            "max_checks_per_pass": 5,       // Max checks per pass
            "max_incidents_per_run": 10     // Max incidents to process
        }

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

    # Step 3: Parse optional config from request body
    # This allows lab scenarios (like P4c with min_required_passes=2) to override
    # the default max_passes_per_incident=1 budget limit
    config = _parse_request_config(handler)

    # Step 4: Invoke the automatic diagnosis loop collector
    # NOTE: collect_automatic_diagnosis_evidence() returns AutoLoopIncidentResult directly,
    # NOT AutoLoopCollectorResult. The handler must not assume result.incident_results exists.
    try:
        result = collect_automatic_diagnosis_evidence(
            incident_id=incident_id,
            external_analysis_dir=external_analysis_dir,
            config=config,
        )
    except Exception as exc:
        error_class = exc.__class__.__name__
        _logger.exception(
            "Automatic diagnosis loop failed for incident_id=%s error_class=%s",
            incident_id,
            error_class,
        )
        # Return structured JSON error, not empty response
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
    # collect_automatic_diagnosis_evidence returns AutoLoopIncidentResult directly
    if result.skipped:
        response = {
            "schema_version": "1.0",
            "incident_id": incident_id,
            "eligible": result.eligible,
            "eligibility_reason": result.eligibility_reason,
            "skipped": True,
            "skip_reason": result.skip_reason,
        }
        # Include budget diagnostics when available for budget_exhausted cases
        # Use safe serialization to handle both dict and dataclass items
        response["budget_diagnostics"] = _serialize_diagnostic_list(result.budget_diagnostics)
        send_json_response(handler, response, code=200)
        return

    # Success or error with partial results
    # Use safe extraction helper since result is AutoLoopIncidentResult
    incident_result = result

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
            "collector_run_id": None,  # Not available from single-incident result
            "error": incident_result.error,
            "error_class": "collector_incident_error",
            "read_only": True,
            "no_remediation_attempted": True,
        }
        send_json_response(handler, response, code=200)
        return

    # Success
    review_packet_name = None
    if incident_result.review_packet_name:
        review_packet_name = incident_result.review_packet_name

    response = {
        "schema_version": "1.0",
        "incident_id": incident_id,
        "eligible": incident_result.eligible,
        "eligibility_reason": incident_result.eligibility_reason,
        "run_id": incident_result.run_id,
        "collector_run_id": None,  # Not available from single-incident result
        "checks_run": incident_result.checks_run,
        "checks_skipped": incident_result.checks_skipped,
        "checks_rejected": incident_result.checks_rejected,
        "review_packet_name": review_packet_name,
        "loop_summary_status": "completed" if incident_result.run_id else "not_run",
        "automatic_diagnosis_review_available": incident_result.review_packet_name is not None,
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
