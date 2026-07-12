"""Backend-mode lifecycle writer for the automatic-diagnosis authority seam.

This module owns the ``backend`` half of the lifecycle dispatch split:
it builds the canonical lifecycle wire-request, performs the
authenticated HTTP POST against the configured backend internal API,
and translates the response into a typed :class:`LifecycleWriteOutcome`.

The seam module (:mod:`incident_diagnosis_authority_seam`) is the only
public entry point; callers MUST NOT import from this file directly.

Failure translation is exhaustive:

* 200 + ``applied=true`` → ``LifecycleWriteApplied``
* 200 + ``applied=false`` → ``LifecycleWriteRejected`` (with the bounded code)
* 404 → ``LifecycleWriteFailed`` (``incident_not_found``) so the
  scheduler never collapses it to the eligibility-level reason.
* 409 (conflict) → ``LifecycleWriteRejected`` (``transition_replay_mismatch``).
* 4xx (other) → ``LifecycleWriteRejected``
* 5xx → ``LifecycleWriteFailed`` (``backend_error``)
* 1xx / 2xx-other / 3xx → ``LifecycleWriteFailed`` (``transport_error``)

Transport errors (timeout, URL error, OS error) NEVER fall back to the
local store; the scheduler must observe the failure.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-INCIDENT-AUTHORITY-SEAM01
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from typing import Any

from .incident_diagnosis_authority_seam import build_lifecycle_request
from .incident_diagnosis_authority_seam_types import (
    LifecycleTransition,
    LifecycleWriteApplied,
    LifecycleWriteFailed,
    LifecycleWriteOutcome,
    LifecycleWriteRejected,
)
from .incident_diagnosis_dispatch_contracts import (
    ENV_BACKEND_URL,
    ENV_INTERNAL_API_TOKEN,
)


def _encode_lifecycle_body(request: Any) -> bytes:
    import json

    return json.dumps(request.to_dict()).encode("utf-8")


def _translate_lifecycle_response(
    *,
    transition: LifecycleTransition,
    incident_id: str,
    http_status: int,
    body_bytes: bytes,
) -> LifecycleWriteOutcome:
    """Translate a backend HTTP response into a typed write outcome.

    The translation is exhaustive over the bounded contract; see the
    module docstring for the full mapping table.
    """
    import json

    decoded: dict[str, Any] | None = None
    if body_bytes:
        try:
            parsed = json.loads(body_bytes.decode("utf-8"))
            if isinstance(parsed, dict):
                decoded = parsed
        except (json.JSONDecodeError, UnicodeDecodeError):
            decoded = None

    if http_status == 200 and decoded is not None:
        if bool(decoded.get("applied", False)) is True:
            return LifecycleWriteApplied(
                transition=transition,
                incident_id=incident_id,
                idempotent_replay=bool(decoded.get("idempotentReplay", False)),
                http_status=http_status,
                detail=(
                    str(decoded.get("detail"))
                    if decoded.get("detail") is not None
                    else "applied via backend"
                ),
            )
        # 200 with explicit applied=false: treat as rejected so the
        # scheduler does not assume success.
        return LifecycleWriteRejected(
            transition=transition,
            incident_id=incident_id,
            reason_code=str(decoded.get("reasonCode") or "backend_rejected"),
            http_status=http_status,
            detail=(
                str(decoded.get("message"))
                if decoded.get("message") is not None
                else None
            ),
        )

    if http_status == 404:
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="incident_not_found",
            http_status=http_status,
            detail="backend reported 404 for the incident",
        )

    if 400 <= http_status < 500:
        reason_code = "request_rejected"
        detail: str | None = None
        if decoded is not None:
            reason_code = str(
                decoded.get("reasonCode")
                or decoded.get("errorCode")
                or "request_rejected"
            )
            detail = (
                str(decoded.get("message"))
                if decoded.get("message") is not None
                else None
            )
        return LifecycleWriteRejected(
            transition=transition,
            incident_id=incident_id,
            reason_code=reason_code,
            http_status=http_status,
            detail=detail,
        )

    if http_status >= 500:
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="backend_error",
            http_status=http_status,
            detail=(
                str(decoded.get("message"))
                if decoded is not None and decoded.get("message") is not None
                else None
            ),
        )

    # 1xx / 2xx other than 200 / 3xx: treat as transport anomaly.
    return LifecycleWriteFailed(
        transition=transition,
        incident_id=incident_id,
        reason_code="transport_error",
        http_status=http_status,
        detail=f"unexpected HTTP status {http_status}",
    )


def _record_lifecycle_backend(
    *,
    transition: LifecycleTransition,
    incident_id: str,
    run_id: str,
    collector_run_id: str,
    payload: dict[str, Any],
) -> LifecycleWriteOutcome:
    """POST a lifecycle transition to the backend internal API.

    Returns a typed :class:`LifecycleWriteOutcome`. NEVER falls back
    to the local store on failure.
    """
    backend_url = os.environ.get(ENV_BACKEND_URL, "").rstrip("/")
    token = os.environ.get(ENV_INTERNAL_API_TOKEN)
    if not backend_url:
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="backend_url_not_configured",
            detail="K9B_BACKEND_INTERNAL_URL is not set in scheduler env",
        )
    if not token:
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="missing_internal_token",
            detail="K9B_INTERNAL_API_TOKEN is not set in scheduler env",
        )

    request = build_lifecycle_request(
        incident_id=incident_id,
        transition=transition,
        collector_run_id=collector_run_id,
        diagnosis_run_id=run_id,
        payload=payload,
    )
    url = f"{backend_url}/api/internal/incidents/diagnosis-loop-transition"
    body = _encode_lifecycle_body(request)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            status = int(resp.status)
            raw = resp.read()
            return _translate_lifecycle_response(
                transition=transition,
                incident_id=incident_id,
                http_status=status,
                body_bytes=raw,
            )
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:  # noqa: BLE001 - defensive
            raw = b""
        return _translate_lifecycle_response(
            transition=transition,
            incident_id=incident_id,
            http_status=int(exc.code),
            body_bytes=raw,
        )
    except TimeoutError:
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="transport_error",
            detail="request to backend timed out",
            exception_type="TimeoutError",
        )
    except urllib.error.URLError as exc:
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="transport_error",
            detail=f"backend URL error: {exc.reason!r}",
            exception_type=(
                type(exc.reason).__name__
                if getattr(exc, "reason", None) is not None
                else "URLError"
            ),
        )
    except OSError as exc:
        return LifecycleWriteFailed(
            transition=transition,
            incident_id=incident_id,
            reason_code="transport_error",
            detail=f"backend connection error: {exc}",
            exception_type=type(exc).__name__,
        )
