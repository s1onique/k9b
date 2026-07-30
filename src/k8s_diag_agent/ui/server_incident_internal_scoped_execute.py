"""HTTP execution for the scoped HTTP seam.

ACT-K9B-HULK-PROMOTION-SCOPED-HTTP-CLIENT-RESPONSIBILITY-SPLIT01.

Owns the ``urlopen`` invocation, the response context handling,
and the handoff to the bounded body reader. The execution
delegate is the single owner of the typed exception handling
surface:

* ``HTTPError`` is forwarded to the status typing module;
* ``URLError`` is forwarded to the error classification module;
* ``TimeoutError`` / ``ConnectionError`` / generic ``OSError``
  each map to a closed :class:`ScopedDispatchUncertaintyReason`.

The executor receives the monotonic clock start from the
facade so the elapsed time recorded on intermediate
observations uses the same anchor as the facade's final
finalize step. The final elapsed time is computed at the END
of the operation by the finalize module so the measurement
covers the full HTTP loop, body read, status classification,
JSON decode, wire parse, request/result binding, and the
construction of the typed transport variant.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedBeforeSendFailureReason,
    ScopedDispatchUncertaintyReason,
    ScopedPromotionHttpBeforeSendFailed,
    ScopedPromotionHttpDispatchUncertain,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpTransportOutcome,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
    read_scoped_body,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_errors import (
    classify_url_error_reason,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_finalize import (
    build_observation,
    elapsed_milliseconds,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_request import (
    declared_content_length,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_status import (
    classify_http_error_response,
    classify_success_response,
)

__all__ = [
    "execute_scoped_request",
]


def _consume_success(
    *,
    context: ScopedPromotionHttpRequestContext,
    resp: Any,
    clock: Callable[[], float],
    start: float,
) -> ScopedPromotionHttpTransportOutcome:
    """Read the bounded body and dispatch the success response.

    The body reader is invoked once; the resulting body-read
    variant is forwarded to the status module for the
    status-code -> typed-variant mapping.
    """
    declared = declared_content_length(getattr(resp, "headers", None))
    body_result = read_scoped_body(resp, declared_content_length=declared)
    elapsed_ms = elapsed_milliseconds(clock, start)
    return classify_success_response(
        context=context,
        resp=resp,
        elapsed_milliseconds=elapsed_ms,
        body_result=body_result,
    )


def _consume_http_error(
    *,
    context: ScopedPromotionHttpRequestContext,
    error: urllib.error.HTTPError,
    clock: Callable[[], float],
    start: float,
) -> ScopedPromotionHttpTransportOutcome:
    """Read the bounded body from the HTTPError and dispatch the
    bounded observation into the status module.

    The observation carries the byte count and SHA-256 of the
    bounded body, but the body text itself is never retained.
    """
    declared = declared_content_length(getattr(error, "headers", None))
    body_result = read_scoped_body(error, declared_content_length=declared)
    elapsed_ms = elapsed_milliseconds(clock, start)
    setattr(error, "actual_byte_count", body_result.actual_byte_count)
    setattr(error, "body_sha256", body_result.body_sha256)
    return classify_http_error_response(
        context=context,
        error=error,
        observation_factory=lambda **kwargs: build_observation(
            context=kwargs["context"],
            transmission=kwargs["transmission"],
            status_code=kwargs["status_code"],
            content_type=kwargs["content_type"],
            declared_content_length=kwargs["declared_content_length"],
            response_byte_count=kwargs["response_byte_count"],
            body_sha256=kwargs["body_sha256"],
            decoding_stage=kwargs["decoding_stage"],
            elapsed_milliseconds_value=kwargs["elapsed_milliseconds"],
        ),
        elapsed_milliseconds=elapsed_ms,
    )


def _consume_url_error(
    *,
    context: ScopedPromotionHttpRequestContext,
    exc: urllib.error.URLError,
    clock: Callable[[], float],
    start: float,
) -> ScopedPromotionHttpTransportOutcome:
    """Forward a ``URLError`` to the typed classification module."""
    classified = classify_url_error_reason(exc)
    if isinstance(classified, ScopedBeforeSendFailureReason):
        return _before_send_failed_with_elapsed(
            context=context,
            reason_code=classified,
            elapsed_milliseconds=elapsed_milliseconds(clock, start),
        )
    return _dispatch_uncertain_with_elapsed(
        context=context,
        reason_code=classified,
        elapsed_milliseconds=elapsed_milliseconds(clock, start),
    )


def _before_send_failed_with_elapsed(
    *,
    context: ScopedPromotionHttpRequestContext,
    reason_code: ScopedBeforeSendFailureReason,
    elapsed_milliseconds: int,
) -> ScopedPromotionHttpTransportOutcome:
    """Construct the typed before-send failure variant with the
    pre-computed elapsed time.
    """
    obs = build_observation(
        context=context,
        transmission=RequestTransmissionState.NOT_STARTED,
        status_code=None,
        content_type=None,
        declared_content_length=None,
        response_byte_count=0,
        body_sha256=None,
        decoding_stage=PromotionResponseDecodingStage.NOT_ATTEMPTED,
        elapsed_milliseconds_value=elapsed_milliseconds,
    )
    return ScopedPromotionHttpBeforeSendFailed(
        observation=obs,
        reason_code=reason_code,
    )


def _dispatch_uncertain_with_elapsed(
    *,
    context: ScopedPromotionHttpRequestContext,
    reason_code: ScopedDispatchUncertaintyReason,
    elapsed_milliseconds: int,
) -> ScopedPromotionHttpTransportOutcome:
    """Construct the typed dispatch-uncertainty variant with the
    pre-computed elapsed time.
    """
    obs = build_observation(
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
        decoding_stage=PromotionResponseDecodingStage.NOT_ATTEMPTED,
        elapsed_milliseconds_value=elapsed_milliseconds,
    )
    return ScopedPromotionHttpDispatchUncertain(
        observation=obs,
        reason_code=reason_code,
    )


def execute_scoped_request(
    *,
    context: ScopedPromotionHttpRequestContext,
    request: urllib.request.Request,
    timeout: float,
    clock: Callable[[], float],
    start: float,
) -> ScopedPromotionHttpTransportOutcome:
    """Run the HTTP loop and dispatch the typed outcome.

    The ``start`` parameter is the monotonic clock anchor
    captured by the facade BEFORE the executor runs. The
    executor uses the same anchor when computing elapsed
    times on intermediate observations so the final
    finalize step at the END of the operation re-stamps the
    elapsed time relative to the same anchor and the
    measurement covers the full operation.
    """
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return _consume_success(
                context=context,
                resp=resp,
                clock=clock,
                start=start,
            )
    except urllib.error.HTTPError as exc:
        return _consume_http_error(
            context=context,
            error=exc,
            clock=clock,
            start=start,
        )
    except urllib.error.URLError as exc:
        return _consume_url_error(
            context=context,
            exc=exc,
            clock=clock,
            start=start,
        )
    except TimeoutError:
        return _dispatch_uncertain_with_elapsed(
            context=context,
            reason_code=ScopedDispatchUncertaintyReason.TIMEOUT,
            elapsed_milliseconds=elapsed_milliseconds(clock, start),
        )
    except ConnectionError:
        return _dispatch_uncertain_with_elapsed(
            context=context,
            reason_code=ScopedDispatchUncertaintyReason.CONNECTION_LOST,
            elapsed_milliseconds=elapsed_milliseconds(clock, start),
        )
    except OSError:
        return _dispatch_uncertain_with_elapsed(
            context=context,
            reason_code=ScopedDispatchUncertaintyReason.TRANSMISSION_UNKNOWN,
            elapsed_milliseconds=elapsed_milliseconds(clock, start),
        )
