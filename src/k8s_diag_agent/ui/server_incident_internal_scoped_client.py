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
the elapsed-time measurement (covering the entire operation),
the typed exception classification (DNS, connection refused, TLS
pre-connect, timeout, connection resets), and the typed outcome
assembly.

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
import socket
import ssl
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
    ScopedPromotionHttpReadFailed,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpShortRead,
    ScopedPromotionHttpSucceeded,
    ScopedPromotionHttpTransportOutcome,
    ScopedReadFailureReason,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
    ScopedBodyReadComplete,
    ScopedBodyReadFailed,
    ScopedBodyReadLimitExceeded,
    ScopedBodyReadReason,
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
    """Raised when the scheduler backend URL is not configured."""


class ScopedSchedulerMissingTokenError(Exception):
    """Raised when the scheduler internal API token is not configured."""


class _MonotonicClock:
    """Injected monotonic clock authority.

    The active scoped HTTP path uses one monotonic clock so the
    measured ``elapsed_milliseconds`` reflects the entire
    operation -- HTTP response / body reading, status
    classification, JSON decoding, wire parsing, and bounded
    outcome construction. The clock is referenced at the END
    of the operation (after status classification, JSON decode,
    wire parse, request/result binding, and transport-variant
    construction) so the elapsed time is comprehensive.
    """

    def __call__(self) -> float:
        return time.monotonic()


def _default_clock() -> _MonotonicClock:
    return _MonotonicClock()


def _require_authenticated_config(
    base_url: str,
    token: str | None,
) -> tuple[str, str]:
    """Validate configuration; raise a typed exception naming the
    missing field.

    The active scoped path MUST NOT silently send an unauthenticated
    request or a request with a missing backend URL. Each missing
    field raises its own typed exception so the caller can carry
    the exact reason into the active scoped path.
    """
    backend_url = _require_valid_backend_url(base_url)
    internal_token = _require_valid_internal_token(token)
    return backend_url, internal_token


def _require_valid_backend_url(base_url: str) -> str:
    """Validate the backend URL; raise typed exception when missing."""
    backend_url = (base_url or "").strip()
    if not backend_url:
        raise ScopedSchedulerBackendConfigError(
            "scoped scheduler backend URL is not configured"
        )
    return backend_url


def _require_valid_internal_token(token: str | None) -> str:
    """Validate the internal API token; raise typed exception when missing."""
    if not token:
        raise ScopedSchedulerMissingTokenError(
            "scoped scheduler internal API token is not configured"
        )
    return token


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
    if isinstance(underlying, socket.gaierror):
        return ScopedBeforeSendFailureReason.DNS_FAILED
    if isinstance(underlying, ssl.SSLError):
        return ScopedBeforeSendFailureReason.TLS_PRECONNECT_FAILED
    # Treat everything else as a post-send transmission uncertainty.
    return ScopedDispatchUncertaintyReason.TRANSMISSION_UNKNOWN


