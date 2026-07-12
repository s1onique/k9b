"""Canonical backend incident-detail lookup function.

This module hosts the **single** function through which all
automatic-diagnosis backend incident reads must pass:

    lookup_backend_incident(client, incident_id) -> BackendIncidentLookupOutcome

The function owns every step of the backend read pipeline:

1. URL / client invocation.
2. HTTP status classification.
3. JSON decoding.
4. API envelope validation (``payload_type`` + ``schema_version``).
5. Aggregate extraction.
6. Domain deserialization via :class:`Incident.from_dict`.
7. Requested-versus-returned identity validation.
8. Construction of the typed outcome.

**Hard invariants** enforced here:

* ``BackendIncidentNotFound`` is constructed **only** when the HTTP
  status is ``404``. No empty body, no parser failure, no schema
  mismatch, no identity mismatch, no exception handler can produce
  ``BackendIncidentNotFound``.
* ``BackendIncidentLookupFailed`` is constructed for every other
  failure mode with the precise :class:`BackendIncidentLookupFailureCode`.
* ``BackendIncidentFound`` is constructed only after a successful
  ``Incident.from_dict`` call whose ``incident_id`` equals the requested
  branded ``IncidentId``.

Suggested by: ACT-K9B-HULK-AUTO-DIAG-BACKEND-DETAIL-OUTCOME01
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from k8s_diag_agent.domain.incident_lifecycle import IncidentId

from .incident_diagnosis_backend_detail_outcomes import (
    BackendIncidentFound,
    BackendIncidentLookupFailed,
    BackendIncidentLookupFailureCode,
    BackendIncidentLookupOutcome,
    BackendIncidentLookupSource,
    BackendIncidentNotFound,
)
from .incident_diagnosis_backend_detail_parser import (
    SUPPORTED_PAYLOAD_TYPE,
    BackendIncidentDeserializationError,
    BackendIncidentDetailParseError,
    BackendIncidentInvalidPayloadError,
    BackendIncidentUnsupportedSchemaError,
    parse_internal_incident_detail_payload,
)

__all__ = [
    "BackendIncidentHttpResponse",
    "BackendIncidentClient",
    "BackendIncidentTransportError",
    "HttpIncidentBackendClient",
    "lookup_backend_incident",
]


_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed HTTP response + client protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BackendIncidentHttpResponse:
    """Minimal typed HTTP response used by the canonical lookup.

    The lookup function consumes the raw ``body`` bytes; it never reads
    headers, and the response object deliberately omits them so
    authorization tokens cannot leak through logging frameworks.
    """

    http_status: int
    body: bytes


class BackendIncidentClient(Protocol):
    """Protocol for the backend incident-detail HTTP client.

    Implementations MUST:

    * raise :class:`BackendIncidentTransportError` for transport-level
      failures (DNS, connection refused, timeout, generic network errors);
    * return a :class:`BackendIncidentHttpResponse` for every HTTP response
      (including 4xx / 5xx) so the lookup function can perform its own
      status classification.
    """

    def fetch_incident(
        self,
        incident_id: IncidentId,
        *,
        timeout: float = 30.0,
    ) -> BackendIncidentHttpResponse: ...


class BackendIncidentTransportError(Exception):
    """Transport-level failure raised by the HTTP client.

    The lookup function translates this into
    :attr:`BackendIncidentLookupFailureCode.TRANSPORT_ERROR`.
    """

    def __init__(self, message: str, *, exception_type: str | None = None) -> None:
        super().__init__(message)
        self.exception_type = exception_type


# ---------------------------------------------------------------------------
# Concrete HTTP client (urllib-backed)
# ---------------------------------------------------------------------------


class HttpIncidentBackendClient:
    """``urllib.request``-backed implementation of :class:`BackendIncidentClient`.

    The class is intentionally tiny: it returns the typed response and
    raises :class:`BackendIncidentTransportError` for transport failures.
    It does NOT swallow status codes as ``None`` and does NOT catch
    arbitrary exceptions to convert them into absence.
    """

    def __init__(self, base_url: str, token: str | None = None) -> None:
        base_url = (base_url or "").rstrip("/")
        if not base_url:
            raise BackendIncidentTransportError(
                "backend internal API URL is not configured",
                exception_type="MissingBackendUrl",
            )
        self._base_url = base_url
        self._token = token

    def fetch_incident(
        self,
        incident_id: IncidentId,
        *,
        timeout: float = 30.0,
    ) -> BackendIncidentHttpResponse:
        url = f"{self._base_url}/api/internal/incidents/{incident_id}"
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # ``resp.read()`` returns bytes; cap to a sane upper bound
                # so a runaway backend cannot OOM the scheduler. 1 MiB
                # is far above any real incident detail payload.
                raw = resp.read(1024 * 1024 + 1)
                truncated = len(raw) > 1024 * 1024
                if truncated:
                    raw = raw[: 1024 * 1024]
                return BackendIncidentHttpResponse(
                    http_status=int(resp.status),
                    body=raw,
                )
        except urllib.error.HTTPError as exc:
            # The HTTP layer is reachable; we have a real status code.
            # Return the response (with body) so the lookup function
            # can classify the status itself. NEVER collapse this to None.
            try:
                raw = exc.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raw = raw[: 1024 * 1024]
            except Exception:  # pragma: no cover - defensive
                raw = b""
            return BackendIncidentHttpResponse(
                http_status=int(exc.code),
                body=raw,
            )
        except TimeoutError as exc:
            raise BackendIncidentTransportError(
                "request to backend timed out",
                exception_type="TimeoutError",
            ) from exc
        except urllib.error.URLError as exc:
            raise BackendIncidentTransportError(
                f"backend URL error: {exc.reason!r}",
                exception_type=type(exc.reason).__name__
                if hasattr(exc, "reason")
                else "URLError",
            ) from exc
        except OSError as exc:
            raise BackendIncidentTransportError(
                f"backend connection error: {exc}",
                exception_type=type(exc).__name__,
            ) from exc


# ---------------------------------------------------------------------------
# Canonical lookup function
# ---------------------------------------------------------------------------


def _failure_for_status(
    status_code: int,
    *,
    requested_incident_id: IncidentId,
    exception_type: str | None = None,
    detail: str | None = None,
) -> BackendIncidentLookupFailed:
    """Map an HTTP status code to the canonical failure variant."""
    if status_code == 401:
        code = BackendIncidentLookupFailureCode.UNAUTHORIZED
    elif status_code == 403:
        code = BackendIncidentLookupFailureCode.FORBIDDEN
    elif 400 <= status_code < 500:
        code = BackendIncidentLookupFailureCode.HTTP_CLIENT_ERROR
    elif status_code >= 500:
        code = BackendIncidentLookupFailureCode.BACKEND_ERROR
    else:
        # Treat 1xx / 2xx / 3xx reaching this branch as a transport error.
        code = BackendIncidentLookupFailureCode.TRANSPORT_ERROR
    return BackendIncidentLookupFailed(
        requested_incident_id=requested_incident_id,
        failure_code=code,
        detail=detail or f"backend returned HTTP {status_code}",
        http_status=status_code,
        exception_type=exception_type,
    )


def _empty_body_failure(
    requested_incident_id: IncidentId,
) -> BackendIncidentLookupFailed:
    """Build the precise failure for an empty 200 response body."""
    return BackendIncidentLookupFailed(
        requested_incident_id=requested_incident_id,
        failure_code=BackendIncidentLookupFailureCode.INVALID_JSON,
        detail="backend returned HTTP 200 with an empty response body",
        http_status=200,
    )


def _json_failure(
    requested_incident_id: IncidentId,
    *,
    http_status: int,
    exception: BaseException,
) -> BackendIncidentLookupFailed:
    """Build the precise failure for a JSON decode error."""
    return BackendIncidentLookupFailed(
        requested_incident_id=requested_incident_id,
        failure_code=BackendIncidentLookupFailureCode.INVALID_JSON,
        detail=f"backend returned HTTP {http_status} with non-JSON body: {exception}",
        http_status=http_status,
        exception_type=type(exception).__name__,
    )


def lookup_backend_incident(
    client: BackendIncidentClient,
    incident_id: IncidentId,
    *,
    timeout: float = 30.0,
) -> BackendIncidentLookupOutcome:
    """Canonical backend incident-detail lookup.

    Args:
        client: A :class:`BackendIncidentClient` implementation that owns
            the HTTP transport. Tests supply a fake client; production
            code uses :class:`HttpIncidentBackendClient`.
        incident_id: The branded :class:`IncidentId` being looked up.
        timeout: HTTP timeout in seconds, forwarded to ``client``.

    Returns:
        A :class:`BackendIncidentLookupOutcome`. The caller MUST dispatch
        on the three variants explicitly; generic truthiness on the
        outcome is forbidden by the static verifier.

    Raises:
        Nothing: every failure mode is encoded in the returned outcome.
    """
    try:
        response = client.fetch_incident(incident_id, timeout=timeout)
    except BackendIncidentTransportError as exc:
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.TRANSPORT_ERROR,
            detail=str(exc),
            exception_type=exc.exception_type,
        )
    except Exception as exc:  # pragma: no cover - defensive boundary
        # Defensive: a client that raises an unexpected exception must
        # not become ``BackendIncidentNotFound``.
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.TRANSPORT_ERROR,
            detail=f"unexpected client error: {exc}",
            exception_type=type(exc).__name__,
        )

    # 1. Status classification. 404 is the ONLY path to BackendIncidentNotFound.
    if response.http_status == 404:
        return BackendIncidentNotFound(
            requested_incident_id=incident_id,
            source=BackendIncidentLookupSource.BACKEND_API,
            http_status=404,
        )
    if response.http_status != 200:
        return _failure_for_status(
            response.http_status,
            requested_incident_id=incident_id,
        )

    # 2. Empty body.
    if not response.body:
        return _empty_body_failure(incident_id)

    # 3. JSON decoding.
    try:
        decoded = json.loads(response.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _json_failure(
            incident_id, http_status=response.http_status, exception=exc
        )

    # 4. Envelope validation.
    try:
        parsed = parse_internal_incident_detail_payload(
            decoded, requested_incident_id=incident_id
        )
    except BackendIncidentInvalidPayloadError as exc:
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
            detail=str(exc),
            http_status=response.http_status,
            exception_type=type(exc).__name__,
        )
    except BackendIncidentUnsupportedSchemaError as exc:
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.UNSUPPORTED_SCHEMA,
            detail=str(exc),
            http_status=response.http_status,
            payload_type=getattr(exc, "_payload_type", None) or SUPPORTED_PAYLOAD_TYPE,
            exception_type=type(exc).__name__,
        )
    except BackendIncidentDetailParseError as exc:
        # Catch-all for other parser failures raised in this module.
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.INVALID_PAYLOAD,
            detail=str(exc),
            http_status=response.http_status,
            exception_type=type(exc).__name__,
        )

    # 5. Domain deserialization. The aggregate has passed envelope
    # validation, but ``Incident.from_dict`` may still raise ``ValueError``
    # (shape) or ``KeyError`` (missing field). Both are translated into
    # DESERIALIZATION_FAILED.
    try:
        from .incident_lifecycle import Incident
    except ImportError as exc:  # pragma: no cover - import-time guard
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED,
            detail=f"failed to import Incident model: {exc}",
            http_status=response.http_status,
            payload_schema_version=parsed.schema_version,
            payload_type=parsed.payload_type,
            exception_type=type(exc).__name__,
        )

    try:
        incident = Incident.from_dict(parsed.incident)
    except BackendIncidentDeserializationError as exc:
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED,
            detail=str(exc),
            http_status=response.http_status,
            payload_schema_version=parsed.schema_version,
            payload_type=parsed.payload_type,
            exception_type=type(exc).__name__,
        )
    except (ValueError, KeyError, TypeError) as exc:
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.DESERIALIZATION_FAILED,
            detail=f"failed to deserialize incident aggregate: {exc}",
            http_status=response.http_status,
            payload_schema_version=parsed.schema_version,
            payload_type=parsed.payload_type,
            exception_type=type(exc).__name__,
        )

    # 6. Identity validation. Compare against the canonical ``IncidentId``.
    # ``incident.incident_id`` is a plain ``str`` at the boundary, so we
    # coerce both sides via ``str()`` for the comparison itself.
    returned_id = str(getattr(incident, "incident_id", "") or "")
    if returned_id != str(incident_id):
        return BackendIncidentLookupFailed(
            requested_incident_id=incident_id,
            failure_code=BackendIncidentLookupFailureCode.IDENTITY_MISMATCH,
            detail=(
                "backend returned incident_id "
                f"{returned_id!r} but the lookup was for {str(incident_id)!r}"
            ),
            http_status=response.http_status,
            payload_schema_version=parsed.schema_version,
            payload_type=parsed.payload_type,
        )

    # 7. Success.
    return BackendIncidentFound(
        requested_incident_id=incident_id,
        incident=incident,
        source=BackendIncidentLookupSource.BACKEND_API,
        http_status=response.http_status,
        payload_schema_version=parsed.schema_version,
        payload_type=parsed.payload_type,
    )
