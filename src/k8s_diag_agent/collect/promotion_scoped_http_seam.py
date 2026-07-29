"""Typed HTTP seam for the canonical scoped current-run promotion path.

ACT-K9B-HULK-PROMOTION-SCOPED-TRANSPORT-MAPPING-TRUTH01-CORRECTION01.

This module owns the typed request context, the typed success
variant, the typed aggregate receipt (with construction-time
validation), the typed distinct body-read variants, the typed
authentication rejection variant, the bounded request fingerprint,
and the bounded HTTP observation for the scoped path.

Identity ownership:

* ``run_id`` -- domain promotion/run identity. Sent as ``runId``
  on the wire and copied into the bounded downstream outcome.
* ``request_id`` -- one HTTP-attempt correlation identity. Carried
  in transport logs, the ``X-K9B-Promotion-Request-ID`` header, and
  the ``PromotionHttpObservation`` only; it MUST never be used as
  ``runId`` or be promoted into a domain identifier.

The deterministic :func:`scoped_promotion_request_fingerprint`
computes a SHA-256 digest over the canonical request payload; two
attempts of the same promotion scope produce the same fingerprint
even when they carry different transport correlation ids. The
fingerprint is the deterministic half of
:class:`PromotionReconciliationToken` -- the request id is the
transport half.
"""

from __future__ import annotations

import hashlib
import json
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

_WIRE_CONTRACT_VERSION = "k9b.scoped.promotion.v1"
_REQUEST_FINGERPRINT_METHOD = "POST"
_REQUEST_FINGERPRINT_ENDPOINT = (
    "/api/internal/incidents/promote-alert-signals"
)


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
        if (
            not isinstance(self.request.source_identity, str)
            or not self.request.source_identity
            or len(self.request.source_identity) > MAX_SOURCE_IDENTITY_LENGTH
        ):
            raise ValueError(
                "ScopedPromotionHttpRequestContext.source_identity MUST "
                f"be a non-empty string bounded by {MAX_SOURCE_IDENTITY_LENGTH}"
            )
        if not self.request.signal_ids:
            raise ValueError(
                "ScopedPromotionHttpRequestContext.signal_ids MUST be "
                "non-empty"
            )
        if len(self.request.signal_ids) > MAX_SIGNAL_IDS:
            raise ValueError(
                "ScopedPromotionHttpRequestContext.signal_ids exceeds "
                f"maximum of {MAX_SIGNAL_IDS}"
            )
        if len(set(self.request.signal_ids)) != len(self.request.signal_ids):
            raise ValueError(
                "ScopedPromotionHttpRequestContext.signal_ids MUST be "
                "unique"
            )
        for signal_id in self.request.signal_ids:
            if not isinstance(signal_id, str):
                raise TypeError(
                    "ScopedPromotionHttpRequestContext.signal_ids entries "
                    "MUST be AlertSignalId (str-typed) instances"
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
    """Scoped transport outcome: 2xx with a valid bounded wire result."""
    observation: PromotionHttpObservation
    bound: BoundScopedPromotionResult


@dataclass(frozen=True, slots=True)
class ScopedPromotionHttpBodyLimitExceeded:
    """Body exceeded the bounded cap; the body is dropped."""
    observation: PromotionHttpObservation


@dataclass(frozen=True, slots=True)
class ScopedPromotionHttpShortRead:
    """Declared Content-Length exceeds the bytes actually received."""
    observation: PromotionHttpObservation


@dataclass(frozen=True, slots=True)
class ScopedPromotionHttpReadFailed:
    """Read raised after response headers were received."""
    observation: PromotionHttpObservation


@dataclass(frozen=True, slots=True)
class ScopedPromotionHttpAuthenticationRejected:
    """Backend returned ``401`` or ``403`` before promotion execution.

    A 401 / 403 from the authentication layer proves no promotion
    could have started, so this variant maps to ``PromotionRejected``
    with ``commit_disposition=D DEFINITELY_NOT_COMMITTED``.
    """
    observation: PromotionHttpObservation


@dataclass(frozen=True, slots=True)
class ScopedPromotionReceipt:
    """Aggregate scoped receipt held alongside the completed projection.

    The receipt is intrinsically authoritative: it holds exactly
    one :class:`BoundScopedPromotionResult` and every aggregate
    property derives from it. Consumers MUST NOT reconstruct
    copy-state by hand; the bound is the only source of truth.
    """

    bound: BoundScopedPromotionResult

    @property
    def requested_signal_ids(self) -> tuple[str, ...]:
        return tuple(
            str(signal_id) for signal_id in self.bound.request.signal_ids
        )

    @property
    def scanned_signal_ids(self) -> tuple[str, ...]:
        return tuple(
            str(signal_id) for signal_id in self.bound.result.scanned_signal_ids
        )

    @property
    def opened_incident_ids(self) -> tuple[str, ...]:
        return tuple(str(i) for i in self.bound.result.opened_incident_ids)

    @property
    def materially_changed_incident_ids(self) -> tuple[str, ...]:
        return tuple(
            str(i) for i in self.bound.result.materially_changed_incident_ids
        )

    @property
    def observation_refreshed_incident_ids(self) -> tuple[str, ...]:
        return tuple(
            str(i) for i in self.bound.result.observation_refreshed_incident_ids
        )

    @property
    def unchanged_incident_ids(self) -> tuple[str, ...]:
        return tuple(str(i) for i in self.bound.result.unchanged_incident_ids)

    @property
    def skipped_signal_ids(self) -> tuple[str, ...]:
        return tuple(
            str(signal_id)
            for signal_id in self.bound.result.skipped_signal_ids
        )

    @property
    def failure_count(self) -> int:
        return len(self.bound.result.failures)




def scoped_promotion_request_fingerprint(
    request: PromoteAlertSignalsRequest,
) -> str:
    """Stable SHA-256 fingerprint over the canonical request payload.

    The canonical byte representation is a length-prefixed,
    sorted-keyed JSON object containing:

    * wire contract version
    * HTTP method
    * endpoint path
    * ``runId``
    * ``sourceIdentity``
    * ordered ``signalIds`` (order matters: ``["a", "b"]`` and
      ``["b", "a"]`` produce different fingerprints so callers MUST
      preserve the request order)

    Two attempts of the same promotion scope (same runId,
    sourceIdentity, and ordered signalIds) produce the same
    fingerprint even when they carry different transport correlation
    ``request_id`` values.
    """
    wire = {
        "wire_contract_version": _WIRE_CONTRACT_VERSION,
        "method": _REQUEST_FINGERPRINT_METHOD,
        "endpoint": _REQUEST_FINGERPRINT_ENDPOINT,
        "runId": str(request.run_id),
        "sourceIdentity": request.source_identity,
        "signalIds": tuple(
            str(signal_id) for signal_id in request.signal_ids
        ),
    }
    canonical = json.dumps(
        wire, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# Closed union for the scoped HTTP transport surface.
ScopedPromotionHttpTransportOutcome = (
    ScopedPromotionHttpSucceeded
    | ScopedPromotionHttpAuthenticationRejected
    | ScopedPromotionHttpBodyLimitExceeded
    | ScopedPromotionHttpShortRead
    | ScopedPromotionHttpReadFailed
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
    "ScopedPromotionHttpAuthenticationRejected",
    "ScopedPromotionHttpBodyLimitExceeded",
    "ScopedPromotionHttpReadFailed",
    "ScopedPromotionHttpRequestContext",
    "ScopedPromotionHttpShortRead",
    "ScopedPromotionHttpSucceeded",
    "ScopedPromotionHttpTransportOutcome",
    "scoped_promotion_request_fingerprint",
]
