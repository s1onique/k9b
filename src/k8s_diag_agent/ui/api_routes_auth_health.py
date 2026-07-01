"""Auth, health, and runtime route definitions.

Split from api_routes_registry.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from .api_contract_types import APISchema, APIOperation, APIResponse


# =============================================================================
# Auth endpoints (public - no auth required)
# =============================================================================

AUTH_ROUTES: tuple[APIOperation, ...] = (
    APIOperation(
        method="GET",
        path="/api/auth/status",
        summary="Get authentication status",
        description="Check if the current session is authenticated and get session info.",
        tags=("auth",),
        operation_id="get_auth_status",
        requires_auth=False,
        responses=(
            APIResponse(
                status_code=200,
                description="Authentication status",
                schema=APISchema(
                    type="object",
                    description="Session status",
                    properties={
                        "authenticated": {"type": "boolean"},
                        "username": {"type": ["string", "null"]},
                    },
                ),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/auth/me",
        summary="Get current user info",
        description="Get information about the currently authenticated user.",
        tags=("auth",),
        operation_id="get_auth_me",
        requires_auth=False,
        responses=(
            APIResponse(
                status_code=200,
                description="Current user info",
                schema=APISchema(
                    type="object",
                    description="User info",
                    properties={
                        "username": {"type": "string"},
                        "authenticated": {"type": "boolean"},
                    },
                ),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/auth/login",
        summary="Login",
        description="Authenticate with username and password to create a session.",
        tags=("auth",),
        operation_id="post_auth_login",
        requires_auth=False,
        request_schema=APISchema(
            type="object",
            description="Login credentials",
            properties={
                "username": {"type": "string"},
                "password": {"type": "string"},
            },
            required=["username", "password"],
        ),
        responses=(
            APIResponse(
                status_code=200,
                description="Login successful",
                schema=APISchema(
                    type="object",
                    properties={"message": {"type": "string"}},
                ),
            ),
            APIResponse(status_code=401, description="Invalid credentials"),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/auth/logout",
        summary="Logout",
        description="Terminate the current session.",
        tags=("auth",),
        operation_id="post_auth_logout",
        requires_auth=False,
        responses=(
            APIResponse(
                status_code=200,
                description="Logout successful",
                schema=APISchema(
                    type="object",
                    properties={"message": {"type": "string"}},
                ),
            ),
        ),
    ),
)


# =============================================================================
# Health endpoints (public - no auth required)
# =============================================================================

HEALTH_ROUTES: tuple[APIOperation, ...] = (
    APIOperation(
        method="GET",
        path="/api/health",
        summary="Backend health check",
        description="Kubernetes liveness/readiness probe endpoint. Returns 200 if backend is healthy.",
        tags=("health",),
        operation_id="get_health",
        requires_auth=False,
        responses=(
            APIResponse(
                status_code=200,
                description="Backend is healthy",
                schema=APISchema(
                    type="object",
                    properties={"status": {"type": "string"}, "timestamp": {"type": "string"}},
                ),
            ),
            APIResponse(status_code=500, description="Backend is unhealthy"),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/health/details",
        summary="Detailed health diagnostics",
        description="Self-diagnosis endpoint available even when /api/health returns 500.",
        tags=("health",),
        operation_id="get_health_details",
        requires_auth=False,
        responses=(
            APIResponse(
                status_code=200,
                description="Health details",
                schema=APISchema(
                    type="object",
                    description="Detailed health info",
                    properties={
                        "status": {"type": "string"},
                        "checks": {"type": "object"},
                        "timestamp": {"type": "string"},
                    },
                ),
            ),
        ),
    ),
)


# =============================================================================
# Runtime status endpoints
# =============================================================================

RUNTIME_ROUTES: tuple[APIOperation, ...] = (
    APIOperation(
        method="GET",
        path="/api/runtime-status",
        summary="Get runtime status",
        description="Get current runtime status and diagnostics information.",
        tags=("runtime",),
        operation_id="get_runtime_status",
        responses=(
            APIResponse(
                status_code=200,
                description="Runtime status",
                schema=APISchema(type="object"),
            ),
        ),
    ),
)
