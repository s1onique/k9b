"""Final observation reconstruction and timing for the scoped HTTP seam.

ACT-K9B-HULK-PROMOTION-SCOPED-HTTP-CLIENT-RESPONSIBILITY-SPLIT01.

Owns:

* The single monotonic clock authority used by the active
  scoped HTTP path. The clock is referenced at the END of
  the operation (after status classification, JSON decode,
  wire parse, request/result binding, and transport-variant
  construction) so the elapsed time covers the full
  operation.
* The bounded ``PromotionHttpObservation`` constructor
  (``build_observation``) shared by every transport variant.
* The final ``replace_observation`` helper that re-stamps the
  elapsed time on the typed transport variant. The
  ``PromotionHttpObservation`` is frozen; the typed variants
  are rebuilt here with the updated observation so the
  mapper receives the comprehensive elapsed time.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from k8s_diag_agent.collect.promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpObservation,
    PromotionHttpRejected,
    PromotionHttpResponseTruncated,
    PromotionResponseDecodingStage,
    RequestTransmissionState,
)
from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpAuthenticationRejected,
    ScopedPromotionHttpBeforeSendFailed,
    ScopedPromotionHttpBodyLimitExceeded,
    ScopedPromotionHttpDispatchUncertain,
    ScopedPromotionHttpReadFailed,
    ScopedPromotionHttpRequestContext,
    ScopedPromotionHttpShortRead,
    ScopedPromotionHttpSucceeded,
    ScopedPromotionHttpTransportOutcome,
)

__all__ = [
    "MONOTONIC_CLOCK",
    "MonotonicClock",
    "build_observation",
    "elapsed_milliseconds",
    "finalize_observation",
    "replace_observation",
]


class MonotonicClock:
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

    __slots__ = ()

    def __call__(self) -> float:
        return time.monotonic()


# Default monotonic clock instance. There is exactly one
# monotonic clock authority in the active scoped path.
MONOTONIC_CLOCK: MonotonicClock = MonotonicClock()


def elapsed_milliseconds(clock: Callable[[], float], start: float) -> int:
    """Compute elapsed milliseconds since ``start`` using the
    supplied monotonic clock.

    The active scoped path uses exactly one monotonic clock
    per request; the elapsed time is recorded once at the END
    of the operation so it covers the full HTTP loop, the
    body read, the status classification, the JSON decode,
    the wire parse, the request/result binding, and the
    construction of the typed transport variant.
    """
    return int((clock() - start) * 1000)


def build_observation(
    *,
    context: ScopedPromotionHttpRequestContext,
    transmission: RequestTransmissionState,
    status_code: int | None,
    content_type: str | None,
    declared_content_length: int | None,
    response_byte_count: int,
    body_sha256: str | None,
    decoding_stage: PromotionResponseDecodingStage,
    elapsed_milliseconds_value: int,
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
        elapsed_milliseconds=elapsed_milliseconds_value,
    )


def replace_observation(
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


def finalize_observation(
    *,
    context: ScopedPromotionHttpRequestContext,
    typed_outcome: ScopedPromotionHttpTransportOutcome,
    clock: Callable[[], float],
    start: float,
) -> ScopedPromotionHttpTransportOutcome:
    """Re-stamp the elapsed time on the observation.

    The clock is referenced at the END of the operation
    AFTER the transport variant is constructed so the
    measurement covers status classification, JSON
    decode, wire parse, request/result binding, and the
    construction of the typed transport variant.
    """
    elapsed_ms = elapsed_milliseconds(clock, start)
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
    return replace_observation(typed_outcome, new_observation)