class ScopedSchedulerClient:
    """Typed HTTP client for the canonical scoped current-run path.

    The client is the single producer of
    :class:`ScopedPromotionHttpTransportOutcome` variants; every
    variant is emitted from the typed path with bound reasons so
    the mapper can do exhaustive matching. Duration is measured
    via the injected monotonic clock from the start of the HTTP
    loop until the bound transport variant is constructed.
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
            return ScopedPromotionHttpBeforeSendFailed(
                observation=self._build_observation(
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
                ),
                reason_code=(
                    ScopedBeforeSendFailureReason.MISSING_BACKEND_URL
                ),
            )
        except ScopedSchedulerMissingTokenError:
            return ScopedPromotionHttpBeforeSendFailed(
                observation=self._build_observation(
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
                ),
                reason_code=(
                    ScopedBeforeSendFailureReason.MISSING_INTERNAL_TOKEN
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
                typed_outcome = self._consume_success(
                    context=context,
                    resp=resp,
                    start=start,
                )
        except urllib.error.HTTPError as exc:
            typed_outcome = self._consume_http_error(
                context=context,
                error=exc,
                start=start,
            )
        except urllib.error.URLError as exc:
            typed_outcome = self._consume_url_error(
                context=context,
                exc=exc,
                start=start,
            )
        except TimeoutError:
            typed_outcome = self._dispatch_uncertain(
                context=context,
                start=start,
                reason_code=ScopedDispatchUncertaintyReason.TIMEOUT,
            )
        except ConnectionError:
            typed_outcome = self._dispatch_uncertain(
                context=context,
                start=start,
                reason_code=(
                    ScopedDispatchUncertaintyReason.CONNECTION_LOST
                ),
            )
        except OSError:
            typed_outcome = self._dispatch_uncertain(
                context=context,
                start=start,
                reason_code=(
                    ScopedDispatchUncertaintyReason.TRANSMISSION_UNKNOWN
                ),
            )
        # Record the final elapsed time AFTER the transport variant
        # is constructed. The clock is referenced here -- at the
        # end of the operation -- so the measurement includes the
        # decoding and binding work that follows the body read.
        return self._finalize_observation(
            context=context,
            typed_outcome=typed_outcome,
            start=start,
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
        if status_code in (401, 403):
            return ScopedPromotionHttpAuthenticationRejected(
                observation=observation
            )
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

    def _finalize_observation(
        self,
        *,
        context: ScopedPromotionHttpRequestContext,
        typed_outcome: ScopedPromotionHttpTransportOutcome,
        start: float,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Re-stamp the elapsed time on the observation.

        The clock is referenced at the END of the operation
        AFTER the transport variant is constructed so the
        measurement covers status classification, JSON
        decode, wire parse, request/result binding, and the
        construction of the typed transport variant.
        """
        elapsed_ms = self._elapsed_ms(start)
        # ``Observation`` is frozen; rebuild a new instance so the
        # final elapsed time is correct. The other fields are
        # preserved from the original.
        new_observation = PromotionHttpObservation(
            request_id=typed_outcome.observation.request_id,
            request_transmission=(
                typed_outcome.observation.request_transmission
            ),
            status_code=typed_outcome.observation.status_code,
            content_type=typed_outcome.observation.content_type,
            declared_content_length=(
                typed_outcome.observation.declared_content_length
            ),
            response_byte_count=(
                typed_outcome.observation.response_byte_count
            ),
            response_body_sha256=(
                typed_outcome.observation.response_body_sha256
            ),
            decoding_stage=typed_outcome.observation.decoding_stage,
            elapsed_milliseconds=elapsed_ms,
        )
        return self._replace_observation(
            typed_outcome, new_observation
        )

    @staticmethod
    def _replace_observation(
        typed_outcome: ScopedPromotionHttpTransportOutcome,
        new_observation: PromotionHttpObservation,
    ) -> ScopedPromotionHttpTransportOutcome:
        """Construct a copy of ``typed_outcome`` whose observation
        is ``new_observation``. Frozen dataclasses cannot be
        mutated in place, so the variant is rebuilt with the
        updated observation.
        """
        from typing import assert_never

        if isinstance(typed_outcome, ScopedPromotionHttpSucceeded):
            return ScopedPromotionHttpSucceeded(
                observation=new_observation,
                bound=typed_outcome.bound,
            )
        if isinstance(typed_outcome, ScopedPromotionHttpAuthenticationRejected):
            return ScopedPromotionHttpAuthenticationRejected(
                observation=new_observation
            )
        if isinstance(typed_outcome, ScopedPromotionHttpBodyLimitExceeded):
            return ScopedPromotionHttpBodyLimitExceeded(
                observation=new_observation
            )
        if isinstance(typed_outcome, ScopedPromotionHttpShortRead):
            return ScopedPromotionHttpShortRead(
                observation=new_observation
            )
        if isinstance(typed_outcome, ScopedPromotionHttpReadFailed):
            return ScopedPromotionHttpReadFailed(
                observation=new_observation,
                reason_code=typed_outcome.reason_code,
            )
        if isinstance(typed_outcome, ScopedPromotionHttpBeforeSendFailed):
            return ScopedPromotionHttpBeforeSendFailed(
                observation=new_observation,
                reason_code=typed_outcome.reason_code,
            )
        if isinstance(typed_outcome, ScopedPromotionHttpDispatchUncertain):
            return ScopedPromotionHttpDispatchUncertain(
                observation=new_observation,
                reason_code=typed_outcome.reason_code,
            )
        # Generic ``PromotionHttp*`` semantic variants are
        # dataclasses with an ``observation`` (and sometimes
        # additional fields). Rebuild each one preserving the
        # other fields.
        from k8s_diag_agent.collect.promotion_http_transport import (
            PromotionHttpAccepted,
            PromotionHttpInvalidJson,
            PromotionHttpInvalidSchema,
            PromotionHttpNoContent,
            PromotionHttpRejected,
            PromotionHttpResponseTruncated,
        )

        if isinstance(typed_outcome, PromotionHttpAccepted):
            return PromotionHttpAccepted(
                observation=new_observation,
            )
        if isinstance(typed_outcome, PromotionHttpNoContent):
            return PromotionHttpNoContent(
                observation=new_observation,
            )
        if isinstance(typed_outcome, PromotionHttpInvalidJson):
            return PromotionHttpInvalidJson(
                observation=new_observation,
                body_excerpt=typed_outcome.body_excerpt,
            )
        if isinstance(typed_outcome, PromotionHttpInvalidSchema):
            return PromotionHttpInvalidSchema(
                observation=new_observation,
                schema_error=typed_outcome.schema_error,
            )
        if isinstance(typed_outcome, PromotionHttpResponseTruncated):
            return PromotionHttpResponseTruncated(
                observation=new_observation,
            )
        if isinstance(typed_outcome, PromotionHttpRejected):
            return PromotionHttpRejected(
                observation=new_observation,
                body_excerpt=typed_outcome.body_excerpt,
            )
        assert_never(typed_outcome)

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
            # Body read failed AFTER response headers were received.
            # Map the typed body-read reason into the closed
            # read-failure vocabulary so the mapper performs
            # exhaustive matching. The body-read failure is a
            # transport-level observation distinct from a
            # dispatch connection reset.
            #
            # ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01:
            # ``TRANSMISSION_UNKNOWN`` is its own distinct bounded
            # code; an unknown post-header read failure MUST NOT be
            # collapsed into ``CONNECTION_LOST`` or ``TIMEOUT``.
            body_reason = body_result.reason
            if body_reason == ScopedBodyReadReason.TIMEOUT:
                scoped_read_reason = ScopedReadFailureReason.TIMEOUT
            elif body_reason == ScopedBodyReadReason.CONNECTION_LOST:
                scoped_read_reason = (
                    ScopedReadFailureReason.CONNECTION_LOST
                )
            else:
                scoped_read_reason = (
                    ScopedReadFailureReason.TRANSMISSION_UNKNOWN
                )
            return ScopedPromotionHttpReadFailed(
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
                reason_code=scoped_read_reason,
            )
        # ``assert_never`` provably fails typing/tests when a new
        # body-read variant is added without an explicit handler.
        from typing import assert_never

        assert_never(body_result)


__all__ = [
    "REQUEST_ID_HEADER",
    "ScopedSchedulerBackendConfigError",
    "ScopedSchedulerClient",
    "ScopedSchedulerMissingTokenError",
]
