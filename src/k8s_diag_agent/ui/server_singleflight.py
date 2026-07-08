"""Single-flight coordination helpers for preventing duplicate concurrent cache builds.

This module provides acquire/release/wait semantics that allow multiple concurrent
requests for the same cache key to coordinate: one builds while others wait,
sharing the result.

All single-flight state lives in this module so that all callers share the same
in-flight map and lock.

Note: emit_fn injection is used to preserve the server.emit_structured_log patch point
for tests. Callers should use the wrappers in server.py for compatibility.
"""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any

# --------------------------------------------------------------------
# Shared single-flight state
# --------------------------------------------------------------------

# Single-flight locks to prevent duplicate concurrent builds for the same cache key.
# Key: cache key, Value: tuple of (event, result_holder list)
# result_holder: list with one element to hold the result when ready.
_single_flight_events: dict[str, tuple[object, list[Any]]] = {}
_single_flight_lock = Lock()


# --------------------------------------------------------------------
# Single-flight coordination (emit_fn injected by server.py wrappers)
# --------------------------------------------------------------------


def _single_flight_acquire_impl(
    *,
    emit_fn: Callable[..., Any],
    key: str,
    request_path: str = "",
    cache_key: str = "",
) -> tuple[bool, tuple[object, list[Any]] | None, float]:
    """Internal implementation of single-flight acquire with emit injection.

    Returns:
        Tuple of (should_build, result_holder_or_event, wait_start_time).
        - should_build=True means this caller should build the result
        - should_build=False means wait for the in-flight build and use its result
        - wait_start_time is the timestamp when waiting started (for measuring wait duration)
    """
    import time as time_module

    wait_start = time_module.perf_counter()
    with _single_flight_lock:
        if key in _single_flight_events:
            # There's already an in-flight request - return event to wait on.
            emit_fn(
                component="single-flight",
                message="Single-flight waiter acquiring",
                run_id="",
                run_label="",
                severity="DEBUG",
                metadata={
                    "single_flight_key": key[:100],
                    "acquire_result": "waiter",
                    "cache_key": cache_key[:100] if cache_key else "",
                    "request_path": request_path,
                },
            )
            return False, _single_flight_events[key], wait_start
        else:
            # Create new in-flight state.
            # result_holder: list with one element to hold result when ready.
            result_holder: list[Any] = [None]
            event = result_holder  # Use list as mutable container for result.
            _single_flight_events[key] = (event, result_holder)
            emit_fn(
                component="single-flight",
                message="Single-flight builder acquiring",
                run_id="",
                run_label="",
                severity="DEBUG",
                metadata={
                    "single_flight_key": key[:100],
                    "acquire_result": "builder",
                    "cache_key": cache_key[:100] if cache_key else "",
                    "request_path": request_path,
                },
            )
            return True, (event, result_holder), wait_start


def _single_flight_release_impl(
    *,
    emit_fn: Callable[..., Any],
    key: str,
    result: object,
    success: bool = True,
    result_type: str = "built",
) -> None:
    """Internal implementation of single-flight release with emit injection.

    Args:
        emit_fn: Structured logging function to use.
        key: The single-flight key.
        result: The result to store (can be None on failure).
        success: Whether the build succeeded - if False, also clean up the entry.
        result_type: Type of result - "built" (freshly built), "cached" (served from cache),
            "error" (build failed).
    """
    import logging
    import time as time_module

    logger = logging.getLogger(__name__)

    with _single_flight_lock:
        if key in _single_flight_events:
            event, result_holder = _single_flight_events[key]
            result_holder[0] = result  # Store result in the holder.

            # Give waiters a moment to read the result before cleaning up.
            # We keep the entry with a sentinel marker to indicate "ready".
            result_holder.append("_READY_")  # Marker to indicate result is ready.

            # Brief delay to allow waiters to pick up the result (max 50ms).
            time_module.sleep(0.005)  # 5ms to let waiters wake up and read.

            # Now delete to allow retries after waiters have had a chance.
            del _single_flight_events[key]

            emit_fn(
                component="single-flight",
                message="Single-flight released",
                run_id="",
                run_label="",
                severity="DEBUG",
                metadata={
                    "single_flight_key": key[:100],
                    "release_success": success,
                    "result_type": result_type,
                },
            )

            logger.debug(
                f"Single-flight released for key: {key[:50]}...",
                extra={"key": key[:100], "action": "release", "success": success},
            )


def _single_flight_wait(
    event_holder: tuple[object, list[Any]],
    wait_start: float,
) -> tuple[object | None, float]:
    """Wait for single-flight result to be ready.

    Note: This function does not emit structured logs, so no emit_fn injection needed.

    Args:
        event_holder: Tuple of (event, result_holder) from _single_flight_acquire.
        wait_start: Timestamp when waiting started (from _single_flight_acquire).

    Returns:
        Tuple of (result, wait_duration_ms).
    """
    import time as time_module

    # Brief spin-wait for result (max ~100ms).
    # Check for both result[0] being non-None AND the _READY_ marker.
    for _i in range(10):
        time_module.sleep(0.01)
        result_holder = event_holder[1]
        # Check if result is ready: either marker present or result is not None.
        if len(result_holder) >= 2 and result_holder[-1] == "_READY_":
            # Result is ready, return it.
            wait_duration_ms = (time_module.perf_counter() - wait_start) * 1000
            return result_holder[0], wait_duration_ms
        if result_holder[0] is not None:
            # Fallback: result was set but marker not yet added (race condition).
            wait_duration_ms = (time_module.perf_counter() - wait_start) * 1000
            return result_holder[0], wait_duration_ms

    # If still not ready, return None (caller will handle).
    wait_duration_ms = (time_module.perf_counter() - wait_start) * 1000
    return None, wait_duration_ms


# --------------------------------------------------------------------
# Run-payload cache state
# --------------------------------------------------------------------

# In-memory cache for run payloads to avoid repeated expensive computation.
# Key: (run_id, ui_index_mtime), Value: (cached_payload, cached_promotions).
_run_payload_cache: dict[tuple[str, float], tuple[dict[str, Any], list[dict[str, object]]]] = {}
_run_payload_cache_lock = Lock()


# --------------------------------------------------------------------
# Notifications cache state
# --------------------------------------------------------------------

# In-memory cache for notifications - keyed by (notifications_dir_mtime, query_params).
# This avoids scanning all notification files on every request.
_notifications_cache: dict[str, tuple[dict[str, Any], float]] = {}  # key -> (payload, mtime)
_notifications_cache_lock = Lock()
