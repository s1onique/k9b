"""Backward-compatible type exports for scheduler health gate.

This module exists for backward compatibility. New code should import from
scripts.scheduler_health_gate.contracts instead.
"""

from __future__ import annotations

from .contracts import SchedulerHealthResult

__all__ = ["SchedulerHealthResult"]
