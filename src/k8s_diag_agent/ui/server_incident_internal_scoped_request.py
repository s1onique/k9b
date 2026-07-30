"""Request construction for the scoped HTTP seam.

ACT-K9B-HULK-PROMOTION-SCOPED-HTTP-CLIENT-RESPONSIBILITY-SPLIT01.

Owns the canonical wire request construction: serialisation of
the immutable :class:`PromoteAlertSignalsRequest`, the
correlation header, and the transport ``http`` envelope.

Identity ownership:

* ``run_id`` (domain) is sent as ``runId`` on the wire;
* ``source_identity`` (domain) is sent as ``sourceIdentity``;
* ``signal_ids`` (domain) is sent as ``signalIds``;
* ``request_id`` is the transport correlation identity and is
  sent only on the ``X-K9B-Promotion-Request-ID`` header. It
  MUST NEVER appear in the request body.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from typing import cast

from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedPromotionHttpRequestContext,
)

# Canonical correlation header. The downstream backend
# ``server_incident_internal_handlers`` reads the same header
# to extract the correlation identity; the client-side
# ``ScopedSchedulerClient`` writes it on every outbound request.
REQUEST_ID_HEADER = "X-K9B-Promotion-Request-ID"


def _serialize_request_body(context: ScopedPromotionHttpRequestContext) -> bytes:
    """Serialise the canonical ``PromoteAlertSignalsRequest`` to JSON bytes.

    The request body MUST contain only the domain identifiers
    (run_id, source_identity, signal_ids). The transport
    ``request_id`` MUST NOT appear here -- it is the
    correlation identity that lives on the
    ``X-K9B-Promotion-Request-ID`` header only.
    """
    return json.dumps(context.request.to_wire_dict()).encode("utf-8")


def build_scoped_request(
    context: ScopedPromotionHttpRequestContext,
    *,
    url: str,
    token: str,
) -> urllib.request.Request:
    """Build the canonical urllib request for the scoped promotion path.

    The headers carry:

    * ``Content-Type: application/json``;
    * ``Authorization: Bearer <token>``;
    * ``X-K9B-Promotion-Request-ID: <request_id>``.

    The body is the canonical wire serialisation of the
    ``PromoteAlertSignalsRequest`` -- the transport
    ``request_id`` is never serialised into the body.
    """
    body = _serialize_request_body(context)
    return urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            REQUEST_ID_HEADER: context.request_id,
        },
        method="POST",
    )


def declared_content_length(headers: object) -> int | None:
    """Best-effort ``Content-Length`` header extraction.

    Used by the bounded body reader to honour the
    ``Content-Length`` short-read detection even when the
    underlying ``HTTPMessage``-shaped object does not
    expose a typed accessor.
    """
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    raw = getter("Content-Length")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def content_type(headers: object) -> str | None:
    """Best-effort ``Content-Type`` header extraction."""
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    typed_getter = cast(Callable[[str], object], getter)
    raw = typed_getter("Content-Type")
    if raw is None:
        return None
    return str(raw)


__all__ = [
    "REQUEST_ID_HEADER",
    "build_scoped_request",
    "content_type",
    "declared_content_length",
]
