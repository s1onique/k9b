#!/usr/bin/env python3
"""Rollout types for CNPG Live Lab.

This module contains the RolloutResult dataclass used by rollout checking functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RolloutResult:
    """Result of classify_rollout_state."""

    fatal: bool
    failure_class: str
    diagnostics: dict[str, Any] = field(default_factory=dict)
    affected_pods: list[str] = field(default_factory=list)
    pod_phase: str = ""
    # Crash-loop specific fields for human-readable status
    crash_pod_name: str = ""
    crash_container_name: str = ""
    crash_restart_count: int = 0
