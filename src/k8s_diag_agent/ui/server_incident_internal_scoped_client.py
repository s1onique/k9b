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
the elapsed-time measurement, the typed exception classification
(DNS, connection refused, TLS pre-connect, timeout, connection
resets), and the typed outcome assembly.

The active scoped path emits typed scoped variants exclusively:
``ScopedPromotionHttpSucceeded``,
``ScopedPromotionHttpAuthenticationRejected``,
``ScopedPromotionHttpBodyLimitExceeded``,
``ScopedPromotionHttpShortRead``,
``ScopedPromotionHttpReadFailed``,
``ScopedPromotionHttpBeforeSendFailed``,
``ScopedPromotionHttpDispatchUncertain`` plus the generic
``PromotionHttp*`` semantic variants that originate inside the
response decoder (accepted, no-content, invalid-json,
invalid-schema, response-truncated). The legacy
``PromotionHttpTransportFailureBeforeSend`` and
``PromotionHttpTransportFailureAfterSend`` are intentionally NOT
emitted by the active scoped path.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpObservation,
    PromotionHttpRejected,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedBeforeSendFailureReason,
    ScopedDispatchUncertaintyReason,
    ScopedPromotionHttpAuthenticationRejected,
    ScopedPromotionHttpBeforeSendFailed,
    ScopedPromotionHttpBodyLimitExceeded,
    ScopedPromotionHttpDispatchUncertain,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpShortRead,
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


class ScopedSchedulerBackendConfigError(Exception):
    """Raised when the scheduler backend URL or token is not configured."""


class _MonotonicClock:
    """Injected monotonic clock authority.

    The active scoped HTTP path uses one monotonic clock so the
    measured ``elapsed_milliseconds`` reflects the entire
    operation -- HTTP response / body reading, status
    classification, JSON decoding, wire parsing, and bounded
    outcome construction.
    """

    def __call__(self) -> float:
        return time.monotonic()


def _default_clock() -> _MonotonicClock:
    return _MonotonicClock()


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


def _classify_url_error_reason(
    exc: urllib.error.URLError,
) -> ScopedBeforeSendFailureReason | ScopedDispatchUncertaintyReason:
    """Classify a ``URLError`` into a typed before-send or
    dispatch-uncertainty reason.

    Returns :class:`ScopedBeforeSendFailureReason` only when the
    underlying ``OSError`` proves the request could not have been
    transmitted (DNS failure, connection refused, TLS pre-connect).
    Otherwise returns :class:`ScopedDispatchUncertaintyReason` so
    the dispatcher can choose the conservative commit-unknown path.
    """
    # ``urllib.error.URLError`` is itself a subclass of ``OSError``
    # but its ``reason`` attribute carries the underlying low-level
    # exception -- ``socket.gaierror`` for DNS, ``ConnectionRefusedError``
    # for pre-connect refusal, ``ssl.SSLError`` for TLS pre-connect.
    # Walk the chain through ``reason`` attributes until we find a
    # more specific ``OSError`` subclass.
    underlying: BaseException | None = exc
    while underlying is not None and isinstance(underlying, urllib.error.URLError):
        underlying = getattr(underlying, "reason", None)
    if isinstance(underlying, ConnectionRefusedError):
        return ScopedBeforeSendFailureReason.CONNECTION_REFUSED
    # ``socket.gaierror`` is NOT a subclass of ``ConnectionError``;
    # check the class name explicitly because Python does not export
    # ``gaierror`` from the ``socket`` module guarantees.
    if underlying is not None and type(underlying).__name__ == "gaierror":
        return ScopedBeforeSendFailureReason.DNS_FAILED
    # ``ssl.SSLError`` is a subclass of ``OSError`` and surfaces a
    # TLS pre-connect failure.
    if underlying is not None and type(underlying).__name__ == "SSLError":
        return ScopedBeforeSendFailureReason.TLS_PRECONNECT_FAILED
    # Treat everything else as a post-send transmission uncertainty.
    return ScopedDispatchUncertaintyReason.TRANSMISSION_UNKNOWN


