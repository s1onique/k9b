"""Typed scoped scheduler client facade.

ACT-K9B-HULK-PROMOTION-SCOPED-DISPATCH-ACTIVATION-AND-CERTAINTY01.

Public client surface for the canonical scoped current-run
promotion path. The HTTP transport loop is split across focused
modules:

* :mod:`server_incident_internal_scoped_body` -- bounded body-read
  algebra and reason codes.
* :mod:`server_incident_internal_scoped_response` -- JSON decode,
  wire schema parsing, and scoped result binding.

The facade owns only the request dispatch, the header injection
(including the ``X-K9B-Promotion-Request-ID`` correlation header),
the elapsed-time measurement, and the typed outcome assembly.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpObservation,
    PromotionHttpRejected,
    PromotionHttpResponseTruncated,
    PromotionHttpTransportFailureAfterSend,
    PromotionHttpTransportFailureBeforeSend,
    PromotionHttpTransportReasonCode,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpTransportOutcome,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
    ScopedBodyReadComplete,
    ScopedBodyReadFailed,
    ScopedBodyReadLimitExceeded,
    ScopedBodyReadShort,
    read_scoped_body,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_response import (
    ScopedResponseObservation,
    accepted_outcome,
    decode_scoped_body,
    no_content_outcome,
)

_logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-K9B-Promotion-Request-ID"

MISSING_CONFIGURATION_BEFORE_SEND = (
    PromotionHttpTransportReasonCode.HTTP_FAILURE_BEFORE_SEND
)


class ScopedSchedulerBackendConfigError(Exception):
    """Raised when the scheduler backend URL or token is not configured."""


def _require_authenticated_config(
    base_url: str,
    token: str | None,
) -> tuple[str, str]:
    """Require both a backend URL and an internal API token.

    The internal scoped endpoint is authenticated. The active
    scoped path MUST NOT silently send an unauthenticated request;
    a missing URL or token fails before send with a typed config
    error.
    """
    backend_url = (base_url or "").strip()
    if not backend_url:
        raise ScopedSchedulerBackendConfigError(
            "scoped scheduler backend URL is not configured"
        )
    if not token:
        raise ScopedSchedulerBackendConfigError(
            "scoped scheduler internal API token is not configured"
        )
    return backend_url, token


def _declared_content_length(headers: Any) -> int | None:
    raw = headers.get("Content-Length") if headers else None
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _content_type(headers: Any) -> str | None:
    return headers.get("Content-Type") if headers else None


class ScopedSchedulerClient:
    """Typed HTTP client for the canonical scoped current-run path."""

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._base_url = base_url
        self._token = token

    def promote_alert_signals_scoped(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        timeout: float = 30.0,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Submit the canonical scoped promotion scope and return
        the typed transport outcome.

        The canonical request is the single authority; this method
        MUST NOT reconstruct a second ``PromoteAlertSignalsRequest``.
        """
        try:
            base_url, token = _require_authenticated_config(
                self._base_url, self._token
            )
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
                reason_code=MISSING_CONFIGURATION_BEFORE_SEND,
            )

        url = f"{base_url.rstrip('/')}/api/internal/incidents/promote-alert-signals"
        request = urllib.request.Request(
            url,
            data=json.dumps(context.request.to_wire_dict()).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                REQUEST_ID_HEADER: context.request_id,
            },
            method="POST",
        )

        return self._execute(context=context, request=request, timeout=timeout)

    def _execute(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        request: urllib.request.Request,
        timeout: float,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Run the HTTP loop, measure elapsed time over the whole operation,
        and dispatch to typed outcomes."""
        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return self._consume_success(
                    context=context,
                    resp=resp,
                    start=start,
                )
        except urllib.error.HTTPError as exc:
            return self._consume_http_error(
                context=context,
                error=exc,
                start=start,
            )
        except urllib.error.URLError as exc:
            return self._consume_url_error(
                context=context,
                exc=exc,
                start=start,
            )
        except (TimeoutError, ConnectionError, OSError):
            # Without an instrumented transport seam that can
            # prove byte transmission, ``urllib`` cannot confirm
            # whether the request reached the wire. Conservative
            # modeling: commit uncertainty.
            return self._post_send_uncertainty(context=context, start=start)

    def _consume_success(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        resp: Any,
        start: float,
    ) -> ScopedPromotionHttpTransportOutcome:
        status_code = int(getattr(resp, "status", 200))
        content_type = _content_type(getattr(resp, "headers", None))
        declared = _declared_content_length(getattr(resp, "headers", None))
        body_result = read_scoped_body(
            resp, declared_content_length=declared
        )
        elapsed_ms = self._elapsed(start)
        meta = ScopedResponseObservation(
            status_code=status_code,
            content_type=content_type,
            declared_content_length=declared,
            body_sha256=getattr(body_result, "body_sha256", None),
            elapsed_milliseconds=elapsed_ms,
        )
        return self._dispatch_body_outcome(
            context=context,
            status_code=status_code,
            body_result=body_result,
            observation_meta=meta,
        )

    def _consume_http_error(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        error: urllib.error.HTTPError,
        start: float,
    ) -> ScopedPromotionHttpTransportOutcome:
        status_code = error.code
        content_type = _content_type(getattr(error, "headers", None))
        declared = _declared_content_length(getattr(error, "headers", None))
        body_result = read_scoped_body(
            error, declared_content_length=declared
        )
        elapsed_ms = self._elapsed(start)
        sha256 = getattr(body_result, "body_sha256", None)
        # ``HTTPError`` is response-shaped: status, headers, and
        # body are available. We never store body text; only the
        # bounded metadata flows back.
        observation = PromotionHttpObservation(
            request_id=context.request_id,
            request_transmission=RequestTransmissionState.RESPONSE_COMPLETED,
            status_code=status_code,
            content_type=content_type,
            declared_content_length=declared,
            response_byte_count=getattr(body_result, "actual_byte_count", 0),
            response_body_sha256=sha256,
            decoding_stage=PromotionResponseDecodingStage.COMPLETED,
            elapsed_milliseconds=elapsed_ms,
        )
        # Without a validated backend no-commit disposition, every
        # HTTP error is commit-uncertainty until proven otherwise;
        # the dispatcher maps this through ``map_scoped_http_transport_to_promotion_outcome``.
        return PromotionHttpRejected(
            observation=observation,
            body_excerpt="",
        )

    def _consume_url_error(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        exc: Any,
        start: float,
    ) -> ScopedPromotionHttpTransportOutcome:
        # ``urllib.error.URLError`` wraps both DNS / connection
        # failures (before send) and reads past headers (after
        # send). Without an instrumented transport seam we cannot
        # distinguish them; conservatively treat as uncertain
        # post-send because the request body may have been written.
        reason = str(getattr(exc, "reason", "") or "")
        if self._looks_like_before_send(reason):
            return self._before_send_failure(
                context=context,
                start=start,
                reason_code=PromotionHttpTransportReasonCode.HTTP_FAILURE_BEFORE_SEND,
            )
        return self._post_send_uncertainty(context=context, start=start)

    @staticmethod
    def _looks_like_before_send(reason: str) -> bool:
        text = reason.lower()
        return any(
            marker in text
            for marker in (
                "name or service not known",
                "temporary failure in name resolution",
                "nodename nor servname provided",
                "no address associated with hostname",
                "connection refused",
                "actively refused",
                "not configured",
            )
        )

    def _post_send_uncertainty(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        start: float,
    ) -> ScopedPromotionHttpTransportOutcome:
        elapsed_ms = self._elapsed(start)
        observation = PromotionHttpObservation(
            request_id=context.request_id,
            request_transmission=RequestTransmissionState.BODY_SENT,
            status_code=None,
            content_type=None,
            declared_content_length=None,
            response_byte_count=0,
            response_body_sha256=None,
            decoding_stage=PromotionResponseDecodingStage.NOT_ATTEMPTED,
            elapsed_milliseconds=elapsed_ms,
        )
        return PromotionHttpTransportFailureAfterSend(
            observation=observation,
            reason_code=PromotionHttpTransportReasonCode.HTTP_READ_TIMEOUT_AFTER_SEND,
        )

    def _before_send_failure(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        start: float,
        reason_code: PromotionHttpTransportReasonCode,
    ) -> ScopedPromotionHttpTransportOutcome:
        elapsed_ms = self._elapsed(start)
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
            reason_code=reason_code,
        )

    @staticmethod
    def _elapsed(start: float) -> int:
        return int((time.monotonic() - start) * 1000)

    def _dispatch_body_outcome(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        status_code: int,
        body_result: Any,
        observation_meta: ScopedResponseObservation,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Map the body-read result and status code into a typed outcome."""
        if isinstance(body_result, ScopedBodyReadComplete):
            if status_code == 202:
                return accepted_outcome(
                    context=context,
                    observation_meta=observation_meta,
                )
            if status_code == 204:
                return no_content_outcome(
                    context=context,
                    observation_meta=observation_meta,
                )
            if not body_result.received:
                # Non-empty-status but empty body -- typed empty-body
                # uncertainty, NOT aggregate successful zero.
                obs = PromotionHttpObservation(
                    request_id=context.request_id,
                    request_transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=observation_meta.content_type,
                    declared_content_length=observation_meta.declared_content_length,
                    response_byte_count=0,
                    response_body_sha256=None,
                    decoding_stage=(
                        PromotionResponseDecodingStage.EMPTY_BODY
                    ),
                    elapsed_milliseconds=observation_meta.elapsed_milliseconds,
                )
                from k8s_diag_agent.collect.promotion_http_transport import (
                    PromotionHttpInvalidJson,
                )
                return PromotionHttpInvalidJson(
                    observation=obs, body_excerpt=""
                )
            return decode_scoped_body(
                context=context,
                body=body_result.received,
                observation_meta=observation_meta,
            )
        if isinstance(body_result, ScopedBodyReadShort):
            return PromotionHttpResponseTruncated(
                observation=PromotionHttpObservation(
                    request_id=context.request_id,
                    request_transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=observation_meta.content_type,
                    declared_content_length=observation_meta.declared_content_length,
                    response_byte_count=body_result.actual_byte_count,
                    response_body_sha256=body_result.body_sha256,
                    decoding_stage=(
                        PromotionResponseDecodingStage.WIRE_SCHEMA
                    ),
                    elapsed_milliseconds=observation_meta.elapsed_milliseconds,
                )
            )
        if isinstance(body_result, ScopedBodyReadLimitExceeded):
            return PromotionHttpResponseTruncated(
                observation=PromotionHttpObservation(
                    request_id=context.request_id,
                    request_transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=observation_meta.content_type,
                    declared_content_length=observation_meta.declared_content_length,
                    response_byte_count=body_result.actual_byte_count,
                    response_body_sha256=body_result.body_sha256,
                    decoding_stage=(
                        PromotionResponseDecodingStage.WIRE_SCHEMA
                    ),
                    elapsed_milliseconds=observation_meta.elapsed_milliseconds,
                )
            )
        if isinstance(body_result, ScopedBodyReadFailed):
            # Read failure AFTER response headers were received.
            # Without further bytes the request body may have been
            # acknowledged by the backend; model as commit uncertainty.
            return PromotionHttpTransportFailureAfterSend(
                observation=PromotionHttpObservation(
                    request_id=context.request_id,
                    request_transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=observation_meta.content_type,
                    declared_content_length=observation_meta.declared_content_length,
                    response_byte_count=0,
                    response_body_sha256=None,
                    decoding_stage=(
                        PromotionResponseDecodingStage.JSON_DECODE
                    ),
                    elapsed_milliseconds=observation_meta.elapsed_milliseconds,
                ),
                reason_code=PromotionHttpTransportReasonCode.HTTP_READ_TIMEOUT_AFTER_SEND,
            )
        # Defensive: unknown body result -> treat as commit-uncertainty.
        return self._post_send_uncertainty(context=context, start=0.0)


__all__ = [
    "MISSING_CONFIGURATION_BEFORE_SEND",
    "REQUEST_ID_HEADER",
    "ScopedSchedulerBackendConfigError",
    "ScopedSchedulerClient",
]
