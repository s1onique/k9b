"""Scheduler health gate for provider smoke testing.

This module provides a scheduler readiness check that runs before incident
discovery. It detects scheduler failure modes (CrashLoopBackOff, missing,
not Ready) and fails fast with actionable evidence.

The scheduler is responsible for incident ingestion - if it's not healthy,
no incidents will be produced regardless of backend health.
"""

from .main import run_scheduler_health_gate
from .types import SchedulerHealthResult

__all__ = [
    "run_scheduler_health_gate",
    "SchedulerHealthResult",
]
