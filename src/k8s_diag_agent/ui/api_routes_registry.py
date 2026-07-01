"""Route registry for the k9b API contract.

This module combines all route definitions and exports the API_ROUTES tuple.
Split into multiple files to keep each below LLM-friendly thresholds.
"""

from __future__ import annotations

from .api_routes_auth_health import AUTH_ROUTES, HEALTH_ROUTES, RUNTIME_ROUTES
from .api_routes_incidents import INCIDENT_ROUTES, NEXTCHECK_ROUTES, RUN_ROUTES
from .api_routes_openapi import OPENAPI_ROUTES

# Combined registry of all API routes
API_ROUTES = (
    AUTH_ROUTES
    + HEALTH_ROUTES
    + RUNTIME_ROUTES
    + INCIDENT_ROUTES
    + RUN_ROUTES
    + NEXTCHECK_ROUTES
    + OPENAPI_ROUTES
)
