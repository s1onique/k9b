#!/usr/bin/env python3
"""OTel Demo Lab types - dataclasses and type definitions.

This module contains all type definitions for the OTel Demo Lab.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .k9b_otel_demo_lab_constants import (
    OTEL_DEMO_CHART,
    OTEL_DEMO_CHART_VERSION,
    OTEL_DEMO_HELM_REPO_NAME,
    OTEL_DEMO_HELM_REPO_URL,
    OTEL_DEMO_NAMESPACE,
    OTEL_DEMO_RELEASE,
)

# Lab mode constants
LAB_MODE_SCAFFOLD = "scaffold"
LAB_MODE_LIVE = "live"
LAB_MODES = (LAB_MODE_SCAFFOLD, LAB_MODE_LIVE)


@dataclass
class LabConfig:
    """Configuration for OTel Demo Lab."""
    
    kubeconfig: str = ""
    artifact_dir: str = "./lab-artifacts/otel-demo"
    mode: Literal["scaffold", "live"] = "scaffold"
    namespace: str = OTEL_DEMO_NAMESPACE
    helm_repo_url: str = OTEL_DEMO_HELM_REPO_URL
    helm_repo_name: str = OTEL_DEMO_HELM_REPO_NAME
    helm_chart: str = OTEL_DEMO_CHART
    helm_chart_version: str = OTEL_DEMO_CHART_VERSION
    helm_release: str = OTEL_DEMO_RELEASE
    readiness_timeout: int = 600  # 10 minutes for full demo deploy
    readiness_poll_interval: int = 30
    incident_wait_seconds: int = 30
    model: str = "qwen/qwen3-235b-a22b"
    llm_base_url: str = ""
    run_real_llm: bool = False
    
    # Live mode specific config
    live_traffic_duration_seconds: int = 600  # 10 minutes
    live_observation_wait_seconds: int = 600  # 10 minutes for symptoms
    live_poll_interval_seconds: int = 30
    
    # Provider smoke config (k9b API integration)
    enable_provider_smoke: bool = False


@dataclass
class LabPhaseResult:
    """Result of a lab phase."""
    
    phase: str
    success: bool
    message: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


@dataclass
class LabResult:
    """Complete lab result."""
    
    started_at: str = ""
    finished_at: str = ""
    elapsed_seconds: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)
    phases: list[dict[str, Any]] = field(default_factory=list)
    success: bool = False
    failure_reason: str = ""
    verification_passed: bool = False
    verification_details: dict[str, Any] = field(default_factory=dict)
    provider_smoke_passed: bool = False
