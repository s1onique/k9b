"""Configuration validation for the scoped HTTP seam.

ACT-K9B-HULK-PROMOTION-SCOPED-HTTP-CLIENT-RESPONSIBILITY-SPLIT01.

Owns the typed configuration validation that the active scoped
HTTP path must satisfy before any wire attempt:

* backend URL presence (``MISSING_BACKEND_URL``);
* internal API token presence (``MISSING_INTERNAL_TOKEN``);
* canonical endpoint construction.

The reason vocabulary is intentionally closed. The mapper does
not inspect exception text; the active scoped path raises a
distinct exception type per missing field so the caller can
carry the exact reason into the typed transport variant.
"""

from __future__ import annotations

from collections.abc import Callable

# Request-ID factory: injectable so tests can use deterministic IDs.
# Re-exported from the facade for callers that prefer the typed
# client surface.
RequestIdFactory = Callable[[], str]


def _generate_request_id() -> str:
    """Default request-id factory: UUID4 hex."""
    import uuid

    return f"promotion-request-{uuid.uuid4().hex}"


class ScopedSchedulerBackendConfigError(Exception):
    """Raised when the scheduler backend URL is not configured."""


class ScopedSchedulerMissingTokenError(Exception):
    """Raised when the scheduler internal API token is not configured."""


def _require_valid_backend_url(base_url: str) -> str:
    """Validate the backend URL; raise typed exception when missing."""
    backend_url = (base_url or "").strip()
    if not backend_url:
        raise ScopedSchedulerBackendConfigError(
            "scoped scheduler backend URL is not configured"
        )
    return backend_url


def _require_valid_internal_token(token: str | None) -> str:
    """Validate the internal API token; raise typed exception when missing."""
    if not token:
        raise ScopedSchedulerMissingTokenError(
            "scoped scheduler internal API token is not configured"
        )
    return token


def require_authenticated_config(
    base_url: str,
    token: str | None,
) -> tuple[str, str]:
    """Validate configuration; raise a typed exception naming the
    missing field.

    The active scoped path MUST NOT silently send an unauthenticated
    request or a request with a missing backend URL. Each missing
    field raises its own typed exception so the caller can carry
    the exact reason into the active scoped path.
    """
    backend_url = _require_valid_backend_url(base_url)
    internal_token = _require_valid_internal_token(token)
    return backend_url, internal_token


def canonical_promote_endpoint(base_url: str) -> str:
    """Build the canonical scoped promotion endpoint URL.

    The active scoped path constructs exactly one endpoint per
    request -- the trailing-slash-insensitive
    ``/api/internal/incidents/promote-alert-signals`` path. The
    path is canonical to preserve the run-id-source-identity-signal
    scope contract; callers MUST NOT override it.
    """
    return f"{base_url.rstrip('/')}/api/internal/incidents/promote-alert-signals"


__all__ = [
    "RequestIdFactory",
    "ScopedSchedulerBackendConfigError",
    "ScopedSchedulerMissingTokenError",
    "canonical_promote_endpoint",
    "require_authenticated_config",
]
