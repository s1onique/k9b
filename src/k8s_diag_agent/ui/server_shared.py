"""Shared path utilities for the UI server.

This module contains pure/shared helpers extracted from server.py to enable
incremental modularization. These helpers are self-contained and do not
depend on request-handler instance state.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)

# Default maximum content length for JSON mutation requests (1 MiB)
DEFAULT_MAX_CONTENT_LENGTH = 1 * 1024 * 1024


def _validate_mutation_origin(handler: HealthUIRequestHandler) -> bool:
    """Validate Origin/Referer headers for CSRF protection on mutation endpoints.

    This implements API-R2: strict Origin/Referer guard for mutation endpoints.
    Follows OWASP recommendation for CSRF protection on state-changing operations.

    Logic:
    1. If Origin header is present, parse it and compare origin scheme/host/port
       to the request Host header. Reject mismatch with 403.
    2. If Origin is absent but Referer is present, parse Referer and compare
       scheme/host/port to request Host. Reject mismatch with 403.
    3. If both Origin and Referer are absent, allow (CLI/non-browser client).
    4. Default scheme is http unless the handler has a trusted scheme source.

    This is strict same-origin checking - do not broadly allow all localhost ports.

    Args:
        handler: The HealthUIRequestHandler instance

    Returns:
        True if origin validation passes (request allowed), False if rejected
        (in which case the handler has already sent a 403 error response)
    """
    origin = handler.headers.get("Origin")
    referer = handler.headers.get("Referer")
    host = handler.headers.get("Host", "")

    # Parse host to extract host and port
    # Host header may include port (e.g., "localhost:8080" or "example.com:443")
    def _parse_host(host_header: str) -> tuple[str, int | None]:
        """Parse Host header into (host, port)."""
        if ":" in host_header:
            host_part, port_part = host_header.rsplit(":", 1)
            try:
                port = int(port_part)
            except ValueError:
                port = None
            return host_part.strip(), port
        # No explicit port - infer from scheme
        return host_header.strip(), None

    def _compare_origin(
        origin_url: str,
        request_host: str,
        expected_scheme: str = "http",
    ) -> bool:
        """Compare parsed origin to request host.

        Args:
            origin_url: The Origin or Referer URL to validate
            request_host: The Host header value from the request
            expected_scheme: The expected scheme for this server (http for HTTP dev server)

        Returns:
            True if origin matches request host, False otherwise
        """
        try:
            parsed = urlparse(origin_url)
        except ValueError:
            # Invalid URL - reject
            return False

        origin_host = parsed.hostname
        origin_port = parsed.port
        origin_scheme = parsed.scheme

        if not origin_host:
            return False

        # Reject invalid schemes
        if origin_scheme not in ("http", "https"):
            return False

        # CRITICAL: Compare scheme explicitly against expected request scheme.
        # This is an HTTP dev server, so https Origin must be rejected
        # even when host/port match. This prevents cross-protocol attacks.
        if origin_scheme != expected_scheme:
            return False

        request_host_name, request_port = _parse_host(request_host)

        # Compare host (case-insensitive per RFC 6454)
        if origin_host.lower() != request_host_name.lower():
            return False

        # Compare port:
        # - If origin has explicit port, it must match request port
        # - If origin has no explicit port, it implies standard port for its scheme
        if origin_port is not None:
            # Origin has explicit port - must match request port
            if origin_port != request_port:
                return False
        else:
            # Origin has no explicit port - check standard port for origin scheme
            standard_port = 80 if origin_scheme == "http" else 443
            # If request is on non-standard port, origin must specify it
            if request_port is not None and request_port != standard_port:
                return False

        return True

    # Case 1: Origin header is present - validate against Host
    if origin:
        if not _compare_origin(origin, host):
            handler._send_json(
                {"error": "Origin mismatch (CSRF protection: API-R2)"},
                403,  # Forbidden
            )
            return False
        return True

    # Case 2: Origin absent but Referer present - validate Referer against Host
    if referer:
        if not _compare_origin(referer, host):
            handler._send_json(
                {"error": "Referer mismatch (CSRF protection: API-R2)"},
                403,  # Forbidden
            )
            return False
        return True

    # Case 3: Both Origin and Referer absent - allow (CLI/non-browser client)
    # This is intentional: CLI tools, server-to-server calls, and direct API
    # clients typically don't send these headers. Combined with localhost-only
    # binding assumption, this is acceptable.
    return True


def _validate_json_mutation_request(
    handler: HealthUIRequestHandler,
    max_content_length: int = DEFAULT_MAX_CONTENT_LENGTH,
) -> dict[str, object] | None:
    """Validate Content-Type, Origin/Referer, and request size for JSON mutation requests.

    This shared helper provides consistent validation for all mutation endpoints:
    - Validates Origin/Referer headers for CSRF protection (API-R2)
    - Validates Content-Type is application/json (or application/json with charset)
    - Enforces max Content-Length to prevent oversized payloads
    - Returns the parsed JSON payload if validation passes
    - Sends appropriate HTTP error responses (400, 403, 413, 415) on failure

    Args:
        handler: The HealthUIRequestHandler instance
        max_content_length: Maximum allowed Content-Length in bytes (default 1 MiB)

    Returns:
        Parsed JSON payload dict if validation passes, None if validation failed
        (in which case the handler has already sent an error response)
    """
    # API-R2: Validate Origin/Referer headers for CSRF protection
    if not _validate_mutation_origin(handler):
        return None

    # Validate Content-Type header
    content_type = handler.headers.get("Content-Type", "")
    # Normalize: strip parameters (e.g., charset) and lowercase for comparison
    if content_type:
        # Extract just the media type before any semicolon
        base_content_type = content_type.split(";")[0].strip().lower()
    else:
        base_content_type = ""

    # Require Content-Type to be application/json with optional charset parameter
    # Reject text/plain, form-urlencoded, multipart, or missing/empty content type
    if base_content_type not in ("application/json",):
        handler._send_json(
            {"error": "Content-Type must be application/json"},
            415,  # Unsupported Media Type
        )
        return None

    # Handle Content-Length
    content_length_str = handler.headers.get("Content-Length", "")
    try:
        content_length = int(content_length_str) if content_length_str else 0
    except ValueError:
        # Invalid Content-Length header - treat as missing/zero
        content_length = 0

    # Check for empty request body on POST endpoints
    if content_length <= 0:
        handler._send_json({"error": "Request body required"}, 400)
        return None

    # Enforce max Content-Length
    if content_length > max_content_length:
        handler._send_json(
            {"error": f"Request body too large (max {max_content_length} bytes)"},
            413,  # Payload Too Large
        )
        return None

    # Read and parse the request body
    try:
        raw_payload = handler.rfile.read(content_length).decode("utf-8")
        payload = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return None

    # Ensure payload is a dict (not array, number, string, etc.)
    if not isinstance(payload, dict):
        handler._send_json({"error": "Invalid JSON payload"}, 400)
        return None

    return payload


def _normalize_runs_dir(runs_dir: Path) -> Path:
    """Normalize runs_dir to the canonical parent directory.

    The canonical runs_dir can be either:
    - 'runs' (parent directory) - UI internally accesses runs/health/ subdirectory
    - 'runs/health' (leaf directory) - directly contains health artifacts

    This function detects which form is being used and normalizes appropriately.
    If user passes runs/health (where artifacts actually live), keep it.
    If user passes runs (parent), keep it.
    If runs/health is empty (no artifacts), normalize to parent runs.

    Args:
        runs_dir: The runs directory as provided by the user

    Returns:
        Normalized runs directory (either parent or leaf)
    """
    resolved = runs_dir.resolve()

    # Check if runs_dir itself is the health directory (e.g., runs/health)
    if resolved.name == "health":
        # Check if this directory itself contains health artifacts
        # (external-analysis, assessments, drilldowns are directly here)
        if any(
            (resolved / subdir).exists()
            for subdir in ["external-analysis", "assessments", "drilldowns"]
        ):
            logger.debug(
                "Kept runs_dir as health leaf directory",
                extra={"input": str(runs_dir), "resolved": str(resolved)},
            )
            return resolved

        # No artifacts in runs/health - normalize to parent runs
        parent = resolved.parent
        logger.debug(
            "Normalized runs_dir from leaf to parent",
            extra={"input": str(runs_dir), "normalized": str(parent)},
        )
        return parent

    # Check if runs_dir has a 'health' subdirectory with artifacts
    health_dir = resolved / "health"
    if health_dir.exists() and any(
        (health_dir / subdir).exists()
        for subdir in ["external-analysis", "assessments", "drilldowns"]
    ):
        logger.debug(
            "Kept runs_dir as parent (has health subdirectory)",
            extra={"input": str(runs_dir), "resolved": str(resolved)},
        )
        return resolved

    return resolved


def _validate_runs_dir(runs_dir: Path) -> None:
    """Validate that runs_dir has the expected structure.

    The canonical runs_dir should have a 'health' subdirectory (or be empty
    if no runs have been executed yet).

    Raises:
        ValueError: If runs_dir appears misconfigured
    """
    resolved = runs_dir.resolve()
    health_subdir = resolved / "health"

    # If neither the parent nor health subdir exists, warn but don't fail
    # This allows fresh startup before any health runs have been executed
    if not resolved.exists() and not health_subdir.exists():
        logger.warning(
            "runs_dir does not exist and may not have been initialized",
            extra={"runs_dir": str(resolved)},
        )
        return

    # If runs/health exists, this is the expected canonical structure
    if health_subdir.exists():
        return

    # Check if user passed runs/health directly (doubled-path bug symptom)
    if resolved.exists() and any(resolved.iterdir()):
        # runs/ exists but no health subdir - might be misconfigured
        logger.warning(
            "runs_dir may be misconfigured: expected parent 'runs' with 'health' subdirectory",
            extra={"runs_dir": str(resolved)},
        )


def _compute_health_root(runs_dir: Path) -> Path:
    """Compute the health root directory for artifact resolution.

    The health root is where artifact-backed source of truth lives:
    - If runs_dir is the parent (e.g., 'runs'), health_root = runs_dir / 'health'
    - If runs_dir is already the health leaf (e.g., 'runs/health'), health_root = runs_dir

    This distinction is critical because plan artifacts (external-analysis/*-next-check-plan.json)
    live under runs/health/external-analysis/, not directly under runs/external-analysis/.

    Args:
        runs_dir: The normalized runs directory

    Returns:
        The health root path for artifact resolution
    """
    resolved = runs_dir.resolve()

    # If runs_dir itself is the health directory, it's already the health root
    if resolved.name == "health":
        return resolved

    # Otherwise, compute health_root as runs_dir / "health"
    health_root = resolved / "health"

    # If health directory exists, use it; otherwise fall back to runs_dir
    # (allows operation before first health run completes)
    if health_root.exists():
        return health_root

    # Fall back to runs_dir if health doesn't exist yet
    return resolved
