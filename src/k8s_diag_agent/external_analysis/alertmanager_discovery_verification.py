"""Alertmanager endpoint verification.

This module provides functions for verifying Alertmanager instances by checking
their health and readiness endpoints.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class VerificationResult:
    """Result of Alertmanager endpoint verification."""

    healthy: bool
    ready: bool
    version: str | None = None
    error: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def verify_alertmanager_endpoint(endpoint: str, timeout_seconds: float = 5.0) -> VerificationResult:
    """Verify an Alertmanager endpoint by checking /-/healthy and /-/ready.

    Both endpoints must respond successfully for a candidate to become
    auto-tracked. This ensures we don't track non-functional Alertmanagers.

    Args:
        endpoint: Base URL of the Alertmanager instance
        timeout_seconds: Timeout for each health check request

    Returns:
        VerificationResult with health/ready status and version info
    """

    endpoint = endpoint.rstrip("/")

    # Check /-/healthy endpoint
    healthy, healthy_error = _check_endpoint(f"{endpoint}/-/healthy", timeout_seconds)

    if not healthy:
        return VerificationResult(
            healthy=False,
            ready=False,
            error=healthy_error,
        )

    # Check /-/ready endpoint
    ready, ready_error = _check_endpoint(f"{endpoint}/-/ready", timeout_seconds)

    if not ready:
        return VerificationResult(
            healthy=True,
            ready=False,
            error=ready_error,
        )

    # Get version info from /api/v2/status (auxiliary, non-blocking)
    version, _ = _get_version(f"{endpoint}/api/v2/status", timeout_seconds)

    return VerificationResult(
        healthy=True,
        ready=True,
        version=version,
    )


def _check_endpoint(url: str, timeout: float) -> tuple[bool, str | None]:
    """Check if an endpoint returns a successful response."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if 200 <= response.status < 300:
                return True, None
            return False, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return False, f"Connection failed: {exc.reason}"
    except TimeoutError:
        return False, "Request timed out"


def _get_version(url: str, timeout: float) -> tuple[str | None, str | None]:
    """Get Alertmanager version from status endpoint."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read())
            version_info = data.get("data", {}).get("versionInfo", {})
            version = version_info.get("version")
            return version, None
    except (OSError, json.JSONDecodeError, ValueError, TimeoutError):
        # REVIEWED: Non-fatal version fetch fallback.
        # Version is auxiliary info - failures should not block Alertmanager discovery.
        return None, None
