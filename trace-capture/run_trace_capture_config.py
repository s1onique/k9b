"""Configuration for run_trace_capture module.

This module contains:
- TraceCaptureConfig dataclass
- Environment helpers for OTel
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TraceCaptureConfig:
    """Configuration for trace capture run."""

    # Artifact directory
    artifact_dir: Path = field(default_factory=lambda: Path(__file__).parent)

    # Backend configuration
    backend_url: str = "http://localhost:8080"
    backend_startup_timeout: float = 30.0

    # OTel configuration
    otel_enabled: bool = True
    service_name: str = "k9b-backend"
    otel_endpoint: str = "http://localhost:4317"
    sample_ratio: float = 1.0

    # Collector configuration
    collector_config_path: Path | None = None
    collector_startup_timeout: float = 10.0

    # Kubernetes collector copy mode
    # When True, copies traces from in-cluster Collector instead of running local Collector
    k8s_collector_mode: bool = False
    k8s_namespace: str = "k9b"
    k8s_collector_pod: str | None = None
    k8s_trace_path: str = "/var/lib/k9b-traces/collector-traces.jsonl"

    # Exercise configuration
    api_timeout: float = 10.0
    exercise_iterations: int = 1
    warmup_iterations: int = 0
    incident_id: str | None = None

    # Perf baseline configuration
    perf_baseline: bool = False
    baseline_output_dir: Path | None = None

    # Output control
    dry_run: bool = False
    verbose: bool = False


def get_backend_env(config: TraceCaptureConfig) -> dict[str, str]:
    """Build environment for backend with OTel enabled.

    Args:
        config: Trace capture configuration

    Returns:
        Environment dictionary for backend process
    """
    env = dict(os.environ)

    if config.otel_enabled:
        env["K9B_OTEL_ENABLED"] = "true"
        env["K9B_OTEL_SERVICE_NAME"] = config.service_name
        env["K9B_OTEL_EXPORTER_OTLP_ENDPOINT"] = config.otel_endpoint
        env["K9B_OTEL_SAMPLE_RATIO"] = str(config.sample_ratio)
    else:
        env["K9B_OTEL_ENABLED"] = "false"

    return env
