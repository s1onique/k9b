"""Typed HTTP seam for the canonical scoped current-run promotion path.

ACT-K9B-HULK-PROMOTION-SCOPED-DISPATCH-ACTIVATION-AND-CERTAINTY01.

This module owns the typed request context, the typed success
variant, and the bounded HTTP observation for the scoped path.

Identity ownership:

* ``run_id`` -- domain promotion/run identity. Sent as ``runId``
  on the wire and copied into the bounded downstream outcome.
* ``request_id`` -- one HTTP-attempt correlation identity. Carried
  in transport logs, the ``X-K9B-Promotion-Request-ID`` header, and
  the ``PromotionHttpObservation`` only; it MUST never be used as
  ``runId`` or be promoted into a domain identifier.

The single canonical request authority is
:class:`PromoteAlertSignalsRequest`. The HTTP context wraps it
directly so the client never reconstructs a second request.

The closed ``ScopedPromotionHttpTransportOutcome`` union is the
bounded set of HTTP transport shapes the scoped client may return.
``typing.assert_never`` is used at the consumer boundary so a
newly added variant cannot silently disappear from the dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.identifiers import AlertSignalId, HealthRunId
from ..incident_alert_promotion_binding import BoundScopedPromotionResult
from ..incident_alert_promotion_contract import PromoteAlertSignalsRequest
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
MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MiB bounded body cap


@dataclass(frozen=True, slots=True)
class ScopedPromotionHttpRequestContext:
    """Immutable, typed request context for one scoped promotion
    HTTP attempt.

    Distinct identities:

    * ``run_id`` -- domain promotion/run identity. Sent as ``runId``
      and copied into the downstream ``PromotionSucceeded.run_id``.
    * ``request_id`` -- one HTTP-attempt correlation identity. Only
      ever appears on the ``X-K9B-Promotion-Request-ID`` header, in
      ``PromotionHttpObservation``, and in structured transport
      events; never on a domain outcome.

    The canonical :class:`PromoteAlertSignalsRequest` is the SINGLE
    request authority. The client MUST NOT reconstruct a second
    request from the convenience properties below.
    """

    request: PromoteAlertSignalsRequest
    request_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, PromoteAlertSignalsRequest):
            raise TypeError(
                "ScopedPromotionHttpRequestContext.request MUST be a "
                "PromoteAlertSignalsRequest"
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

    @property
    def run_id(self) -> HealthRunId:
        return self.request.run_id

    @property
    def source_identity(self) -> str:
        return self.request.source_identity

    @property
    def signal_ids(self) -> tuple[AlertSignalId, ...]:
        return self.request.signal_ids


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
    "MAX_RESPONSE_BYTES",
    "MAX_SIGNAL_IDS",
    "MAX_SOURCE_IDENTITY_LENGTH",
    "ScopedPromotionHttpRequestContext",
    "ScopedPromotionHttpSucceeded",
    "ScopedPromotionHttpTransportOutcome",
]
