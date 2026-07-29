"""Typed scoped scheduler client.

ACT-K9B-HULK-PROMOTION-SCOPED-CLIENT-TYPED-HTTP-SEAM01.

Owns the HTTP transport loop for the active scoped current-run
promotion path. The client consumes only the canonical scoped
types:

* :class:`PromoteAlertSignalsRequest`
* :class:`IncidentPromotionResult` (via ``from_wire_dict``)
* :class:`BoundScopedPromotionResult`
* :class:`ScopedPromotionHttpRequestContext`
* :class:`ScopedPromotionHttpSucceeded` (and the shared
  :class:`ScopedPromotionHttpTransportOutcome` union)

It does NOT import or call any of the legacy snake_case symbols
(``PromotionResponse``, ``PromotionHttpWireResult``, etc.). The
companion AST/source guard in
``tests/unit/test_scoped_legacy_decoder_isolation.py`` verifies
that boundary deterministically.

The HTTP loop handles:

* bounded body reader (``MAX_RESPONSE_BYTES``);
* ``urllib.error.HTTPError`` as a response -- the status code,
  headers, and body are captured into the typed observation;
* malformed JSON / invalid wire schema / legacy snake_case body
  -- all converge on the typed transport variants;
* ``204 No Content`` and ``202 Accepted`` -- distinct typed
  variants for ``may_have_committed=True`` uncertainty;
* timeout / connection-loss / short-read -- post-send transport
  failures with ``may_have_committed=True``.

No credentials, no response body, no incident evidence is ever
logged. The bounded ``response_body_sha256`` is recorded for
operator correlation only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from ..collect.promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpObservation,
    PromotionHttpRejected,
    PromotionHttpResponseTruncated,
    PromotionHttpTransportFailureBeforeSend,
    PromotionHttpTransportReasonCode,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from ..collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpSucceeded,
    ScopedPromotionHttpTransportOutcome,
)
from ..incident_alert_promotion_binding import BoundScopedPromotionResult
from ..incident_alert_promotion_contract import (
    IncidentPromotionResult,
    PromoteAlertSignalsRequest,
    PromotionScopeError,
)

MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MiB bounded body cap

_logger = logging.getLogger(__name__)


class ScopedSchedulerBackendConfigError(Exception):
    """Raised when the scheduler backend URL or token is not configured."""


def _compute_sha256(body: bytes | None) -> str | None:
    """Return SHA-256 over a bounded body, or ``None`` if empty."""
    if not body:
        return None
    return hashlib.sha256(body).hexdigest()


def _build_request_url(base_url: str) -> str:
    """Build the scoped URL."""
    return f"{base_url.rstrip('/')}/api/internal/incidents/promote-alert-signals"


def _build_request_body(
    context: ScopedPromotionHttpRequestContext,
) -> bytes:
    """Build the canonical camelCase wire request body."""
    request = PromoteAlertSignalsRequest(
        run_id=context.run_id,
        source_identity=context.source_identity,
        signal_ids=tuple(context.signal_ids),
    )
    wire: Mapping[str, object] = request.to_wire_dict()
    return json.dumps(wire).encode("utf-8")


class ScopedSchedulerClient:
    """Typed HTTP client for the canonical scoped current-run path."""

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._token = token

    def _require_backend_url(self) -> str:
        backend_url = (self._base_url or "").strip()
        if not backend_url:
            raise ScopedSchedulerBackendConfigError(
                "scoped scheduler backend URL is not configured"
            )
        return backend_url

    def promote_alert_signals_scoped(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        timeout: float = 30.0,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Submit the explicit current-run promotion scope.

        Returns the closed
        :data:`ScopedPromotionHttpTransportOutcome` union so the
        dispatcher can drive the bounded
        :class:`PromotionOutcome` projection without re-parsing
        the response body.
        """
        try:
            base_url = self._require_backend_url()
        except ScopedSchedulerBackendConfigError:
            observation = PromotionHttpObservation(
                request_id=context.request_id,
                request_transmission=RequestTransmissionState.NOT_STARTED,
                status_code=None,
                content_type=None,
                declared_content_length=None,
                response_byte_count=0,
                response_body_sha256=None,
                decoding_stage=PromotionResponseDecodingStage.NOT_ATTEMPTED,
                elapsed_milliseconds=0,
            )
            return PromotionHttpTransportFailureBeforeSend(
                observation=observation,
                reason_code=PromotionHttpTransportReasonCode.HTTP_FAILURE_BEFORE_SEND,
            )

        url = _build_request_url(base_url)
        data = _build_request_body(context)
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        request = urllib.request.Request(
            url, data=data, headers=headers, method="POST"
        )

        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return self._consume_success_response(
                    context=context,
                    response=resp,
                    elapsed_milliseconds=elapsed_ms,
                )
        except urllib.error.HTTPError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return self._consume_http_error_response(
                context=context,
                error=exc,
                elapsed_milliseconds=elapsed_ms,
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            elapsed_ms = int((time.monotonic() - start) * 1000)
            observation = PromotionHttpObservation(
                request_id=context.request_id,
                request_transmission=RequestTransmissionState.NOT_STARTED,
                status_code=None,
                content_type=None,
                declared_content_length=None,
                response_byte_count=0,
                response_body_sha256=None,
                decoding_stage=PromotionResponseDecodingStage.NOT_ATTEMPTED,
                elapsed_milliseconds=elapsed_ms,
            )
            return PromotionHttpTransportFailureBeforeSend(
                observation=observation,
                reason_code=PromotionHttpTransportReasonCode.HTTP_FAILURE_BEFORE_SEND,
            )

    def _consume_success_response(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        response: Any,
        elapsed_milliseconds: int,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Consume a 2xx response and dispatch to the typed variants."""
        status_code = getattr(response, "status", None) or getattr(
            response, "code", None
        )
        content_type = response.headers.get("Content-Type") if response.headers else None
        declared_length = response.headers.get("Content-Length") if response.headers else None
        declared_length_int: int | None
        try:
            declared_length_int = (
                int(declared_length) if declared_length is not None else None
            )
        except (TypeError, ValueError):
            declared_length_int = None

        body = self._read_bounded_body(response)
        if body is None:
            return PromotionHttpResponseTruncated(
                observation=PromotionHttpObservation(
                    request_id=context.request_id,
                    request_transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=content_type,
                    declared_content_length=declared_length_int,
                    response_byte_count=MAX_RESPONSE_BYTES,
                    response_body_sha256=None,
                    decoding_stage=(
                        PromotionResponseDecodingStage.JSON_DECODE
                    ),
                    elapsed_milliseconds=elapsed_milliseconds,
                )
            )

        return self._decode_body(
            context=context,
            body=body,
            status_code=status_code,
            content_type=content_type,
            declared_content_length=declared_length_int,
            elapsed_milliseconds=elapsed_milliseconds,
        )

    def _consume_http_error_response(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        error: urllib.error.HTTPError,
        elapsed_milliseconds: int,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Treat ``HTTPError`` as a response (status, headers, body)."""
        status_code = error.code
        content_type = error.headers.get("Content-Type") if error.headers else None
        declared_length = error.headers.get("Content-Length") if error.headers else None
        try:
            declared_length_int = (
                int(declared_length) if declared_length is not None else None
            )
        except (TypeError, ValueError):
            declared_length_int = None

        body = self._read_bounded_body(error)
        if body is None:
            return PromotionHttpResponseTruncated(
                observation=PromotionHttpObservation(
                    request_id=context.request_id,
                    request_transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=content_type,
                    declared_content_length=declared_length_int,
                    response_byte_count=MAX_RESPONSE_BYTES,
                    response_body_sha256=None,
                    decoding_stage=PromotionResponseDecodingStage.JSON_DECODE,
                    elapsed_milliseconds=elapsed_milliseconds,
                )
            )

        observation = PromotionHttpObservation(
            request_id=context.request_id,
            request_transmission=RequestTransmissionState.RESPONSE_COMPLETED,
            status_code=status_code,
            content_type=content_type,
            declared_content_length=declared_length_int,
            response_byte_count=len(body),
            response_body_sha256=_compute_sha256(body),
            decoding_stage=PromotionResponseDecodingStage.COMPLETED,
            elapsed_milliseconds=elapsed_milliseconds,
        )
        return PromotionHttpRejected(
            observation=observation,
            body_excerpt=_safe_excerpt(body),
        )

    def _read_bounded_body(self, response: Any) -> bytes | None:
        """Read up to ``MAX_RESPONSE_BYTES`` from the response body.

        Returns ``None`` when the body exceeds the cap (truncated).
        """
        try:
            chunk: bytes = response.read(MAX_RESPONSE_BYTES + 1)
        except (TimeoutError, ConnectionError, OSError):
            return None
        return chunk[:MAX_RESPONSE_BYTES]

    def _decode_body(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        body: bytes,
        status_code: int | None,
        content_type: str | None,
        declared_content_length: int | None,
        elapsed_milliseconds: int,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Decode the body through the canonical typed pipeline."""
        sha = _compute_sha256(body)
        if not body:
            if status_code == 202:
                return PromotionHttpAccepted(
                    observation=PromotionHttpObservation(
                        request_id=context.request_id,
                        request_transmission=(
                            RequestTransmissionState.RESPONSE_COMPLETED
                        ),
                        status_code=status_code,
                        content_type=content_type,
                        declared_content_length=declared_content_length,
                        response_byte_count=0,
                        response_body_sha256=None,
                        decoding_stage=PromotionResponseDecodingStage.EMPTY_BODY,
                        elapsed_milliseconds=elapsed_milliseconds,
                    )
                )
            if status_code == 204:
                return PromotionHttpNoContent(
                    observation=PromotionHttpObservation(
                        request_id=context.request_id,
                        request_transmission=(
                            RequestTransmissionState.RESPONSE_COMPLETED
                        ),
                        status_code=status_code,
                        content_type=content_type,
                        declared_content_length=declared_content_length,
                        response_byte_count=0,
                        response_body_sha256=None,
                        decoding_stage=PromotionResponseDecodingStage.EMPTY_BODY,
                        elapsed_milliseconds=elapsed_milliseconds,
                    )
                )
            # Non-empty-status but empty body -- typed empty-body
            # uncertainty rather than false authoritative zero.
            return PromotionHttpInvalidJson(
                observation=PromotionHttpObservation(
                    request_id=context.request_id,
                    request_transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=content_type,
                    declared_content_length=declared_content_length,
                    response_byte_count=0,
                    response_body_sha256=None,
                    decoding_stage=PromotionResponseDecodingStage.EMPTY_BODY,
                    elapsed_milliseconds=elapsed_milliseconds,
                ),
                body_excerpt="",
            )
        # Body is non-empty -- attempt JSON decode.
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            observation = PromotionHttpObservation(
                request_id=context.request_id,
                request_transmission=(
                    RequestTransmissionState.RESPONSE_COMPLETED
                ),
                status_code=status_code,
                content_type=content_type,
                declared_content_length=declared_content_length,
                response_byte_count=len(body),
                response_body_sha256=sha,
                decoding_stage=PromotionResponseDecodingStage.JSON_DECODE,
                elapsed_milliseconds=elapsed_milliseconds,
            )
            return PromotionHttpInvalidJson(
                observation=observation,
                body_excerpt=_safe_excerpt(body),
            )

        if not isinstance(payload, Mapping):
            observation = PromotionHttpObservation(
                request_id=context.request_id,
                request_transmission=(
                    RequestTransmissionState.RESPONSE_COMPLETED
                ),
                status_code=status_code,
                content_type=content_type,
                declared_content_length=declared_content_length,
                response_byte_count=len(body),
                response_body_sha256=sha,
                decoding_stage=PromotionResponseDecodingStage.WIRE_SCHEMA,
                elapsed_milliseconds=elapsed_milliseconds,
            )
            return PromotionHttpInvalidSchema(
                observation=observation,
                schema_error=(
                    f"promotion response must be a JSON object; got "
                    f"{type(payload).__name__}"
                ),
            )

        try:
            result = IncidentPromotionResult.from_wire_dict(payload)
        except PromotionScopeError as exc:
            observation = PromotionHttpObservation(
                request_id=context.request_id,
                request_transmission=(
                    RequestTransmissionState.RESPONSE_COMPLETED
                ),
                status_code=status_code,
                content_type=content_type,
                declared_content_length=declared_content_length,
                response_byte_count=len(body),
                response_body_sha256=sha,
                decoding_stage=PromotionResponseDecodingStage.WIRE_SCHEMA,
                elapsed_milliseconds=elapsed_milliseconds,
            )
            return PromotionHttpInvalidSchema(
                observation=observation,
                schema_error=str(exc),
            )

        request = PromoteAlertSignalsRequest(
            run_id=context.run_id,
            source_identity=context.source_identity,
            signal_ids=tuple(context.signal_ids),
        )
        try:
            bound = BoundScopedPromotionResult(request=request, result=result)
        except PromotionScopeError as exc:
            observation = PromotionHttpObservation(
                request_id=context.request_id,
                request_transmission=(
                    RequestTransmissionState.RESPONSE_COMPLETED
                ),
                status_code=status_code,
                content_type=content_type,
                declared_content_length=declared_content_length,
                response_byte_count=len(body),
                response_body_sha256=sha,
                decoding_stage=PromotionResponseDecodingStage.WIRE_SCHEMA,
                elapsed_milliseconds=elapsed_milliseconds,
            )
            return PromotionHttpInvalidSchema(
                observation=observation,
                schema_error=f"binding failed: {exc}",
            )

        observation = PromotionHttpObservation(
            request_id=context.request_id,
            request_transmission=RequestTransmissionState.RESPONSE_COMPLETED,
            status_code=status_code,
            content_type=content_type,
            declared_content_length=declared_content_length,
            response_byte_count=len(body),
            response_body_sha256=sha,
            decoding_stage=PromotionResponseDecodingStage.COMPLETED,
            elapsed_milliseconds=elapsed_milliseconds,
        )
        return ScopedPromotionHttpSucceeded(observation=observation, bound=bound)


def _safe_excerpt(body: bytes, *, limit: int = 256) -> str:
    """Return a bounded, error-safe textual excerpt of a response body."""
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return ""
    return text[:limit]


__all__ = [
    "MAX_RESPONSE_BYTES",
    "ScopedSchedulerBackendConfigError",
    "ScopedSchedulerClient",
]
