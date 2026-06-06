"""api_runtime_status.py - API payload builder for runtime status.

IMPORTANT: This is a FRONTEND SCAFFOLD implementation.
The backend currently returns placeholder unavailable data (None values).
Real log counting and PVC extraction is deferred until backend data sources are available.

This module builds the runtime status payload for the /api/runtime-status endpoint.
It is a read-only observability projection derived from cluster data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .model_runtime_status import (
    LogWindowCounts,
    LogWindows,
    PodLogWindows,
    PvcUsage,
    RuntimeStatusPayload,
)

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)

# Backend and scheduler pod names for log queries
_BACKEND_POD_NAMES = frozenset({"k9b-backend", "backend", "k9b-backend-0"})
_SCHEDULER_POD_NAMES = frozenset({"k9b-scheduler", "scheduler", "k9b-scheduler-0"})

# Non-info log severities only
_NON_INFO_SEVERITIES = frozenset({"ERROR", "WARNING"})


def build_runtime_status_payload(runs_dir: Path) -> RuntimeStatusPayload:
    """Build the runtime status payload from cluster data.

    This is a read-only observability projection. No data transformation
    is performed; the frontend should only render.

    Args:
        runs_dir: Path to the runs directory containing health data

    Returns:
        RuntimeStatusPayload with log counts and PVC usage
    """
    # Build log windows from cluster snapshots if available
    log_windows = _build_log_windows_from_snapshots(runs_dir)

    # Build PVC usage from cluster snapshots if available
    backend_pvc = _build_pvc_usage_from_snapshots(runs_dir)

    return RuntimeStatusPayload(
        log_windows=log_windows,
        backend_pvc=backend_pvc,
    )


def _build_log_windows_from_snapshots(runs_dir: Path) -> LogWindows:
    """Build log window counts from cluster snapshots.

    This function attempts to count ERROR and WARNING log lines from
    backend and scheduler pods across sliding time windows.

    If snapshot data is unavailable, values will be None (unavailable).
    If data is present but counts are zero, values will be 0 (explicit zero).

    Args:
        runs_dir: Path to the runs directory

    Returns:
        LogWindows with counts for backend and scheduler pods
    """
    # Placeholder implementation - return unavailable state
    # In a full implementation, this would:
    # 1. Load cluster snapshots from runs_dir
    # 2. For each snapshot, find backend/scheduler pods
    # 3. Count ERROR and WARNING log lines in sliding windows
    # 4. Aggregate counts across snapshots

    # Return unavailable state (None values) for now
    # This allows the frontend to distinguish between:
    # - unavailable data (None) - "backend: unavailable"
    # - zero counts (0) - "0 error / 0 warning"
    return LogWindows(
        backend=PodLogWindows(
            m5=LogWindowCounts(warning=None, error=None),
            m10=LogWindowCounts(warning=None, error=None),
            m15=LogWindowCounts(warning=None, error=None),
        ),
        scheduler=PodLogWindows(
            m5=LogWindowCounts(warning=None, error=None),
            m10=LogWindowCounts(warning=None, error=None),
            m15=LogWindowCounts(warning=None, error=None),
        ),
    )


def _build_pvc_usage_from_snapshots(runs_dir: Path) -> PvcUsage | None:
    """Build PVC usage from cluster snapshots.

    This function attempts to get storage usage for the backend PVC
    from cluster snapshots.

    Args:
        runs_dir: Path to the runs directory

    Returns:
        PvcUsage if data is available, None otherwise
    """
    # Placeholder implementation - return None (unavailable)
    # In a full implementation, this would:
    # 1. Load cluster snapshots from runs_dir
    # 2. Find PVCs with backend-related names
    # 3. Extract capacity, used, and free bytes
    # 4. Calculate used_percent

    # Return unavailable state (None values) for now
    # The frontend will render this as "unavailable"
    return PvcUsage(
        name="backend-data",
        used_bytes=None,
        free_bytes=None,
        capacity_bytes=None,
        used_percent=None,
    )


def handle_runtime_status_route(handler: HealthUIRequestHandler) -> None:
    """Handle GET /api/runtime-status route.

    Args:
        handler: The HTTP request handler instance
    """
    try:
        payload = build_runtime_status_payload(handler.runs_dir)
        handler._send_json(payload.to_dict())
    except (ValueError, RuntimeError) as exc:
        logger.warning("Failed to build runtime status payload", extra={"error": str(exc)})
        # Return empty payload on error (frontend will show unavailable)
        payload = RuntimeStatusPayload(
            log_windows=LogWindows(
                backend=PodLogWindows(
                    m5=LogWindowCounts(warning=None, error=None),
                    m10=LogWindowCounts(warning=None, error=None),
                    m15=LogWindowCounts(warning=None, error=None),
                ),
                scheduler=PodLogWindows(
                    m5=LogWindowCounts(warning=None, error=None),
                    m10=LogWindowCounts(warning=None, error=None),
                    m15=LogWindowCounts(warning=None, error=None),
                ),
            ),
            backend_pvc=None,
        )
        handler._send_json(payload.to_dict())
