"""Internal API handler for the diagnosis-loop lifecycle transition endpoint.

The handler applies a bounded diagnosis-loop lifecycle transition
(``started`` / ``failed`` / ``completed``) to the **backend-owned**
incident store. The scheduler calls this endpoint over the existing
internal-API bearer-token channel instead of writing the local
``IncidentStore`` directly when running in ``backend-api`` mode.

The atomic, idempotent apply-and-record critical section lives in
:mod:`server_incident_diagnosis_lifecycle_idempotency`; this module is
the thin HTTP boundary: auth, request parsing, bounded validation, and
response shaping.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from .server_incident_diagnosis_lifecycle_idempotency import (
    apply_transition_idempotently,
)
from .server_incident_internal_auth import _validate_internal_token

_logger = logging.getLogger(__name__)

# Lifecycle request/response schema version. Must match the
# ``LIFECYCLE_SCHEMA_VERSION`` value in
# ``incident_diagnosis_authority_seam``. Requests carrying a different
# schema version are rejected with HTTP 400 (unsupported request
# schema) and a bounded validation message; this contract is aligned
# with the scheduler-side client translation and the endpoint tests.
LIFECYCLE_SCHEMA_VERSION: int = 1

# Supported transition values. Keep this list in lock-step with the
# ``LifecycleTransition`` enum on the scheduler side.
SUPPORTED_TRANSITIONS: frozenset[str] = frozenset({
    "started",
    "failed",
    "completed",
})


def _send_json(handler: Any, payload: dict[str, Any], status_code: int) -> None:
    """Emit a JSON response without leaking request bodies or auth tokens."""
    handler._send_json(payload, status_code)


def _read_request_body(handler: Any) -> dict[str, Any] | None:
    """Parse the JSON request body; return None on malformed input."""
    try:
        length = int(handler.headers.get("Content-Length", 0))
    except (TypeError, ValueError):
        _send_json(
            handler,
            {"error": "Bad Request", "message": "missing Content-Length"},
            400,
        )
        return None
    if length < 0:
        _send_json(
            handler,
            {"error": "Bad Request", "message": "negative Content-Length"},
            400,
        )
        return None
    try:
        raw = handler.rfile.read(length) if length > 0 else b""
    except OSError as exc:
        _send_json(
            handler,
            {"error": "Bad Request", "message": f"failed to read body: {exc}"},
            400,
        )
        return None
    if not raw:
        _send_json(
            handler,
            {"error": "Bad Request", "message": "empty request body"},
            400,
        )
        return None
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        _send_json(
            handler,
            {
                "error": "Bad Request",
                "message": f"invalid JSON: {exc}",
            },
            400,
        )
        return None
    if not isinstance(decoded, dict):
        _send_json(
            handler,
            {
                "error": "Bad Request",
                "message": "request body must be a JSON object",
            },
            400,
        )
        return None
    return decoded


def _validate_payload(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(normalized, error_message)`` for a parsed request body.

    All field names are intentionally read from the wire-side camelCase
    to keep the contract aligned with the scheduler-side client. The
    server-side types and IDs are branded at the boundary.
    """
    schema_version = data.get("schemaVersion")
    if schema_version != LIFECYCLE_SCHEMA_VERSION:
        return (
            None,
            f"unsupported schemaVersion {schema_version!r}; expected {LIFECYCLE_SCHEMA_VERSION}",
        )
    incident_id = data.get("incidentId")
    if not isinstance(incident_id, str) or not incident_id:
        return (None, "incidentId is required and must be a non-empty string")
    transition = data.get("transition")
    if transition not in SUPPORTED_TRANSITIONS:
        return (
            None,
            f"transition must be one of {sorted(SUPPORTED_TRANSITIONS)}; got {transition!r}",
        )
    collector_run_id = data.get("collectorRunId")
    if not isinstance(collector_run_id, str) or not collector_run_id:
        return (None, "collectorRunId is required and must be a non-empty string")
    diagnosis_run_id = data.get("diagnosisRunId")
    if diagnosis_run_id is not None and not isinstance(diagnosis_run_id, str):
        return (None, "diagnosisRunId must be a string when present")
    if isinstance(diagnosis_run_id, str) and not diagnosis_run_id:
        # An empty string is treated as absent; the canonical key uses None.
        diagnosis_run_id = None
    occurred_at_str = data.get("occurredAt")
    if not isinstance(occurred_at_str, str) or not occurred_at_str:
        return (None, "occurredAt is required and must be an ISO-8601 string")
    payload = data.get("payload")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return (None, "payload must be a JSON object when present")
    try:
        occurred_at = datetime.fromisoformat(occurred_at_str)
    except ValueError:
        return (None, f"occurredAt is not a valid ISO-8601 timestamp: {occurred_at_str!r}")
    if occurred_at.tzinfo is None:
        # Reject naive timestamps; identity is the contract.
        return (None, "occurredAt must include a timezone offset")

    normalized = {
        "schemaVersion": int(schema_version),
        "incidentId": str(incident_id),
        "transition": str(transition),
        "collectorRunId": str(collector_run_id),
        "diagnosisRunId": (
            str(diagnosis_run_id) if diagnosis_run_id is not None else None
        ),
        "occurredAt": occurred_at.astimezone(UTC).isoformat(),
        "payload": dict(payload),
    }
    return (normalized, None)