class ScopedSchedulerClient:
    """Typed HTTP client for the canonical scoped current-run path.

    The client is the single producer of
    :class:`ScopedPromotionHttpTransportOutcome` variants; every
    variant is emitted from the typed path with bound reasons so
    the mapper can do exhaustive matching.
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._base_url = base_url
        self._token = token
        self._clock: Callable[[], float] = clock or _default_clock()

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
            observation = self._build_observation(
                context=context,
                transmission=RequestTransmissionState.NOT_STARTED,
                status_code=None,
                content_type=None,
                declared_content_length=None,
                response_byte_count=0,
                body_sha256=None,
                decoding_stage=(
                    PromotionResponseDecodingStage.NOT_ATTEMPTED
                ),
                elapsed_milliseconds=0,
            )
            return ScopedPromotionHttpBeforeSendFailed(
                observation=observation,
                reason_code=(
                    ScopedBeforeSendFailureReason.MISSING_BACKEND_URL
                ),
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
        start = self._clock()
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
        except TimeoutError:
            # Without an instrumented transport seam that can
            # prove byte transmission, ``urllib`` cannot confirm
            # whether the request reached the wire. Model as
            # dispatch-unknown via the closed reason.
            return self._dispatch_uncertain(
                context=context,
                start=start,
                reason_code=ScopedDispatchUncertaintyReason.TIMEOUT,
            )
        except ConnectionError:
            return self._dispatch_uncertain(
                context=context,
                start=start,
                reason_code=(
                    ScopedDispatchUncertaintyReason.CONNECTION_LOST
                ),
            )
        except OSError:
            # Connection reset or other low-level ``OSError`` is
            # treated as transmission-uncertain.
            return self._dispatch_uncertain(
                context=context,
                start=start,
                reason_code=(
                    ScopedDispatchUncertaintyReason.TRANSMISSION_UNKNOWN
                ),
            )

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
        elapsed_ms = self._elapsed_ms(start)
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
        elapsed_ms = self._elapsed_ms(start)
        sha256 = getattr(body_result, "body_sha256", None)
        # ``HTTPError`` is response-shaped: status, headers, and
        # body are available. We never store body text; only the
        # bounded metadata flows back.
        observation = self._build_observation(
            context=context,
            transmission=RequestTransmissionState.RESPONSE_COMPLETED,
            status_code=status_code,
            content_type=content_type,
            declared_content_length=declared,
            response_byte_count=getattr(
                body_result, "actual_byte_count", 0
            ),
            body_sha256=sha256,
            decoding_stage=PromotionResponseDecodingStage.COMPLETED,
            elapsed_milliseconds=elapsed_ms,
        )
        # 401 / 403 prove no promotion execution could begin;
        # ``HTTPError`` retains the status, headers, and readable
        # body so we MUST NOT collapse it into a generic exception.
        if status_code in (401, 403):
            return ScopedPromotionHttpAuthenticationRejected(
                observation=observation
            )
        # All other HTTP errors (400 / 409 / 429 / 5xx) without a
        # validated backend no-execution disposition are
        # commit-uncertainty at the dispatch layer.
        return PromotionHttpRejected(
            observation=observation,
            body_excerpt="",
        )

    def _consume_url_error(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        exc: urllib.error.URLError,
        start: float,
    ) -> ScopedPromotionHttpTransportOutcome:
        classified = _classify_url_error_reason(exc)
        if isinstance(classified, ScopedBeforeSendFailureReason):
            return self._before_send_failed(
                context=context,
                start=start,
                reason_code=classified,
            )
        return self._dispatch_uncertain(
            context=context,
            start=start,
            reason_code=classified,
        )

    def _dispatch_uncertain(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        start: float,
        reason_code: ScopedDispatchUncertaintyReason,
    ) -> ScopedPromotionHttpTransportOutcome:
        elapsed_ms = self._elapsed_ms(start)
        observation = self._build_observation(
            context=context,
            transmission=(
                RequestTransmissionState
                .DISPATCH_STARTED_TRANSMISSION_UNKNOWN
            ),
            status_code=None,
            content_type=None,
            declared_content_length=None,
            response_byte_count=0,
            body_sha256=None,
            decoding_stage=(
                PromotionResponseDecodingStage.NOT_ATTEMPTED
            ),
            elapsed_milliseconds=elapsed_ms,
        )
        return ScopedPromotionHttpDispatchUncertain(
            observation=observation,
            reason_code=reason_code,
        )

    def _before_send_failed(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        start: float,
        reason_code: ScopedBeforeSendFailureReason,
    ) -> ScopedPromotionHttpTransportOutcome:
        elapsed_ms = self._elapsed_ms(start)
        observation = self._build_observation(
            context=context,
            transmission=RequestTransmissionState.NOT_STARTED,
            status_code=None,
            content_type=None,
            declared_content_length=None,
            response_byte_count=0,
            body_sha256=None,
            decoding_stage=(
                PromotionResponseDecodingStage.NOT_ATTEMPTED
            ),
            elapsed_milliseconds=elapsed_ms,
        )
        return ScopedPromotionHttpBeforeSendFailed(
            observation=observation,
            reason_code=reason_code,
        )

    def _build_observation(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        transmission: RequestTransmissionState,
        status_code: int | None,
        content_type: str | None,
        declared_content_length: int | None,
        response_byte_count: int,
        body_sha256: str | None,
        decoding_stage: PromotionResponseDecodingStage,
        elapsed_milliseconds: int,
    ) -> PromotionHttpObservation:
        """Build a bounded ``PromotionHttpObservation`` in one
        place so the elapsed time is recorded exactly once for any
        variant.
        """
        return PromotionHttpObservation(
            request_id=context.request_id,
            request_transmission=transmission,
            status_code=status_code,
            content_type=content_type,
            declared_content_length=declared_content_length,
            response_byte_count=response_byte_count,
            response_body_sha256=body_sha256,
            decoding_stage=decoding_stage,
            elapsed_milliseconds=elapsed_milliseconds,
        )

    def _elapsed_ms(self, start: float) -> int:
        return int((self._clock() - start) * 1000)

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
                obs = self._build_observation(
                    context=context,
                    transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=observation_meta.content_type,
                    declared_content_length=(
                        observation_meta.declared_content_length
                    ),
                    response_byte_count=0,
                    body_sha256=None,
                    decoding_stage=(
                        PromotionResponseDecodingStage.EMPTY_BODY
                    ),
                    elapsed_milliseconds=(
                        observation_meta.elapsed_milliseconds
                    ),
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
            return ScopedPromotionHttpShortRead(
                observation=self._build_observation(
                    context=context,
                    transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=observation_meta.content_type,
                    declared_content_length=(
                        observation_meta.declared_content_length
                    ),
                    response_byte_count=body_result.actual_byte_count,
                    body_sha256=body_result.body_sha256,
                    decoding_stage=(
                        PromotionResponseDecodingStage.WIRE_SCHEMA
                    ),
                    elapsed_milliseconds=(
                        observation_meta.elapsed_milliseconds
                    ),
                )
            )
        if isinstance(body_result, ScopedBodyReadLimitExceeded):
            return ScopedPromotionHttpBodyLimitExceeded(
                observation=self._build_observation(
                    context=context,
                    transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=observation_meta.content_type,
                    declared_content_length=(
                        observation_meta.declared_content_length
                    ),
                    response_byte_count=body_result.actual_byte_count,
                    body_sha256=body_result.body_sha256,
                    decoding_stage=(
                        PromotionResponseDecodingStage.WIRE_SCHEMA
                    ),
                    elapsed_milliseconds=(
                        observation_meta.elapsed_milliseconds
                    ),
                )
            )
        if isinstance(body_result, ScopedBodyReadFailed):
            # Read failure AFTER response headers were received.
            # Without further bytes the request body may have been
            # acknowledged by the backend; model as dispatch
            # uncertainty. The body reader does not know whether
            # the underlying failure was a read timeout or a
            # connection reset; conservatively use
            # ``TRANSMISSION_UNKNOWN`` so the dispatcher remains
            # accurate about the missing evidence.
            return ScopedPromotionHttpDispatchUncertain(
                observation=self._build_observation(
                    context=context,
                    transmission=(
                        RequestTransmissionState.RESPONSE_COMPLETED
                    ),
                    status_code=status_code,
                    content_type=observation_meta.content_type,
                    declared_content_length=(
                        observation_meta.declared_content_length
                    ),
                    response_byte_count=0,
                    body_sha256=None,
                    decoding_stage=(
                        PromotionResponseDecodingStage.JSON_DECODE
                    ),
                    elapsed_milliseconds=(
                        observation_meta.elapsed_milliseconds
                    ),
                ),
                reason_code=(
                    ScopedDispatchUncertaintyReason.TRANSMISSION_UNKNOWN
                ),
            )
        # ``assert_never`` provably fails typing/tests when a new
        # body-read variant is added without an explicit handler.
        from typing import assert_never

        assert_never(body_result)


__all__ = [
    "REQUEST_ID_HEADER",
    "ScopedSchedulerBackendConfigError",
    "ScopedSchedulerClient",
]
