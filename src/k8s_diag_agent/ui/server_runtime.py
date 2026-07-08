"""Server bootstrap and runtime helpers extracted from server.py.

This module contains:
- Server startup function (start_ui_server)
- HTTP server construction helpers
- Access log formatting and emission with injectable emit function
- Request state management helpers
- Safe loopback host detection

These helpers are self-contained and do not depend on request-handler
instance state. They can be used independently or with HealthUIRequestHandler.
"""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Project root and default static directory
PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_STATIC_DIR = PROJECT_ROOT / "frontend" / "dist"

# Slow request threshold in milliseconds
_SLOW_REQUEST_THRESHOLD_MS = 1000


# Safe loopback hosts that don't require --unsafe-bind
_SAFE_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _init_otel_at_startup() -> None:
    """Initialize OpenTelemetry tracing at server startup.

    This function is called during server startup to configure OpenTelemetry
    tracing based on environment variables. It logs initialization status.

    The tracing is disabled by default and only activates when
    K9B_OTEL_ENABLED is explicitly set to a truthy value.

    Tracer provider is optional - server runs without tracing if not configured.
    """
    from ..observability import configure_otel, load_otel_config_from_env

    try:
        config = load_otel_config_from_env()
    except Exception as exc:
        print(f"OpenTelemetry: config load error (non-fatal): {exc}", file=sys.stderr)
        return

    if not config.enabled:
        return  # Silent - tracing disabled by default is expected

    try:
        configure_otel(config)
        print(
            f"OpenTelemetry: configured (service={config.service_name}, "
            f"endpoint={config.endpoint}, sample_ratio={config.sample_ratio})",
            file=sys.stderr,
        )
    except Exception as exc:
        # Log but don't fail startup - tracing is optional
        print(f"OpenTelemetry: configuration error (non-fatal): {exc}", file=sys.stderr)


def _init_diagnosis_provider_at_startup() -> None:
    """Initialize production diagnosis provider at server startup.

    This function is called during server startup to initialize the production
    diagnosis provider from environment configuration. It logs the initialization
    status for observability.

    The provider is only initialized if all required environment variables are set.
    If not configured, the server runs without LLM diagnosis capability (graceful degradation).
    """
    from ..collect.api_incident_one_pass_diagnosis_provider import (
        get_provider_config_status,
        init_production_diagnosis_provider,
    )

    try:
        config_status = get_provider_config_status()
    except Exception as exc:
        # Config status retrieval failed - log and continue without provider
        print(f"Diagnosis provider: config status error (non-fatal): {exc}", file=sys.stderr)
        return

    # config_status is a dict, check if provider is configured
    if not config_status.get("config_present"):
        # No config found - provider not configured
        print("Diagnosis provider: not configured (set K9B_DIAGNOSIS_PROVIDER_NAME, K9B_DIAGNOSIS_MODEL, K9B_DIAGNOSIS_BASE_URL to enable)", file=sys.stderr)
        return

    # Log safe config status (no raw API key - dict fields only)
    print(f"Diagnosis provider: initializing (provider={config_status.get('provider_name')}, model={config_status.get('model')}, api_key_present={config_status.get('api_key_present')})", file=sys.stderr)

    try:
        initialized = init_production_diagnosis_provider()
        if initialized:
            print("Diagnosis provider: initialized successfully", file=sys.stderr)
        else:
            print("Diagnosis provider: initialization failed (check logs)", file=sys.stderr)
    except Exception as exc:
        # Log but don't fail startup - provider is optional
        print(f"Diagnosis provider: initialization error (non-fatal): {exc}", file=sys.stderr)


def _is_exposed_host(host: str) -> bool:
    """Check if the host is exposed (non-loopback).

    Safe loopback hosts: 127.0.0.1, localhost, ::1
    Unsafe/exposed hosts: 0.0.0.0, ::, external IPs, non-loopback hostnames.
    """
    return host.lower() not in _SAFE_LOOPBACK_HOSTS


