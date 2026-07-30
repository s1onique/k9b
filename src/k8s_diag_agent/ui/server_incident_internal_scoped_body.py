"""Bounded body-read algebra for the scoped HTTP seam.

ACT-K9B-HULK-PROMOTION-SCOPED-DISPATCH-ACTIVATION-AND-CERTAINTY01.

The body reader produces one of the closed result variants below;
it NEVER returns a silently truncated prefix as complete input.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from k8s_diag_agent.collect.promotion_scoped_http_seam import MAX_RESPONSE_BYTES


class ScopedBodyReadReasonCode(StrEnum):
    """Closed body-read reason codes used outside the body reader.

    New variants that need closed type inference are added to
    :class:`ScopedBodyReadReason` so the reader can carry the
    typed reason into the transport outcome.
    """

    BODY_READ_LIMIT_EXCEEDED = "HTTP_RESPONSE_BODY_LIMIT_EXCEEDED"
    BODY_READ_SHORT = "HTTP_RESPONSE_SHORT_READ"
    BODY_READ_FAILED = "HTTP_RESPONSE_READ_FAILED"


class ScopedBodyReadReason(StrEnum):
    """Closed body-read failure reason vocabulary.

    Used when the body reader observed a read failure AFTER the
    response headers were received. The reader classifies the
    underlying ``OSError`` into one of the closed values below
    so the transport mapper can do exhaustive matching against
    :class:`ScopedReadFailureReason`.
    """

    TIMEOUT = "timeout"
    CONNECTION_LOST = "connection_lost"
    TRANSMISSION_UNKNOWN = "transmission_unknown"


@dataclass(frozen=True, slots=True)
class ScopedBodyReadResult:
    """Closed body-read result.

    Exactly one of the variant sub-dataclasses is returned; consumers
    must narrow on the concrete type rather than on a generic shape.
    """

    received: bytes
    declared_content_length: int | None
    actual_byte_count: int
    body_sha256: str | None


def _is_completely_consumed(received: bytes) -> bool:
    """``urllib`` returns ``b""`` when the body is fully drained.

    ``read(n)`` returns up to ``n`` bytes; calling ``read(n)`` again
    after a complete body returns ``b""``. The bounded reader below
    relies on this contract to detect "short read".
    """
    return received == b""


@dataclass(frozen=True, slots=True)
class ScopedBodyReadComplete(ScopedBodyReadResult):
    """Body was fully consumed within the bounded cap."""


@dataclass(frozen=True, slots=True)
class ScopedBodyReadLimitExceeded:
    """Body exceeded ``MAX_RESPONSE_BYTES``.

    The body is NOT returned to consumers -- the wire bytes are
    dropped to prevent silent truncation masquerading as a complete
    payload.
    """

    declared_content_length: int | None
    actual_byte_count: int
    body_sha256: str


@dataclass(frozen=True, slots=True)
class ScopedBodyReadShort:
    """Server declared ``Content-Length`` larger than the bytes received."""

    received: bytes
    declared_content_length: int
    actual_byte_count: int
    body_sha256: str | None


@dataclass(frozen=True, slots=True)
class ScopedBodyReadFailed:
    """Read raised after response headers were received.

    No body bytes are returned; ``declared_content_length`` and
    ``body_sha256`` may be ``None`` because the read failed before
    any bounded bytes were captured. ``reason`` is a closed
    :class:`ScopedBodyReadReason` so the caller can build the
    correct scoped transport variant.
    """

    declared_content_length: int | None
    actual_byte_count: int = 0
    body_sha256: str | None = None
    reason: ScopedBodyReadReason = ScopedBodyReadReason.TRANSMISSION_UNKNOWN


def _classify_body_read_failure_reason(exc: BaseException) -> ScopedBodyReadReason:
    """Classify a body-read failure into the closed reason vocabulary.

    ``TimeoutError`` is a separate type in Python 3.11+; treated
    as TIMEOUT. ``ConnectionError`` (a base class whose
    subclasses include ``ConnectionResetError``,
    ``ConnectionAbortedError``, and ``BrokenPipeError``) maps to
    CONNECTION_LOST. Everything else is TRANSMISSION_UNKNOWN.
    """
    if isinstance(exc, TimeoutError):
        return ScopedBodyReadReason.TIMEOUT
    if isinstance(exc, ConnectionError):
        return ScopedBodyReadReason.CONNECTION_LOST
    return ScopedBodyReadReason.TRANSMISSION_UNKNOWN


def read_scoped_body(
    response: Any,
    *,
    declared_content_length: int | None,
) -> (
    ScopedBodyReadComplete
    | ScopedBodyReadLimitExceeded
    | ScopedBodyReadShort
    | ScopedBodyReadFailed
):
    """Read a bounded body from ``response`` and classify the result.

    Reads up to ``MAX_RESPONSE_BYTES + 1`` to detect overflow. The
    ``+1`` overshoot is the canonical "limit exceeded" probe; it is
    never returned as a truncated prefix.
    """
    if declared_content_length is not None and declared_content_length > MAX_RESPONSE_BYTES:
        # Server declared more than the bounded cap. The body is
        # unreadable for our purposes; do not call ``read`` at all
        # because it would block or stream a huge response.
        return ScopedBodyReadLimitExceeded(
            declared_content_length=declared_content_length,
            actual_byte_count=0,
            body_sha256="",
        )

    try:
        chunk = response.read(MAX_RESPONSE_BYTES + 1)
    except (TimeoutError, ConnectionError, OSError) as exc:
        return ScopedBodyReadFailed(
            declared_content_length=declared_content_length,
            actual_byte_count=0,
            body_sha256=None,
            reason=_classify_body_read_failure_reason(exc),
        )

    if len(chunk) > MAX_RESPONSE_BYTES:
        # The body exceeds the bounded cap. Drop the chunk and
        # hash the bounded prefix only for diagnostic correlation;
        # never return the chunk to consumers as if it were
        # complete.
        return ScopedBodyReadLimitExceeded(
            declared_content_length=declared_content_length,
            actual_byte_count=MAX_RESPONSE_BYTES,
            body_sha256=hashlib.sha256(chunk[:MAX_RESPONSE_BYTES]).hexdigest(),
        )

    actual_byte_count = len(chunk)
    body_sha256: str | None
    if chunk:
        body_sha256 = hashlib.sha256(chunk).hexdigest()
    else:
        body_sha256 = None

    if declared_content_length is not None and declared_content_length > actual_byte_count:
        return ScopedBodyReadShort(
            received=chunk,
            declared_content_length=declared_content_length,
            actual_byte_count=actual_byte_count,
            body_sha256=body_sha256,
        )

    return ScopedBodyReadComplete(
        received=chunk,
        declared_content_length=declared_content_length,
        actual_byte_count=actual_byte_count,
        body_sha256=body_sha256,
    )


def safe_excerpt(body: bytes, *, limit: int = 256) -> str:
    """Deprecated: returns an empty string.

    The active scoped path MUST NOT retain or log response-body
    text. The dispatcher projects bounded stable reason/disposition
    fields only.
    """
    return ""


__all__ = [
    "ScopedBodyReadComplete",
    "ScopedBodyReadFailed",
    "ScopedBodyReadLimitExceeded",
    "ScopedBodyReadReason",
    "ScopedBodyReadReasonCode",
    "ScopedBodyReadResult",
    "ScopedBodyReadShort",
    "read_scoped_body",
    "safe_excerpt",
]


# Silence unused-import warning for Mapping -- kept for future body
# decoding helpers that may want a typed view of the response.
_ = Mapping
