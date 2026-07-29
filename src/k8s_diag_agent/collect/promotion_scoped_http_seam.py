"""Typed HTTP seam for the canonical scoped current-run promotion path.

ACT-K9B-HULK-PROMOTION-SCOPED-CLIENT-TYPED-HTTP-SEAM01.

This module owns the typed request context, the typed success
variant, and the bounded HTTP observation for the scoped path.

Identity ownership:

* ``run_id`` -- domain promotion/run identity. Sent as ``runId``
  on the wire and copied into the bounded downstream outcome.
* ``request_id`` -- one HTTP-attempt correlation identity. Carried
  in transport logs and the ``PromotionHttpObservation`` only; it
  MUST never be used as ``run_id`` or be promoted into a domain
  identifier.
* ``source_identity`` -- domain source-identity of the scoped
  promotion request.

The transport observation retains the request id and the
request-transmission state, plus the response byte count and the
bounded body digest, so the scheduler can correlate the attempt
without leaking the request body.

The closed ``ScopedPromotionHttpTransportOutcome`` union is the
bounded set of HTTP transport shapes the scoped client may return.
``typing.assert_never`` is used at the consumer boundary so a
newly added variant cannot silently disappear from the dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.identifiers import AlertSignalId, HealthRunId
from ..incident_alert_promotion_binding import BoundScopedPromotionResult
from .promotion_http_transport import (
    PromotionHttpAccepted,
    PromotionHttpInvalidJson,
    PromotionHttpInvalidSchema,
    PromotionHttpNoContent,
    PromotionHttpObservation,
    PromotionHttpRejected,
    PromotionHttpResponseTruncated,
    PromotionHttpTransportFailureAfterSend,
    PromotionHttpTransportFailureBeforeSend,
)

MAX_REQUEST_ID_LENGTH = 128
MAX_SOURCE_IDENTITY_LENGTH = 512
MAX_SIGNAL_IDS = 200


@dataclass(frozen=True, slots=True)
class ScopedPromotionHttpRequestContext:
    """Immutable, typed request context for one scoped promotion
    HTTP attempt.

    Distinct identities:

    * ``run_id`` -- domain promotion/run identity. Sent as ``runId``
      and copied into the downstream ``PromotionSucceeded.run_id``.
    * ``request_id`` -- one HTTP-attempt correlation identity. Only
      ever appears on ``PromotionHttpObservation`` and structured
      transport events; never on a domain outcome.
    """

    run_id: HealthRunId
    request_id: str
    source_identity: str
    signal_ids: tuple[AlertSignalId, ...]

    def __post_init__(self) -> None:
        # ``HealthRunId`` and ``AlertSignalId`` are ``typing.NewType``
        # aliases over ``str``; runtime ``isinstance`` against a
        # ``NewType`` is rejected on Python 3.14. Validate against
        # the underlying ``str`` instead; the static type checker
        # is the authority for the NewType contract.
        if not isinstance(self.run_id, str):
            raise TypeError(
                "ScopedPromotionHttpRequestContext.run_id MUST be a "
                "HealthRunId (str-typed)"
            )
        if not isinstance(self.request_id, str) or not self.request_id:
            raise ValueError(
                "ScopedPromotionHttpRequestContext.request_id MUST be a "
                "non-empty string"
            )
        if len(self.request_id) > MAX_REQUEST_ID_LENGTH:
            raise ValueError(
                "ScopedPromotionHttpRequestContext.request_id exceeds "
                f"maximum length of {MAX_REQUEST_ID_LENGTH}"
            )
        if (
            not isinstance(self.source_identity, str)
            or not self.source_identity
            or len(self.source_identity) > MAX_SOURCE_IDENTITY_LENGTH
        ):
            raise ValueError(
                "ScopedPromotionHttpRequestContext.source_identity MUST "
                f"be a non-empty string bounded by {MAX_SOURCE_IDENTITY_LENGTH}"
            )
        if not self.signal_ids:
            raise ValueError(
                "ScopedPromotionHttpRequestContext.signal_ids MUST be "
                "non-empty"
            )
        if len(self.signal_ids) > MAX_SIGNAL_IDS:
            raise ValueError(
                "ScopedPromotionHttpRequestContext.signal_ids exceeds "
                f"maximum of {MAX_SIGNAL_IDS}"
            )
        if len(set(self.signal_ids)) != len(self.signal_ids):
            raise ValueError(
                "ScopedPromotionHttpRequestContext.signal_ids MUST be "
                "unique"
            )
        for signal_id in self.signal_ids:
            if not isinstance(signal_id, str):
                raise TypeError(
                    "ScopedPromotionHttpRequestContext.signal_ids entries "
                    "MUST be AlertSignalId (str-typed) instances"
                )


@dataclass(frozen=True, slots=True)
class ScopedPromotionHttpSucceeded:
    """Scoped transport outcome: 2xx with a valid bounded wire result.

    Carries the bounded observation plus the typed bound result so
    the dispatcher can drive the closed ``PromotionOutcome``
    projection without re-parsing the response body.
    """

    observation: PromotionHttpObservation
    bound: BoundScopedPromotionResult


# Closed union for the scoped HTTP transport surface. The success
# variant is endpoint-specific; the remaining variants are shared
# with the generic transport module because the failure / bounded-
# uncertainty shapes are endpoint-agnostic.
ScopedPromotionHttpTransportOutcome = (
    ScopedPromotionHttpSucceeded
    | PromotionHttpAccepted
    | PromotionHttpNoContent
    | PromotionHttpRejected
    | PromotionHttpInvalidJson
    | PromotionHttpInvalidSchema
    | PromotionHttpTransportFailureBeforeSend
    | PromotionHttpTransportFailureAfterSend
    | PromotionHttpResponseTruncated
)


__all__ = [
    "MAX_REQUEST_ID_LENGTH",
    "MAX_SIGNAL_IDS",
    "MAX_SOURCE_IDENTITY_LENGTH",
    "ScopedPromotionHttpRequestContext",
    "ScopedPromotionHttpSucceeded",
    "ScopedPromotionHttpTransportOutcome",
]
