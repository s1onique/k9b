"""Observability module for k9b backend OpenTelemetry integration.

This module provides:
- OTelConfig dataclass for bootstrap configuration
- load_otel_config_from_env() for environment-based config loading
- configure_otel() for SDK initialization
- trace_http_request() for HTTP request span instrumentation
- normalize_http_route() for low-cardinality span names

The bootstrap is disabled by default and only activates when
K9B_OTEL_ENABLED is explicitly set to a truthy value.
"""

from k8s_diag_agent.observability.http_spans import (
    get_route_normalization_result,
    normalize_http_route,
    trace_http_request,
    trace_http_request_with_status,
)
from k8s_diag_agent.observability.otel_bootstrap import (
    OTelConfig,
    configure_otel,
    load_otel_config_from_env,
)

__all__ = [
    "OTelConfig",
    "configure_otel",
    "get_route_normalization_result",
    "load_otel_config_from_env",
    "normalize_http_route",
    "trace_http_request",
    "trace_http_request_with_status",
]