def _build_startup_security_message(host: str, port: int, auth_token: str | None) -> list[str]:
    """Build the startup security warning messages.

    Args:
        host: The host address being bound to
        port: The port being bound to
        auth_token: The configured auth token (None if not set)

    Returns:
        List of message lines to print to stderr
    """
    messages: list[str] = []

    messages.append(f"WARNING: Starting operator UI on exposed address '{host}:{port}'.")
    messages.append("The UI/API has mutation endpoints that can modify cluster state.")

    if not auth_token:
        messages.append("WARNING: No K9B_UI_TOKEN configured. Mutation endpoints are unprotected.")
        messages.append(
            "Set the K9B_UI_TOKEN environment variable or --auth-token CLI flag to protect them."
        )

    messages.append(
        "Ensure this host is only accessible from trusted networks, "
        "or use a reverse proxy with authentication in front of this service."
    )

    return messages


def start_ui_server_impl(
    *,
    server_factory: type,
    runs_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
    unsafe_bind: bool = False,
    auth_token: str | None = None,
    serve_forever: bool = True,
) -> None:
    """Start the UI HTTP server with the given configuration.

    Args:
        server_factory: HTTP server class (e.g., ThreadingHTTPServer) - injected for test mock compatibility
        runs_dir: Directory containing run health data
        host: Host address to bind to (default: 127.0.0.1)
        port: Port to bind to (default: 8080)
        static_dir: Directory containing static assets (default: frontend/dist)
        unsafe_bind: Allow binding to non-loopback addresses
        auth_token: Bearer token for mutation endpoint authentication
        serve_forever: If True, call server.serve_forever(). If False, return after
            server startup (for unit test fake servers). Defaults to True.
    """
    # Import here to avoid circular imports
    from .server import HealthUIRequestHandler
    from .server_shared import _normalize_runs_dir, _validate_runs_dir

    # Check for exposed host binding
    if _is_exposed_host(host):
        if not unsafe_bind:
            print(
                f"ERROR: Refusing to bind to exposed address '{host}' without --unsafe-bind.",
                file=sys.stderr,
            )
            print(
                "The UI/API has mutation endpoints (POST /api/next-check-approval, "
                "/api/next-check-execution, /api/deterministic-next-check/promote, etc.)",
                file=sys.stderr,
            )
            print(
                "To bind to non-loopback addresses, use --unsafe-bind to acknowledge the risk.",
                file=sys.stderr,
            )
            print(
                "Alternatively, bind to a loopback address (127.0.0.1, localhost, or ::1) "
                "and use port-forwarding for remote access.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        # Host is exposed and unsafe_bind is True - print security warnings
        for msg in _build_startup_security_message(host, port, auth_token):
            print(msg, file=sys.stderr)
        print(file=sys.stderr)

    # Normalize and validate runs_dir
    normalized_runs_dir = _normalize_runs_dir(runs_dir)
    _validate_runs_dir(normalized_runs_dir)

    # Initialize OpenTelemetry tracing if configured (disabled by default)
    _init_otel_at_startup()

    # Initialize production diagnosis provider if configured
    _init_diagnosis_provider_at_startup()

    assets = static_dir or DEFAULT_STATIC_DIR
    handler = functools.partial(
        HealthUIRequestHandler,
        runs_dir=normalized_runs_dir,
        static_dir=assets,
        auth_token=auth_token,
    )
    server = server_factory((host, port), handler)
    print(
        f"Operator UI listening on http://{host}:{port}/ (runs: {normalized_runs_dir}, assets: {assets})",
        file=sys.stderr,
    )
    try:
        if serve_forever:
            server.serve_forever()
        else:
            # For unit tests: return after server construction and safety checks.
            # Cleanup is handled by the server context manager.
            pass
    except KeyboardInterrupt:
        print("Shutting down operator UI server", file=sys.stderr)
        server.shutdown()
    finally:
        server.server_close()


def start_ui_server(
    runs_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    static_dir: Path | None = None,
    unsafe_bind: bool = False,
    auth_token: str | None = None,
) -> None:
    """Start the UI HTTP server with the given configuration.

    This is a compatibility wrapper that injects the default StructuredErrorHTTPServer.
    Tests should patch k8s_diag_agent.ui.server.StructuredErrorHTTPServer before calling
    this function to intercept server startup.

    Args:
        runs_dir: Directory containing run health data
        host: Host address to bind to (default: 127.0.0.1)
        port: Port to bind to (default: 8080)
        static_dir: Directory containing static assets (default: frontend/dist)
        unsafe_bind: Allow binding to non-loopback addresses
        auth_token: Bearer token for mutation endpoint authentication
    """
    # Import here to allow tests to patch server.StructuredErrorHTTPServer before this runs
    from .server import StructuredErrorHTTPServer as _StructuredErrorHTTPServer

    start_ui_server_impl(
        server_factory=_StructuredErrorHTTPServer,
        runs_dir=runs_dir,
        host=host,
        port=port,
        static_dir=static_dir,
        unsafe_bind=unsafe_bind,
        auth_token=auth_token,
    )


def _log_request_access_with_emit(
    *,
    emit_fn: Callable[..., Any],
    slow_request_threshold_ms: float,
    method: str,
    path: str,
    query: str,
    status_code: int,
    duration_ms: float,
    response_bytes: int,
    client_ip: str,
    run_label: str = "",
    is_static_asset: bool = False,
    request_id: str = "",
    route_return_ms: float = 0.0,
    client_request_id: str = "",
) -> None:
    """Log structured HTTP access event with injectable emit function.

    This version accepts an emit_fn parameter to allow the caller to inject
    the emit_structured_log function, preserving test mock compatibility.

    Args:
        emit_fn: The emit_structured_log function to use (injected by caller)
        slow_request_threshold_ms: Threshold in ms above which request is "slow" (injected by caller)
        method: HTTP method (GET, POST, etc.)
        path: Request path (e.g., /api/run)
        query: Query string (e.g., run_id=abc)
        status_code: HTTP response status code
        duration_ms: Request handling duration in milliseconds
        response_bytes: Response body size in bytes
        client_ip: Client IP address
        run_label: Run label when known, else empty string
        is_static_asset: Whether this is a static asset request
        request_id: Correlation ID for linking access log to route timing logs
        route_return_ms: Time from request start to route handler returning (before send)
        client_request_id: Client-generated request ID from X-K9B-Client-Request-Id header
    """
    # Determine severity based on status code and latency
    if status_code >= 500:
        severity = "ERROR"
    elif status_code >= 400:
        severity = "WARNING"
    elif duration_ms >= slow_request_threshold_ms:
        severity = "WARNING"
    elif is_static_asset:
        # Use DEBUG for static assets to reduce noise
        severity = "DEBUG"
    else:
        severity = "INFO"

    # Build message
    message = f"{method} {path}"
    if query:
        message += f"?{query}"

    metadata: dict[str, Any] = {
        "method": method,
        "path": path,
        "query": query,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        "response_bytes": response_bytes,
        "client_ip": client_ip,
        "run_label": run_label,
    }

    # Add correlation fields if available
    if request_id:
        metadata["request_id"] = request_id
    if client_request_id:
        metadata["client_request_id"] = client_request_id
    if route_return_ms > 0:
        metadata["route_return_ms"] = round(route_return_ms, 2)
        # Compute network/flush overhead for debugging
        send_overhead = duration_ms - route_return_ms
        if send_overhead > 0:
            metadata["send_overhead_ms"] = round(send_overhead, 2)

    emit_fn(
        component="ui-access",
        message=message,
        severity=severity,
        run_label=run_label,
        run_id="",
        metadata=metadata,
    )
