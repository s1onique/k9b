"""model_runtime_status.py - Data models for runtime status API.

This module defines the Pydantic models for the runtime status payload.
Used by the API builder to construct responses for the frontend.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LogWindowCounts:
    """Non-info log counts for a single time window.
    
    Values may be None to indicate unavailable/missing data.
    Zero counts are explicit: warning=0, error=0
    """
    warning: int | None = None
    error: int | None = None


@dataclass
class PodLogWindows:
    """Log counts for a pod across multiple sliding time windows."""
    m5: LogWindowCounts = field(default_factory=LogWindowCounts)
    m10: LogWindowCounts = field(default_factory=LogWindowCounts)
    m15: LogWindowCounts = field(default_factory=LogWindowCounts)


@dataclass
class LogWindows:
    """Aggregated log counts for backend and scheduler pods."""
    backend: PodLogWindows = field(default_factory=PodLogWindows)
    scheduler: PodLogWindows = field(default_factory=PodLogWindows)


@dataclass
class PvcUsage:
    """PVC storage usage with byte counts and percentage.
    
    Attributes:
        name: PVC name (e.g., "backend-data").
        used_bytes: Used storage in bytes.
        free_bytes: Free/available storage in bytes.
        capacity_bytes: Total capacity in bytes.
        used_percent: Percentage of capacity used (0-100).
        source: Data source method (e.g., "statvfs", "kubelet", "k8s_api").
        unavailable_reason: Human-readable reason if data is unavailable.
    """
    name: str = ""
    used_bytes: int | None = None
    free_bytes: int | None = None
    capacity_bytes: int | None = None
    used_percent: int | None = None
    source: str | None = None
    unavailable_reason: str | None = None


@dataclass
class RuntimeStatusPayload:
    """Complete runtime status payload for the frontend.
    
    This is a read-only observability projection derived from cluster data.
    The frontend should only render; no data transformation is needed.
    """
    log_windows: LogWindows = field(default_factory=LogWindows)
    backend_pvc: PvcUsage | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for JSON serialization."""
        return {
            "log_windows": {
                "backend": {
                    "5m": {"warning": self.log_windows.backend.m5.warning, "error": self.log_windows.backend.m5.error},
                    "10m": {"warning": self.log_windows.backend.m10.warning, "error": self.log_windows.backend.m10.error},
                    "15m": {"warning": self.log_windows.backend.m15.warning, "error": self.log_windows.backend.m15.error},
                },
                "scheduler": {
                    "5m": {"warning": self.log_windows.scheduler.m5.warning, "error": self.log_windows.scheduler.m5.error},
                    "10m": {"warning": self.log_windows.scheduler.m10.warning, "error": self.log_windows.scheduler.m10.error},
                    "15m": {"warning": self.log_windows.scheduler.m15.warning, "error": self.log_windows.scheduler.m15.error},
                },
            },
            "backend_pvc": (
                {
                    "name": self.backend_pvc.name,
                    "used_bytes": self.backend_pvc.used_bytes,
                    "free_bytes": self.backend_pvc.free_bytes,
                    "capacity_bytes": self.backend_pvc.capacity_bytes,
                    "used_percent": self.backend_pvc.used_percent,
                    "source": self.backend_pvc.source,
                    "unavailable_reason": self.backend_pvc.unavailable_reason,
                }
                if self.backend_pvc
                else None
            ),
        }
