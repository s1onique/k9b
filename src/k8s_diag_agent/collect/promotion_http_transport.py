"""Typed HTTP transport algebra for the backend promotion path.

ACT-K9B-HULK-PROMOTION-AMBIGUOUS-RESPONSE-TRANSPORT-TRUTH01-LOCAL-CONTRACT01.

This module introduces a closed, immutable typed observation for the
HTTP request / response boundary of the backend promotion path. The
observation replaces the prior ``Exception`` / free-form string
discriminant with bounded enums and a frozen dataclass so every
known transport shape has a typed home and ``AMBIGUOUS_RESPONSE`` is
no longer used as the catch-all bucket for known cases.

The closed union ``PromotionHttpTransportOutcome`` (a discriminated
union over typed variant dataclasses) carries the bounded HTTP
facts. The mapping layer
(:func:`map_promotion_http_transport_to_outcome`) projects every
known shape onto the typed ``PromotionOutcome`` so the selection
handoff from the prior correction cycle (``dec9592a`` /
``dd8886cf`` / ``b2637197``) receives an authoritative typed input.

Out of scope:

* Harbor credentials / image publication;
* Kubernetes / ``kubectl`` access;
* live response capture from the production cluster.

The HTTP observations are immutable and bounded: only metadata is
carried, never the response body.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------


class RequestTransmissionState(StrEnum):
    """Stage at which the request transmission completed.

    The discriminator mirrors the natural lifecycle of an HTTP
    request. ``NOT_STARTED`` covers the pre-send branch (DNS,
    connect refused, TLS handshake); ``HEADERS_SENT`` and
    ``DISPATCH_STARTED_TRANSMISSION_UNKNOWN`` is the conservative
    post-send state when ``urllib`` cannot prove the body reached
    the backend. ``HEADERS_SENT`` is reserved for instrumented
    transport seams that can prove flush.
    """

    NOT_STARTED = "not_started"
    HEADERS_SENT = "headers_sent"
    DISPATCH_STARTED_TRANSMISSION_UNKNOWN = "dispatch_started_transmission_unknown"
    RESPONSE_STARTED = "response_started"
    RESPONSE_COMPLETED = "response_completed"


class PromotionResponseDecodingStage(StrEnum):
    """Where the response decoder gave up (or completed).

    The closed union is consumed verbatim by the mapping layer so
    the discriminator is never a free-form exception string.
    """

    NOT_ATTEMPTED = "not_attempted"
    EMPTY_BODY = "empty_body"
    JSON_DECODE = "json_decode"
    WIRE_SCHEMA = "wire_schema"
    COMPLETED = "completed"


# ---------------------------------------------------------------------------
# Stable bounded reason codes for transport failures.
# ---------------------------------------------------------------------------


class PromotionHttpTransportReasonCode(StrEnum):
    """Closed transport-shape codes replacing the ``AMBIGUOUS_RESPONSE`` catch-all.

    ``AMBIGUOUS_RESPONSE`` is intentionally NOT in this enum. The
    prior ACT's catch-all bucket is retained as a final invariant
    violation fallback in the classifier but no longer used as an
    ordinary outcome for a known transport shape.
    """

    HTTP_ACCEPTED_WITHOUT_RESULT = "HTTP_ACCEPTED_WITHOUT_RESULT"
    HTTP_NO_CONTENT_AFTER_SEND = "HTTP_NO_CONTENT_AFTER_SEND"
    HTTP_EMPTY_SUCCESS_BODY = "HTTP_EMPTY_SUCCESS_BODY"
    HTTP_INVALID_JSON = "HTTP_INVALID_JSON"
    HTTP_INVALID_SCHEMA = "HTTP_INVALID_SCHEMA"
    HTTP_RESPONSE_TRUNCATED = "HTTP_RESPONSE_TRUNCATED"
    HTTP_READ_TIMEOUT_AFTER_SEND = "HTTP_READ_TIMEOUT_AFTER_SEND"
    HTTP_CONNECTION_LOST_AFTER_SEND = "HTTP_CONNECTION_LOST_AFTER_SEND"
    HTTP_FAILURE_BEFORE_SEND = "HTTP_FAILURE_BEFORE_SEND"
    UNEXPECTED_CLIENT_RESULT = "UNEXPECTED_CLIENT_RESULT"
    HTTP_ERROR_VALID_RESULT = "HTTP_ERROR_VALID_RESULT"


# ---------------------------------------------------------------------------
# Immutable HTTP observation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PromotionHttpObservation:
    """Immutable, bounded HTTP transport observation.

    Captures only metadata. The complete response body is never
    carried. The SHA-256 is computed over the bounded bytes actually
    received so the operator can correlate scheduler and backend
    evidence without leaking the payload.
    """

    request_id: str
    request_transmission: RequestTransmissionState
    status_code: int | None
    content_type: str | None
    declared_content_length: int | None
    response_byte_count: int
    response_body_sha256: str | None
    decoding_stage: PromotionResponseDecodingStage
    elapsed_milliseconds: int

    def to_event_dict(self) -> dict[str, object]:
        """Return a JSON-safe dict for structured event projection."""
        return {
            "request_id": self.request_id,
            "request_transmission": self.request_transmission.value,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "declared_content_length": self.declared_content_length,
            "response_byte_count": self.response_byte_count,
            "response_body_sha256": self.response_body_sha256,
            "decoding_stage": self.decoding_stage.value,
            "elapsed_milliseconds": self.elapsed_milliseconds,
        }


def compute_response_sha256(body: bytes | None) -> str | None:
    """Compute a bounded SHA-256 over a response body, or ``None`` if empty."""
    if not body:
        return None
    return hashlib.sha256(body).hexdigest()


# ---------------------------------------------------------------------------
# Closed transport outcome variants
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PromotionHttpSucceeded:
    """2xx response with a valid wire result (authoritative success)."""

    observation: PromotionHttpObservation
    raw_payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class PromotionHttpAccepted:
    """``202 Accepted`` response without an authoritative completion result.

    Per the contract, ``202`` after a mutating request means the
    backend acknowledged the request but did not prove the commit
    completed. The scheduler MUST treat this as genuinely uncertain.
    """

    observation: PromotionHttpObservation


@dataclass(frozen=True, slots=True)
class PromotionHttpNoContent:
    """``204 No Content`` response after a mutating request.

    The backend acknowledged the request but returned no payload.
    The scheduler MUST NOT interpret this as successful zero.
    """

    observation: PromotionHttpObservation


@dataclass(frozen=True, slots=True)
class PromotionHttpRejected:
    """Definite server rejection before any commit could happen."""

    observation: PromotionHttpObservation
    body_excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionHttpInvalidJson:
    """Response completed but the body failed to decode as JSON."""

    observation: PromotionHttpObservation
    body_excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionHttpInvalidSchema:
    """Response decoded as JSON but failed wire-schema validation."""

    observation: PromotionHttpObservation
    schema_error: str | None = None


@dataclass(frozen=True, slots=True)
class PromotionHttpTransportFailureBeforeSend:
    """Transport failed before the request was transmitted.

    DNS failure, connection refused, TLS handshake failure, connect
    timeout. ``may_have_committed`` MUST be ``False``.
    """

    observation: PromotionHttpObservation
    reason_code: PromotionHttpTransportReasonCode


@dataclass(frozen=True, slots=True)
class PromotionHttpTransportFailureAfterSend:
    """Transport failed after the request body was transmitted.

    Read timeout after body send, connection lost after body send,
    response truncation. ``may_have_committed`` MUST be ``True``.
    """

    observation: PromotionHttpObservation
    reason_code: PromotionHttpTransportReasonCode


@dataclass(frozen=True, slots=True)
class PromotionHttpResponseTruncated:
    """The response body exceeded the bounded reader limit.

    ``may_have_committed`` is ``True``: the backend may have committed
    but the response was truncated and cannot be classified.
    """

    observation: PromotionHttpObservation


# Closed union of all known transport shapes.
PromotionHttpTransportOutcome = (
    PromotionHttpSucceeded
    | PromotionHttpAccepted
    | PromotionHttpNoContent
    | PromotionHttpRejected
    | PromotionHttpInvalidJson
    | PromotionHttpInvalidSchema
    | PromotionHttpTransportFailureBeforeSend
    | PromotionHttpTransportFailureAfterSend
    | PromotionHttpResponseTruncated
)


def transport_outcome_kind(outcome: PromotionHttpTransportOutcome) -> str:
    """Return the closed variant name for structured event projection."""
    return type(outcome).__name__


def transport_reason(outcome: PromotionHttpTransportOutcome) -> str | None:
    """Return the bounded reason code when the outcome carries one."""
    if isinstance(outcome, PromotionHttpTransportFailureBeforeSend | PromotionHttpTransportFailureAfterSend):
        return outcome.reason_code.value
    return None


def may_have_committed_from_transport(
    outcome: PromotionHttpTransportOutcome,
) -> bool:
    """Project ``may_have_committed`` from the closed transport union.

    The projection is exact and exhaustive over the union. Any new
    variant MUST be added here AND in the consumer that derives
    ``may_have_committed``.
    """
    # ``as_dict`` would be circular; explicit isinstance for clarity.
    if isinstance(outcome, PromotionHttpTransportFailureBeforeSend):
        return False
    if isinstance(
        outcome,
        (
            PromotionHttpSucceeded,
            PromotionHttpAccepted,
            PromotionHttpNoContent,
            PromotionHttpInvalidJson,
            PromotionHttpInvalidSchema,
            PromotionHttpTransportFailureAfterSend,
            PromotionHttpResponseTruncated,
        ),
    ):
        return True
    # ``PromotionHttpRejected`` is a definite pre-commit rejection:
    # the backend proved no commit happened.
    if isinstance(outcome, PromotionHttpRejected):
        return False
    raise TypeError(
        "may_have_committed_from_transport received an unhandled "
        f"variant: {type(outcome).__name__!r}"
    )
