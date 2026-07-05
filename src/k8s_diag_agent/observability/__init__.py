"""Observability module for k9b backend OpenTelemetry integration.

This module provides:
- OTelConfig dataclass for bootstrap configuration
- load_otel_config_from_env() for environment-based config loading
- configure_otel() for SDK initialization
- trace_http_request() for HTTP request span instrumentation
- normalize_http_route() for low-cardinality span names
- trace_internal_operation() for internal span instrumentation
- internal_span() context manager for internal spans
- Convenience helpers for common internal span patterns

The bootstrap is disabled by default and only activates when
K9B_OTEL_ENABLED is explicitly set to a truthy value.
"""

from k8s_diag_agent.observability.http_spans import (
    get_route_normalization_result,
    normalize_http_route,
    trace_http_request,
    trace_http_request_with_status,
)
from k8s_diag_agent.observability.internal_spans import (
    internal_span,
    trace_api_response_project,
    trace_artifact_decode_json,
    trace_artifact_read_json,
    trace_artifact_scan,
    trace_automatic_diagnosis_review_load,
    trace_diagnosis_loop_load_passes,
    trace_diagnosis_loop_load_summary,
    trace_incident_store_get,
    trace_incident_store_list,
    trace_internal_operation,
    trace_review_packet_load,
    trace_review_packet_project,
    trace_snapshot_bundle_load,
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
    "internal_span",
    "load_otel_config_from_env",
    "normalize_http_route",
    "trace_api_response_project",
    "trace_artifact_decode_json",
    "trace_artifact_read_json",
    "trace_artifact_scan",
    "trace_automatic_diagnosis_review_load",
    "trace_diagnosis_loop_load_passes",
    "trace_diagnosis_loop_load_summary",
    "trace_http_request",
    "trace_http_request_with_status",
    "trace_incident_store_get",
    "trace_incident_store_list",
    "trace_internal_operation",
    "trace_review_packet_load",
    "trace_review_packet_project",
    "trace_snapshot_bundle_load",
]
