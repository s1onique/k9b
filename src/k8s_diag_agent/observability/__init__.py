"""Observability module for k9b backend OpenTelemetry integration.

This module provides:
- OTelConfig dataclass for bootstrap configuration
- load_otel_config_from_env() for environment-based config loading
- configure_otel() for SDK initialization

The bootstrap is disabled by default and only activates when
K9B_OTEL_ENABLED is explicitly set to a truthy value.
"""

from k8s_diag_agent.observability.otel_bootstrap import (
    OTelConfig,
    configure_otel,
    load_otel_config_from_env,
)

__all__ = [
    "OTelConfig",
    "configure_otel",
    "load_otel_config_from_env",
]
