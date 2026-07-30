"""Status semantics for the scoped HTTP seam.

ACT-K9B-HULK-PROMOTION-SCOPED-HTTP-CLIENT-RESPONSIBILITY-SPLIT01.

Owns the status-code -> typed-transport-variant mapping
applied AFTER the bounded body read finishes:

* ``200`` with a valid canonical scoped payload
  -> ``ScopedPromotionHttpSucceeded``;
* ``200`` with an aggregate successful zero payload
  -> ``ScopedPromotionHttpSucceeded``;
* ``200`` with an empty body
  -> bounded JSON-decode uncertainty;
* ``200`` with malformed JSON
  -> invalid-JSON uncertainty;
* ``200`` with a legacy snake_case schema
  -> invalid scoped schema;
* ``202`` (with or without body)
  -> ``PromotionHttpAccepted``;
* ``204``
  -> ``PromotionHttpNoContent``;
* ``401`` / ``403``
  -> ``ScopedPromotionHttpAuthenticationRejected``
  (precise ``DEFINITELY_NOT_COMMITTED`` disposition);
* ``HTTPError`` for any other 4xx / 5xx
  -> ``PromotionHttpRejected`` (uncertain; no instrumented
  proof that the backend did not execute the request).

A malformed ``500`` MUST NOT become a definite rejection.
A canonical-looking ``202`` MUST NEVER become a completed
success variant.
"""

from __future__ import annotations

