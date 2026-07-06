#!/usr/bin/env python3
"""Shared types for vmalert→Alertmanager→K9B incident lab."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LabPhase:
    """Result of a single lab phase."""
    name: str
    success: bool
    message: str = ""
    artifacts: dict[str, Any] = field(default_factory=dict)
    failure_class: str | None = None


@dataclass
class LabConfig:
    """Configuration for the lab."""
    kubeconfig: str
    artifact_dir: Path
    k9b_namespace: str = "k9b"
    monitoring_namespace: str = "monitoring"
    lab_namespace: str = "k9b-alertmanager-lab"
    k9b_release: str = "k9b"
    alertmanager_release: str = "alertmanager"
    readiness_timeout: int = 120
    alert_wait_timeout: int = 30
    webhook_token: str = "lab-secret-token"


@dataclass
class LabResult:
    """Result of the complete lab run."""
    success: bool = False
    started_at: str = ""
    finished_at: str = ""
    failure_reason: str | None = None
    phases: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)