def handle_diagnosis_loop_transition(handler: Any) -> None:
    """Handle POST /api/internal/incidents/diagnosis-loop-transition.

    The endpoint accepts a single bounded request and applies it to the
    backend-owned incident store. Idempotent deliveries collapse to a
    single observable transition; conflicting replays (same key,
    different payload) are rejected with HTTP 409 and a stable reason
    code.
    """
    if not _validate_internal_token(handler):
        _send_json(
            handler,
            {
                "error": "Unauthorized",
                "message": "Valid internal API token required",
            },
            401,
        )
        return

    raw = _read_request_body(handler)
    if raw is None:
        return

    normalized, error_message = _validate_payload(raw)
    if error_message is not None or normalized is None:
        _send_json(
            handler,
            {"error": "Bad Request", "message": error_message or "invalid request"},
            400,
        )
        return

    applied = apply_transition_idempotently(
        transition=normalized["transition"],
        incident_id=normalized["incidentId"],
        collector_run_id=normalized["collectorRunId"],
        diagnosis_run_id=normalized["diagnosisRunId"],
        occurred_at=datetime.fromisoformat(normalized["occurredAt"]),
        payload=normalized["payload"],
    )

    if applied["outcome"] == "incident_not_found":
        _send_json(
            handler,
            {
                "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
                "type": "incident-diagnosis-loop-transition-result",
                "applied": False,
                "reasonCode": "incident_not_found",
                "incidentId": normalized["incidentId"],
                "transition": normalized["transition"],
            },
            404,
        )
        return

    if applied["outcome"] == "replay_mismatch":
        _send_json(
            handler,
            {
                "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
                "type": "incident-diagnosis-loop-transition-result",
                "applied": False,
                "reasonCode": "transition_replay_mismatch",
                "incidentId": normalized["incidentId"],
                "transition": normalized["transition"],
            },
            409,
        )
        return

    if applied["outcome"] == "persistence_failed":
        _send_json(
            handler,
            {
                "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
                "type": "incident-diagnosis-loop-transition-result",
                "applied": False,
                "reasonCode": "persistence_failed",
                "exceptionType": applied.get("exception_type", "Unknown"),
                "incidentId": normalized["incidentId"],
                "transition": normalized["transition"],
            },
            500,
        )
        return

    # applied or idempotent_replay
    _send_json(
        handler,
        {
            "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
            "type": "incident-diagnosis-loop-transition-result",
            "applied": True,
            "idempotentReplay": bool(applied.get("idempotent_replay", False)),
            "incidentId": normalized["incidentId"],
            "transition": normalized["transition"],
        },
        200,
    )


__all__ = [
    "LIFECYCLE_SCHEMA_VERSION",
    "SUPPORTED_TRANSITIONS",
    "handle_diagnosis_loop_transition",
]
