"""OpenTelemetry HTTP request span instrumentation for k9b backend.

This module provides a disabled-by-default HTTP request boundary instrumentation seam:
- One request-level span per backend API call
- Low-cardinality span names using normalized route templates
- Bounded span attributes
- Privacy-safe (no request/response body capture)
- Testable without a live collector

The instrumentation is activated only when K9B_OTEL_ENABLED is set to a truthy value.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Final, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable


T = TypeVar("T")

logger = logging.getLogger(__name__)

# =============================================================================
# Route Normalization
# =============================================================================

# Pattern to match UUID-like incident IDs (kebab-case UUID format)
# Examples: 1234abcd-5678-efgh-9999-ijklmnopqrst
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

# Pattern to match any non-empty segment (for unknown dynamic paths)
_NON_EMPTY_SEGMENT = re.compile(r"^[^/]+$")

# Mapping of known API route templates to their normalized forms
# Order matters: more specific patterns MUST come first (regex is checked sequentially)
_KNOWN_ROUTE_NORMALIZATIONS: Final[list[tuple[re.Pattern[str], str]]] = [
    # Incident routes - concrete paths first (no trailing segment that could match generic pattern)
    (re.compile(r"^/api/incidents/snapshot$"), "/api/incidents/snapshot"),
    (re.compile(r"^/api/incidents/review-packet$"), "/api/incidents/review-packet"),
    (re.compile(r"^/api/incidents$"), "/api/incidents"),
    # Incident routes with path parameters (must come after concrete paths)
    (re.compile(r"^/api/incidents/[^/]+/automatic-diagnosis-review/handoff$"), "/api/incidents/{incident_id}/automatic-diagnosis-review/handoff"),
    (re.compile(r"^/api/incidents/[^/]+/automatic-diagnosis-loop/one-pass$"), "/api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass"),
    (re.compile(r"^/api/incidents/[^/]+/diagnosis-loop/one-pass$"), "/api/incidents/{incident_id}/diagnosis-loop/one-pass"),
    (re.compile(r"^/api/incidents/[^/]+/one-pass-diagnosis$"), "/api/incidents/{incident_id}/one-pass-diagnosis"),
    (re.compile(r"^/api/incidents/[^/]+$"), "/api/incidents/{incident_id}"),
    # Run routes
    (re.compile(r"^/api/runs/[^/]+/alertmanager-sources/[^/]+/action$"), "/api/runs/{run_id}/alertmanager-sources/{source_id}/action"),
    (re.compile(r"^/api/runs$"), "/api/runs"),
    (re.compile(r"^/api/run$"), "/api/run"),
    (re.compile(r"^/api/fleet$"), "/api/fleet"),
    (re.compile(r"^/api/proposals$"), "/api/proposals"),
    (re.compile(r"^/api/cluster-detail$"), "/api/cluster-detail"),
    (re.compile(r"^/api/notifications$"), "/api/notifications"),
    # Next-check routes
    (re.compile(r"^/api/deterministic-next-check/promote$"), "/api/deterministic-next-check/promote"),
    (re.compile(r"^/api/next-check-execution$"), "/api/next-check-execution"),
    (re.compile(r"^/api/next-check-approval$"), "/api/next-check-approval"),
    (re.compile(r"^/api/next-check-execution-usefulness$"), "/api/next-check-execution-usefulness"),
    (re.compile(r"^/api/alertmanager-relevance-feedback$"), "/api/alertmanager-relevance-feedback"),
    (re.compile(r"^/api/run-batch-next-check-execution$"), "/api/run-batch-next-check-execution"),
    # Auth routes
    (re.compile(r"^/api/auth/login$"), "/api/auth/login"),
    (re.compile(r"^/api/auth/logout$"), "/api/auth/logout"),
    (re.compile(r"^/api/auth/me$"), "/api/auth/me"),
    (re.compile(r"^/api/auth/status$"), "/api/auth/status"),
    # Health routes
    (re.compile(r"^/api/health/details$"), "/api/health/details"),
    (re.compile(r"^/api/health$"), "/api/health"),
    # Runtime routes
    (re.compile(r"^/api/runtime-status$"), "/api/runtime-status"),
    # OpenAPI route
    (re.compile(r"^/api/openapi\.json$"), "/api/openapi.json"),
]


def normalize_http_route(method: str, path: str) -> str:
    """Normalize an HTTP route to a low-cardinality span name.

    Converts concrete dynamic paths to template placeholders to ensure
    span names remain low-cardinality and privacy-safe.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Raw request path

    Returns:
        Normalized route template string suitable for span naming.
        Examples:
            GET /api/incidents -> GET /api/incidents
            GET /api/incidents/abc-123 -> GET /api/incidents/{incident_id}
            POST /api/incidents/xyz-456/diagnosis-loop/one-pass -> POST /api/incidents/{incident_id}/diagnosis-loop/one-pass
    """
    # Strip query string if present
    route = path.split("?")[0]

    # Check each known normalization pattern
    for pattern, normalized in _KNOWN_ROUTE_NORMALIZATIONS:
        if pattern.match(route):
            return f"{method} {normalized}"

    # Unknown API route: use safe fallback without leaking raw path
    if route.startswith("/api/"):
        # Use a safe fallback that doesn't leak any path segments
        return f"{method} /api/{{unknown}}"

    # Non-API route (static assets, etc.)
    return f"{method} /{{static}}"


def get_route_normalization_result(method: str, path: str) -> tuple[str, bool]:
    """Get the normalized route and whether it was a known API route.

    Args:
        method: HTTP method
        path: Raw request path

    Returns:
        Tuple of (normalized_route, is_known_api_route)
    """
    route = path.split("?")[0]

    for pattern, normalized in _KNOWN_ROUTE_NORMALIZATIONS:
        if pattern.match(route):
            return (f"{method} {normalized}", True)

    if route.startswith("/api/"):
        return (f"{method} /api/{{unknown}}", False)

    return (f"{method} /{{static}}", False)


# =============================================================================
# HTTP Request Span Wrapper
# =============================================================================

# Lazy import holder for tracer (avoids heavyweight import when disabled)
_tracer = None


def _get_tracer() -> object | None:
    """Get or create the OTel tracer for HTTP spans.

    Returns None if tracing is not available/disabled.
    """
    global _tracer
    if _tracer is None:
        try:
            from opentelemetry import trace

            _tracer = trace.get_tracer(__name__)
        except ImportError:
            # OTel not installed - return None to indicate tracing unavailable
            return None
    return _tracer


def _is_tracing_enabled() -> bool:
    """Check if tracing is enabled via configuration.

    Returns True only when K9B_OTEL_ENABLED is truthy and OTel SDK is available.
    """
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        # Check if provider is the no-op provider (default when not configured)
        # The no-op provider class name contains "None" when not initialized
        provider_class = type(provider).__name__
        if "None" in provider_class or "no_op" in provider_class.lower():
            return False
        return True
    except ImportError:
        return False
    except Exception:
        return False


def trace_http_request(
    *,
    method: str,
    path: str,
    handler_name: str,
    call: Callable[[], T],
) -> T:
    """Wrap an HTTP handler call with an OpenTelemetry span.

    This function provides request-level tracing for backend API calls.
    When tracing is disabled or unavailable, it simply calls the handler
    without any instrumentation overhead.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Raw request path
        handler_name: Name of the handler function for attribute logging
        call: The handler call to wrap

    Returns:
        The return value of the handler call

    Raises:
        Re-raises any exception from the handler unchanged after recording
        it on the span if tracing is active.
    """
    # Fast path: if tracing is disabled, just call the handler
    tracer = _get_tracer()
    if tracer is None:
        return call()

    if not _is_tracing_enabled():
        return call()

    # Get normalized route for span name
    normalized_route, is_known_route = get_route_normalization_result(method, path)
    span_name = normalized_route

    # Create and use the span
    with tracer.start_as_current_span(span_name) as span:
        # Set bounded attributes
        span.set_attribute("k9b.api.method", method)
        span.set_attribute("k9b.api.route", normalized_route)
        span.set_attribute("k9b.api.handler", handler_name)
        span.set_attribute("k9b.api.route_known", is_known_route)

        # Set HTTP attributes
        span.set_attribute("http.request.method", method)

        try:
            result = call()
            return result
        except Exception as exc:
            # Record exception on span and set error status per OTel semantic conventions
            span.record_exception(exc)
            span.set_status("ERROR", str(exc))
            span.set_attribute("k9b.http.status_code", 500)
            raise


def trace_http_request_with_status(
    *,
    method: str,
    path: str,
    handler_name: str,
    call: Callable[[], int],
) -> int:
    """Wrap an HTTP handler call with an OpenTelemetry span, tracking status code.

    Variant of trace_http_request that captures the HTTP status code returned
    by the handler.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Raw request path
        handler_name: Name of the handler function for attribute logging
        call: The handler call that returns the HTTP status code

    Returns:
        The HTTP status code returned by the handler

    Raises:
        Re-raises any exception from the handler unchanged after recording
        it on the span if tracing is active.
    """
    # Fast path: if tracing is disabled, just call the handler
    tracer = _get_tracer()
    if tracer is None:
        return call()

    if not _is_tracing_enabled():
        return call()

    # Get normalized route for span name
    normalized_route, is_known_route = get_route_normalization_result(method, path)
    span_name = normalized_route

    # Create and use the span
    with tracer.start_as_current_span(span_name) as span:
        # Set bounded attributes
        span.set_attribute("k9b.api.method", method)
        span.set_attribute("k9b.api.route", normalized_route)
        span.set_attribute("k9b.api.handler", handler_name)
        span.set_attribute("k9b.api.route_known", is_known_route)

        # Set HTTP attributes
        span.set_attribute("http.request.method", method)

        try:
            status_code = call()
            span.set_attribute("http.response.status_code", status_code)
            span.set_attribute("k9b.http.status_code", status_code)
            return status_code
        except Exception as exc:
            # Record exception on span and set error status per OTel semantic conventions
            span.record_exception(exc)
            span.set_status("ERROR", str(exc))
            span.set_attribute("k9b.http.status_code", 500)
            raise
