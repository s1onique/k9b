"""Implementation helpers for server.py compatibility wrappers.

This module contains the actual implementation logic for compatibility wrappers
that must live in server.py to preserve the server.emit_structured_log patch point.
The `_with_emit` functions accept an injectable emit_fn parameter.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------
# Access-log implementation helper
# --------------------------------------------------------------------


def _log_request_access_with_emit(
    emit_fn: Any,
    slow_request_threshold_ms: float,
    method: str,
    path: str,
    query: str,
    status_code: int,
    duration_ms: float,
    response_bytes: int,
    client_ip: str,
    run_label: str = "",
    is_static_asset: bool = False,
    request_id: str = "",
    route_return_ms: float = 0.0,
    client_request_id: str = "",
) -> None:
    """Access-log implementation helper.

    This function accepts an injectable emit_fn to preserve test mock
    compatibility via the server.emit_structured_log patch point.

    Args:
        emit_fn: The emit_structured_log function (injected by caller).
        slow_request_threshold_ms: Threshold in ms above which request is "slow".
        method: HTTP method (GET, POST, etc.)
        path: Request path (e.g., /api/run)
        query: Query string (e.g., run_id=abc)
        status_code: HTTP response status code
        duration_ms: Request handling duration in milliseconds
        response_bytes: Response body size in bytes
        client_ip: Client IP address
        run_label: Run label when known, else empty string
        is_static_asset: Whether this is a static asset request
        request_id: Correlation ID for linking access log to route timing logs
        route_return_ms: Time from request start to route handler returning (before send)
        client_request_id: Client-generated request ID from X-K9B-Client-Request-Id header
    """
    from .server_runtime import _log_request_access_with_emit as _impl

    _impl(
        emit_fn=emit_fn,
        slow_request_threshold_ms=slow_request_threshold_ms,
        method=method,
        path=path,
        query=query,
        status_code=status_code,
        duration_ms=duration_ms,
        response_bytes=response_bytes,
        client_ip=client_ip,
        run_label=run_label,
        is_static_asset=is_static_asset,
        request_id=request_id,
        route_return_ms=route_return_ms,
        client_request_id=client_request_id,
    )


# --------------------------------------------------------------------
# Single-flight implementation helpers
# --------------------------------------------------------------------


def _single_flight_acquire_with_emit(
    emit_fn: Any,
    key: str,
    request_path: str = "",
    cache_key: str = "",
) -> tuple[bool, tuple[object, list[Any]] | None, float]:
    """Single-flight acquire implementation helper.

    This function accepts an injectable emit_fn to preserve test mock
    compatibility via the server.emit_structured_log patch point.
    """
    from .server_singleflight import _single_flight_acquire_impl as _impl

    return _impl(
        emit_fn=emit_fn,
        key=key,
        request_path=request_path,
        cache_key=cache_key,
    )


def _single_flight_release_with_emit(
    emit_fn: Any,
    key: str,
    result: object,
    success: bool = True,
    result_type: str = "built",
) -> None:
    """Single-flight release implementation helper.

    This function accepts an injectable emit_fn to preserve test mock
    compatibility via the server.emit_structured_log patch point.
    """
    from .server_singleflight import _single_flight_release_impl as _impl

    return _impl(
        emit_fn=emit_fn,
        key=key,
        result=result,
        success=success,
        result_type=result_type,
    )
