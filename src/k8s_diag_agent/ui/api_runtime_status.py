"""api_runtime_status.py - API payload builder for runtime status.

This module builds the runtime status payload for the /api/runtime-status endpoint.
It is a read-only observability projection derived from backend log and cluster data.

Data sources:
- Log severity counts: runs/health/health.log (structured JSON health-loop log)
  - Counts ERROR and WARNING entries in sliding 5/10/15-minute windows
  - WARNING/error fields for both "backend" and "scheduler" are populated from the SAME
    shared health operational log source. These are NOT pod-specific backend/scheduler
    log extracts. They represent aggregate operational health from the health loop.
    Until per-pod/component log extraction is implemented, both fields show identical
    counts derived from the global health.log.
- PVC usage: Filesystem stats via os.statvfs() on configured mount paths
  - backend-data: /app/runs (PVC mount path)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
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

# Non-info log severities to count
_NON_INFO_SEVERITIES = frozenset({"ERROR", "WARNING"})

# Health log path relative to runs directory
_HEALTH_LOG_PATH = Path("health") / "health.log"

# PVC name to mount path mapping for Runtime Status
# Maps PVC names to their local mount paths in the backend pod.
# The backend pod mounts the PVC at the configured mountPath, so we can
# read filesystem stats directly from the local mount without RBAC.
_RUNTIME_STATUS_PVC_MOUNTS: dict[str, str] = {
    "backend-data": "/app/runs",
}


def build_runtime_status_payload(
    runs_dir: Path,
    *,
    now: datetime | None = None,
) -> RuntimeStatusPayload:
    """Build the runtime status payload from backend log and cluster data.

    Args:
        runs_dir: Path to the runs directory containing health data
        now: Optional clock for testing. Defaults to datetime.now(UTC) in production.

    Returns:
        RuntimeStatusPayload with log counts and PVC usage
    """
    # Build log windows from health.log
    log_windows = _build_log_windows_from_health_log(runs_dir, now=now)

    # Build PVC usage from local filesystem stats
    backend_pvc = _build_pvc_usage_from_statvfs("backend-data")

    return RuntimeStatusPayload(
        log_windows=log_windows,
        backend_pvc=backend_pvc,
    )


def _build_log_windows_from_health_log(
    runs_dir: Path,
    *,
    now: datetime | None = None,
) -> LogWindows:
    """Build log window counts from the health.log structured log file.

    Counts ERROR and WARNING severity entries from the health loop log,
    which contains operational events across all health runs.

    If the health.log is unavailable or unreadable, all values will be None
    (unavailable state) to distinguish from explicit zero counts.

    Note: The "backend" and "scheduler" fields in LogWindows are populated
    from the same shared health operational log. They are NOT pod-specific
    log extracts. Until per-component log extraction exists, both fields
    show identical counts representing aggregate health-loop operational events.

    Args:
        runs_dir: Path to the runs directory
        now: Optional clock for testing. Defaults to datetime.now(UTC) in production.

    Returns:
        LogWindows with counts for backend and scheduler pods
    """
    health_log_path = runs_dir / _HEALTH_LOG_PATH

    if not health_log_path.exists():
        return _empty_log_windows()

    try:
        counts_by_window = _count_severity_by_window(health_log_path, now=now)
    except OSError as exc:
        logger.debug("Failed to read health.log for runtime status: %s", exc)
        return _empty_log_windows()

    return LogWindows(
        backend=PodLogWindows(
            m5=LogWindowCounts(
                warning=counts_by_window.get(5, {}).get("WARNING", 0),
                error=counts_by_window.get(5, {}).get("ERROR", 0),
            ),
            m10=LogWindowCounts(
                warning=counts_by_window.get(10, {}).get("WARNING", 0),
                error=counts_by_window.get(10, {}).get("ERROR", 0),
            ),
            m15=LogWindowCounts(
                warning=counts_by_window.get(15, {}).get("WARNING", 0),
                error=counts_by_window.get(15, {}).get("ERROR", 0),
            ),
        ),
        scheduler=PodLogWindows(
            m5=LogWindowCounts(
                warning=counts_by_window.get(5, {}).get("WARNING", 0),
                error=counts_by_window.get(5, {}).get("ERROR", 0),
            ),
            m10=LogWindowCounts(
                warning=counts_by_window.get(10, {}).get("WARNING", 0),
                error=counts_by_window.get(10, {}).get("ERROR", 0),
            ),
            m15=LogWindowCounts(
                warning=counts_by_window.get(15, {}).get("WARNING", 0),
                error=counts_by_window.get(15, {}).get("ERROR", 0),
            ),
        ),
    )


def _count_severity_by_window(
    health_log_path: Path,
    *,
    now: datetime | None = None,
) -> dict[int, dict[str, int]]:
    """Count ERROR and WARNING entries by sliding time window.

    Reads the structured JSON health.log and counts non-info severity
    entries within 5-minute, 10-minute, and 15-minute windows ending at `now`.

    Args:
        health_log_path: Path to the health.log file
        now: Optional clock for testing. Defaults to datetime.now(UTC) in production.

    Returns:
        Dict mapping window size (minutes) to severity counts
    """
    window_end = now or datetime.now(UTC)
    windows: dict[int, tuple[datetime, dict[str, int]]] = {
        5: (window_end - timedelta(minutes=5), {"WARNING": 0, "ERROR": 0}),
        10: (window_end - timedelta(minutes=10), {"WARNING": 0, "ERROR": 0}),
        15: (window_end - timedelta(minutes=15), {"WARNING": 0, "ERROR": 0}),
    }

    with health_log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            severity = entry.get("severity", "")
            if severity not in _NON_INFO_SEVERITIES:
                continue

            timestamp_str = entry.get("timestamp")
            if not timestamp_str:
                continue

            try:
                entry_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            for _window_minutes, (window_start, counts) in windows.items():
                if entry_time >= window_start:
                    counts[severity] = counts.get(severity, 0) + 1

    return {minutes: counts for minutes, (_, counts) in windows.items()}


def _empty_log_windows() -> LogWindows:
    """Return unavailable state for all log windows.

    Used when health.log is missing or unreadable.
    """
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


def _build_pvc_usage_unavailable() -> PvcUsage | None:
    """Return unavailable state for PVC usage.

    PVC usage data is not currently available in cluster snapshots.
    This function returns None to indicate unavailable data, allowing
    the frontend to distinguish between:
    - unavailable data (None) - "PVC: unavailable"
    - populated data (PvcUsage instance)

    Note: This function is kept for backwards compatibility. New code should
    use _build_pvc_usage_from_statvfs() which provides real filesystem stats.
    """
    return None


def _build_pvc_usage_from_statvfs(pvc_name: str) -> PvcUsage | None:
    """Build PVC usage from local filesystem stats using os.statvfs().

    Reads filesystem statistics directly from the PVC mount path without
    requiring kubectl exec or additional RBAC permissions.

    Args:
        pvc_name: PVC name (e.g., "backend-data").

    Returns:
        PvcUsage with filesystem stats, or None if mount path not configured.
    """
    # Look up the mount path for this PVC
    mount_path = _RUNTIME_STATUS_PVC_MOUNTS.get(pvc_name)
    if not mount_path:
        logger.debug("No mount path configured for PVC: %s", pvc_name)
        return None

    return _get_filesystem_stats(pvc_name, mount_path)


def _get_filesystem_stats(pvc_name: str, mount_path: str) -> PvcUsage:
    """Get filesystem statistics for a mount path using os.statvfs().

    Args:
        pvc_name: PVC name for display.
        mount_path: Local mount path to query.

    Returns:
        PvcUsage with capacity, used, and free bytes from statvfs.
        Returns unavailable state on any error (missing path, permission denied, etc.).
    """
    try:
        # Check if path exists
        if not os.path.exists(mount_path):
            return PvcUsage(
                name=pvc_name,
                used_bytes=None,
                free_bytes=None,
                capacity_bytes=None,
                used_percent=None,
                source="statvfs",
                unavailable_reason=f"Path not found: {mount_path}",
            )

        # Get filesystem stats
        stat_info = os.statvfs(mount_path)

        # Extract values (convert from filesystem blocks to bytes)
        # f_frsize is the fragment size (usually same as block size)
        # f_blocks is total fragments
        # f_bfree is free fragments
        # f_bavail is available fragments (for non-privileged users)
        frsize = stat_info.f_frsize or 1  # Avoid division by zero
        total_blocks = stat_info.f_blocks
        free_blocks = stat_info.f_bfree
        avail_blocks = stat_info.f_bavail  # Available to non-privileged users

        capacity_bytes = total_blocks * frsize
        free_bytes = avail_blocks * frsize  # Use available, not just free
        used_bytes = (total_blocks - free_blocks) * frsize

        # Handle edge case: zero capacity means no meaningful stats
        if capacity_bytes == 0:
            return PvcUsage(
                name=pvc_name,
                used_bytes=None,
                free_bytes=None,
                capacity_bytes=None,
                used_percent=None,
                source="statvfs",
                unavailable_reason="Zero capacity filesystem",
            )

        # Calculate percentage
        used_percent = round((used_bytes / capacity_bytes) * 100)

        return PvcUsage(
            name=pvc_name,
            used_bytes=used_bytes,
            free_bytes=free_bytes,
            capacity_bytes=capacity_bytes,
            used_percent=used_percent,
            source="statvfs",
            unavailable_reason=None,
        )

    except OSError as exc:
        logger.debug("Failed to get filesystem stats for %s: %s", mount_path, exc)
        return PvcUsage(
            name=pvc_name,
            used_bytes=None,
            free_bytes=None,
            capacity_bytes=None,
            used_percent=None,
            source="statvfs",
            unavailable_reason=f"Cannot read filesystem: {exc}",
        )
    except (ValueError, TypeError) as exc:
        logger.debug("Unexpected error getting filesystem stats for %s: %s", mount_path, exc)
        return PvcUsage(
            name=pvc_name,
            used_bytes=None,
            free_bytes=None,
            capacity_bytes=None,
            used_percent=None,
            source="statvfs",
            unavailable_reason="Invalid filesystem data",
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
            log_windows=_empty_log_windows(),
            backend_pvc=None,
        )
        handler._send_json(payload.to_dict())