import urllib.error
from typing import Any

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpInvalidJson,
    PromotionHttpRejected,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpAuthenticationRejected,
    ScopedPromotionHttpBodyLimitExceeded,
    ScopedPromotionHttpReadFailed,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpShortRead,
    ScopedPromotionHttpTransportOutcome,
    ScopedReadFailureReason,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_body import (
    ScopedBodyReadComplete,
    ScopedBodyReadFailed,
    ScopedBodyReadLimitExceeded,
    ScopedBodyReadReason,
    ScopedBodyReadShort,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_request import (
    content_type,
    declared_content_length,
)
from k8s_diag_agent.ui.server_incident_internal_scoped_response import (
    ScopedResponseObservation,
    accepted_outcome,
    decode_scoped_body,
    no_content_outcome,
)

__all__ = [
    "classify_success_response",
    "classify_http_error_response",
    "dispatch_body_outcome",
]


def _build_response_meta(
    *,
    context: ScopedPromotionHttpRequestContext,
    resp: Any,
    elapsed_milliseconds: int,
    body_result: Any,
) -> ScopedResponseObservation:
    """Build the bounded response metadata carried into the
    typed outcome before body classification.
    """
    return ScopedResponseObservation(
        status_code=int(getattr(resp, "status", 200)),
        content_type=content_type(getattr(resp, "headers", None)),
        declared_content_length=declared_content_length(
            getattr(resp, "headers", None)
        ),
        body_sha256=getattr(body_result, "body_sha256", None),
        elapsed_milliseconds=elapsed_milliseconds,
    )


def classify_success_response(
    *,
    context: ScopedPromotionHttpRequestContext,
    resp: Any,
    elapsed_milliseconds: int,
    body_result: Any,
) -> ScopedPromotionHttpTransportOutcome:
    """Map a 2xx ``urlopen`` body-read result into a typed outcome.

    The body reader has already finished; we only project the
    body-read result + status code into the typed transport union.
    """
    status_code = int(getattr(resp, "status", 200))
    observation_meta = _build_response_meta(
        context=context,
        resp=resp,
        elapsed_milliseconds=elapsed_milliseconds,
        body_result=body_result,
    )
    return dispatch_body_outcome(
        context=context,
        status_code=status_code,
        body_result=body_result,
        observation_meta=observation_meta,
    )


def classify_http_error_response(
    *,
    context: ScopedPromotionHttpRequestContext,
    error: urllib.error.HTTPError,
    observation_factory: Any,
    elapsed_milliseconds: int,
) -> ScopedPromotionHttpTransportOutcome:
    """Map an ``HTTPError`` response into a typed outcome.

    ``401`` / ``403`` construct the authentication rejection
    variant. Every other HTTP error is the bounded
    ``PromotionHttpRejected`` variant -- the active scoped path
    does NOT have proof that the backend did not execute the
    request, so a malformed ``500`` must not become a definite
    rejection.
    """
    status_code = error.code
    observed_content_type = content_type(getattr(error, "headers", None))
    observed_declared = declared_content_length(
        getattr(error, "headers", None)
    )
    observed_byte_count = getattr(error, "actual_byte_count", 0)
    body_sha256 = getattr(error, "body_sha256", None)
    observation = observation_factory(
        context=context,
        transmission=RequestTransmissionState.RESPONSE_COMPLETED,
        status_code=status_code,
        content_type=observed_content_type,
        declared_content_length=observed_declared,
        response_byte_count=observed_byte_count,
        body_sha256=body_sha256,
        decoding_stage=PromotionResponseDecodingStage.COMPLETED,
        elapsed_milliseconds=elapsed_milliseconds,
    )
    if status_code in (401, 403):
        return ScopedPromotionHttpAuthenticationRejected(
            observation=observation
        )
    return PromotionHttpRejected(
        observation=observation,
        body_excerpt="",
    )


def dispatch_body_outcome(
    *,
    context: ScopedPromotionHttpRequestContext,
    status_code: int,
    body_result: Any,
    observation_meta: ScopedResponseObservation,
) -> ScopedPromotionHttpTransportOutcome:
    """Map the body-read result and status code into a typed outcome.

    The body-result dispatch is the single closed pattern
    for the active scoped path. Every concrete body-read
    variant is handled explicitly; the final ``assert_never``
    provably fails typing/tests when a new body-read variant
    is added without an explicit handler.
    """
    if isinstance(body_result, ScopedBodyReadComplete):
        return _dispatch_complete_body(
            context=context,
            status_code=status_code,
            body_result=body_result,
            observation_meta=observation_meta,
        )
    if isinstance(body_result, ScopedBodyReadShort):
        return ScopedPromotionHttpShortRead(
            observation=_build_response_observation(
                context=context,
                status_code=status_code,
                observation_meta=observation_meta,
                response_byte_count=body_result.actual_byte_count,
                body_sha256=body_result.body_sha256,
                decoding_stage=PromotionResponseDecodingStage.WIRE_SCHEMA,
            )
        )
    if isinstance(body_result, ScopedBodyReadLimitExceeded):
        return ScopedPromotionHttpBodyLimitExceeded(
            observation=_build_response_observation(
                context=context,
                status_code=status_code,
                observation_meta=observation_meta,
                response_byte_count=body_result.actual_byte_count,
                body_sha256=body_result.body_sha256,
                decoding_stage=PromotionResponseDecodingStage.WIRE_SCHEMA,
            )
        )
    if isinstance(body_result, ScopedBodyReadFailed):
        return _dispatch_failed_body_read(
            context=context,
            status_code=status_code,
            body_result=body_result,
            observation_meta=observation_meta,
        )
    # ``assert_never`` provably fails typing/tests when a new
    # body-read variant is added without an explicit handler.
    from typing import assert_never

    assert_never(body_result)


def _dispatch_complete_body(
    *,
    context: ScopedPromotionHttpRequestContext,
    status_code: int,
    body_result: ScopedBodyReadComplete,
    observation_meta: ScopedResponseObservation,
) -> ScopedPromotionHttpTransportOutcome:
    """Dispatch a fully-consumed body into the typed variant.

    * ``202`` always -> ``PromotionHttpAccepted``;
    * ``204`` always -> ``PromotionHttpNoContent``;
    * ``200`` with empty body -> bounded JSON-decode uncertainty;
    * ``200`` with non-empty body -> :func:`decode_scoped_body`.
    """
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
        obs = _build_response_observation(
            context=context,
            status_code=status_code,
            observation_meta=observation_meta,
            response_byte_count=0,
            body_sha256=None,
            decoding_stage=PromotionResponseDecodingStage.EMPTY_BODY,
        )
        return PromotionHttpInvalidJson(
            observation=obs, body_excerpt=""
        )
    return decode_scoped_body(
        context=context,
        body=body_result.received,
        observation_meta=observation_meta,
    )


def _dispatch_failed_body_read(
    *,
    context: ScopedPromotionHttpRequestContext,
    status_code: int,
    body_result: ScopedBodyReadFailed,
    observation_meta: ScopedResponseObservation,
) -> ScopedPromotionHttpReadFailed:
    """Map the typed body-read reason into the closed
    read-failure vocabulary.

    The body-read failure is a transport-level observation
    distinct from a dispatch connection reset.

    ACT-K9B-HULK-PROMOTION-TYPED-ACCUMULATOR-AND-LOCAL-CLOSURE01-CORRECTION01-FINALIZATION01:
    ``TRANSMISSION_UNKNOWN`` is its own distinct bounded code;
    an unknown post-header read failure MUST NOT be collapsed
    into ``CONNECTION_LOST`` or ``TIMEOUT``.
    """
    body_reason = body_result.reason
    if body_reason == ScopedBodyReadReason.TIMEOUT:
        scoped_read_reason = ScopedReadFailureReason.TIMEOUT
    elif body_reason == ScopedBodyReadReason.CONNECTION_LOST:
        scoped_read_reason = ScopedReadFailureReason.CONNECTION_LOST
    else:
        scoped_read_reason = ScopedReadFailureReason.TRANSMISSION_UNKNOWN
    return ScopedPromotionHttpReadFailed(
        observation=_build_response_observation(
            context=context,
            status_code=status_code,
            observation_meta=observation_meta,
            response_byte_count=0,
            body_sha256=None,
            decoding_stage=PromotionResponseDecodingStage.JSON_DECODE,
        ),
        reason_code=scoped_read_reason,
    )


def _build_response_observation(
    *,
    context: ScopedPromotionHttpRequestContext,
    status_code: int,
    observation_meta: ScopedResponseObservation,
    response_byte_count: int,
    body_sha256: str | None,
    decoding_stage: PromotionResponseDecodingStage,
) -> Any:
    """Build a bounded ``PromotionHttpObservation`` for HTTPError /
    body-read failure dispatch.

    The :class:`ScopedResponseObservation` carries the elapsed
    time stamped by the executor; here we hoist that into the
    full observation so the response metadata is preserved
    downstream.
    """
    from k8s_diag_agent.collect.promotion_http_transport import (
        PromotionHttpObservation,
    )

    return PromotionHttpObservation(
        request_id=context.request_id,
        request_transmission=RequestTransmissionState.RESPONSE_COMPLETED,
        status_code=status_code,
        content_type=observation_meta.content_type,
        declared_content_length=observation_meta.declared_content_length,
        response_byte_count=response_byte_count,
        response_body_sha256=body_sha256,
        decoding_stage=decoding_stage,
        elapsed_milliseconds=observation_meta.elapsed_milliseconds,
    )
