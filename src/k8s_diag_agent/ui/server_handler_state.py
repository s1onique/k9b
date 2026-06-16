"""Handler state and access-log helpers extracted from server.py.

This module contains per-request state management and access logging helpers
used by HealthUIRequestHandler. These helpers operate on handler instance state
and can be called as thin wrappers from the handler class.

Extracted from server.py:
- Per-request state reset
- Access log completion
- Request timing correlation
- Client IP extraction
- Run label extraction

These helpers are self-contained and depend on HealthUIRequestHandler instance state.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


def reset_request_state(handler: BaseHTTPRequestHandler) -> None:
    """Reset all per-request state to measure actual request processing time.

    This must be called at the start of each do_GET/do_POST to ensure
    duration_ms reflects request processing, not connection idle time.

    Args:
        handler: HealthUIRequestHandler instance with _start_time, _request_id,
                 _route_return_ms, _response_bytes, _status_code attributes.
    """
    handler._start_time = time.perf_counter()
    handler._request_id = ""
    handler._route_return_ms = 0.0
    handler._response_bytes = 0
    handler._status_code = 200


def get_client_ip(handler: BaseHTTPRequestHandler) -> str:
    """Extract client IP from request.

    Args:
        handler: HealthUIRequestHandler instance with headers and client_address.

    Returns:
        Client IP address string.
    """
    # Check for forwarded headers (reverse proxy)
    forwarded = handler.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP in the chain
        return forwarded.split(",")[0].strip()
    # Fall back to direct connection
    client = handler.client_address
    if isinstance(client, tuple):
        return client[0]
    return str(client)


def get_run_label(handler: Any) -> str:
    """Extract run_label from the current context if available.

    Args:
        handler: HealthUIRequestHandler instance with _load_context method.

    Returns:
        Run label string if available, empty string otherwise.
    """
    # Try to get run_label from the loaded context
    # This is a best-effort attempt; if context can't be loaded, return empty
    try:
        context = handler._load_context()
        if context and context.run:
            return context.run.run_label or ""
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError):
        # Narrowed: _load_context already handles file/JSON errors;
        # remaining candidates are simple attribute accesses
        pass
    return ""


def set_request_timing_state(
    handler: Any,
    request_id: str,
    route_return_ms: float,
) -> None:
    """Set correlation and timing info for access log.

    Called by server_reads.py after building the route payload but before
    sending the response. This allows the access log to include correlation
    IDs and route timing alongside the actual request duration.

    Args:
        handler: HealthUIRequestHandler instance with _request_id and _route_return_ms.
        request_id: Correlation ID for linking access log to route timing logs
        route_return_ms: Time from request start to route handler returning (before send)
    """
    handler._request_id = request_id
    handler._route_return_ms = route_return_ms


def log_access_completion(
    handler: Any,
    emit_fn: Any,
    slow_request_threshold_ms: float,
) -> None:
    """Log access completion with latency and status.

    This is the core access logging function. It accepts injectable emit_fn
    to preserve test mock compatibility via server.emit_structured_log patch point.

    CRITICAL: This function must never raise. If emit_fn fails, we must NOT
    propagate the exception because the caller (do_GET/do_POST) has a try/except
    that re-raises after calling this function. If this raises, send_error() is
    never called and the client gets RemoteDisconnected instead of a proper 500.
    """
    try:
        _log_access_completion_inner(handler, emit_fn, slow_request_threshold_ms)
    except Exception as exc:
        # NEVER let logging failures propagate - that would break the HTTP response
        # and turn deterministic 500s into RemoteDisconnected errors for clients.
        # At worst, we lose an access log. The client always gets a response.
        import sys

        print(f"access logging failed: {type(exc).__name__}: {exc}", file=sys.stderr)


def _log_access_completion_inner(
    handler: Any,
    emit_fn: Any,
    slow_request_threshold_ms: float,
) -> None:
    """Inner implementation of log_access_completion. Raises are NOT caught here."""
    if handler._start_time == 0.0:
        return

    duration_ms = (time.perf_counter() - handler._start_time) * 1000

    # Read client_request_id from request headers
    client_request_id = handler.headers.get("X-K9B-Client-Request-Id", "")

    # Build message
    method = handler._request_method
    path = handler._request_path
    query = handler._request_query
    status_code = handler._status_code
    response_bytes = handler._response_bytes
    request_id = handler._request_id
    route_return_ms = handler._route_return_ms

    # Determine severity based on status code and latency
    if status_code >= 500:
        severity = "ERROR"
    elif status_code >= 400:
        severity = "WARNING"
    elif duration_ms >= slow_request_threshold_ms:
        severity = "WARNING"
    elif handler._is_static:
        # Use DEBUG for static assets to reduce noise
        severity = "DEBUG"
    else:
        severity = "INFO"

    message = f"{method} {path}"
    if query:
        message += f"?{query}"

    metadata: dict[str, Any] = {
        "method": method,
        "path": path,
        "query": query,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "response_bytes": response_bytes,
        "client_ip": get_client_ip(handler),
        "run_label": get_run_label(handler) if path.startswith("/api/") else "",
    }

    # Add correlation fields if available
    if request_id:
        metadata["request_id"] = request_id
    if client_request_id:
        metadata["client_request_id"] = client_request_id
    if route_return_ms > 0:
        metadata["route_return_ms"] = round(route_return_ms, 2)
        # Compute network/flush overhead for debugging
        send_overhead = duration_ms - route_return_ms
        if send_overhead > 0:
            metadata["send_overhead_ms"] = round(send_overhead, 2)

    emit_fn(
        component="ui-access",
        message=message,
        severity=severity,
        run_label=metadata["run_label"],
        run_id="",
        metadata=metadata,
    )
