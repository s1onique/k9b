"""Exception classification for the scoped HTTP seam.

ACT-K9B-HULK-PROMOTION-SCOPED-HTTP-CLIENT-RESPONSIBILITY-SPLIT01.

Owns the typed ``URLError`` classification. The active typed
path does NOT inspect exception message text -- it walks the
:class:`urllib.error.URLError` ``reason`` chain to the
concrete ``OSError`` subclass and projects the result onto
the closed :class:`ScopedBeforeSendFailureReason` or
:class:`ScopedDispatchUncertaintyReason` vocabulary via
:class:`isinstance`.

The ``TimeoutError`` / ``ConnectionError`` / generic
``OSError`` cases are handled directly by the executor
because they do not carry a ``reason`` chain to walk.
"""

from __future__ import annotations

import socket
import ssl
import urllib.error

from k8s_diag_agent.collect.promotion_scoped_http_seam import (
    ScopedBeforeSendFailureReason,
    ScopedDispatchUncertaintyReason,
)

__all__ = ["classify_url_error_reason"]


def classify_url_error_reason(
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
