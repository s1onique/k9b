"""Adapter functions for normalized handler signature.

This module provides adapter wrappers that convert handlers with varying signatures
to the normalized signature: (handler, query, path_params).

Each adapter bridges the gap between the registry's dispatch signature and the
existing handler implementation. This allows incremental migration without
rewriting all handlers at once.

Next-check and AlertManager adapters are in api_dispatch_adapters_nextcheck.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api_contract_types import UIIndexContext
    from .server import HealthUIRequestHandler

# Re-export nextcheck/alertmanager adapters from the split module
# These are intentional re-exports for backwards compatibility with existing imports
from .api_dispatch_adapters_nextcheck import (  # noqa: F401
    handle_alertmanager_relevance_feedback_dispatch,
    handle_alertmanager_source_action_dispatch,
    handle_alertmanager_source_debug_packet_dispatch,
    handle_alertmanager_source_debug_packet_probe_dispatch,
    handle_alertmanager_source_promotion_review_dispatch,
    handle_alertmanager_sources_review_packet_dispatch,
    handle_batch_next_check_execution_dispatch,
    handle_deterministic_promotion_dispatch,
    handle_next_check_approval_dispatch,
    handle_next_check_execution_dispatch,
    handle_usefulness_feedback_dispatch,
)

# =============================================================================
# OpenAPI adapters
# =============================================================================


def handle_openapi_json_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/openapi.json."""
    from .api_openapi import handle_openapi_json

    handle_openapi_json(handler)


def handle_openapi_docs_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/docs."""
    from .api_openapi import handle_openapi_docs

    handle_openapi_docs(handler)


# =============================================================================
# Auth adapters
# =============================================================================


def handle_status_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/auth/status."""
    from .auth_routes import handle_status

    handle_status(handler)


def handle_me_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/auth/me."""
    from .auth_routes import handle_me

    handle_me(handler)


def handle_login_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/auth/login."""
    from .auth_routes import handle_login

    handle_login(handler)


def handle_logout_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/auth/logout."""
    from .auth_routes import handle_logout

    handle_logout(handler)


# =============================================================================
# Health adapters
# =============================================================================


def handle_health_route_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/health."""
    from .api_health import handle_health_route

    handle_health_route(handler)


def handle_health_details_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/health/details."""
    from .api_health_details import handle_health_details as _handle

    _handle(handler)


# =============================================================================
# Runtime status adapter
# =============================================================================


def handle_runtime_status_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/runtime-status."""
    from .api_runtime_status import handle_runtime_status_route

    handle_runtime_status_route(handler)


# =============================================================================
# Incident adapters (GET routes)
# =============================================================================


def handle_incidents_list_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/incidents."""
    from .server_incident_reads import handle_incidents_list_route

    handle_incidents_list_route(handler, query)


def handle_incident_detail_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/incidents/{incident_id}."""
    from .server_incident_reads import handle_incident_detail_route

    incident_id = path_params.get("incident_id", "")
    # Build the full path for the existing handler
    path = f"/api/incidents/{incident_id}"
    handle_incident_detail_route(handler, path)


def handle_incident_handoff_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/incidents/{incident_id}/automatic-diagnosis-review/handoff."""
    from .server_incident_reads import handle_automatic_diagnosis_review_handoff_route

    incident_id = path_params.get("incident_id", "")
    path = f"/api/incidents/{incident_id}/automatic-diagnosis-review/handoff"
    handle_automatic_diagnosis_review_handoff_route(handler, path)


# =============================================================================
# Incident adapters (POST routes)
# =============================================================================


def handle_incident_snapshot_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/incidents/snapshot."""
    from .server_incident import handle_incident_snapshot_api

    handle_incident_snapshot_api(handler)


def handle_incident_review_packet_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/incidents/review-packet."""
    from .server_review_packet import handle_incident_review_packet_api

    handle_incident_review_packet_api(handler)


def handle_incident_diagnosis_loop_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/incidents/{incident_id}/diagnosis-loop/one-pass."""
    from .server_incident_diagnosis_loop import handle_incident_diagnosis_loop_one_pass_api

    incident_id = path_params.get("incident_id", "")
    handle_incident_diagnosis_loop_one_pass_api(handler, incident_id)


def handle_incident_one_pass_diagnosis_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/incidents/{incident_id}/one-pass-diagnosis."""
    from .server_incident_one_pass_diagnosis_service import (
        handle_incident_one_pass_diagnosis_service_api,
    )

    incident_id = path_params.get("incident_id", "")
    handle_incident_one_pass_diagnosis_service_api(handler, incident_id)


def handle_incident_automatic_diagnosis_loop_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for POST /api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass."""
    from .server_incident_automatic_diagnosis_loop import (
        handle_incident_automatic_diagnosis_loop_one_pass_api,
    )

    incident_id = path_params.get("incident_id", "")
    handle_incident_automatic_diagnosis_loop_one_pass_api(handler, incident_id)


# =============================================================================
# Run adapters
# =============================================================================


def handle_runs_list_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/runs."""
    from .server_runs_list_reads import handle_runs_list_route

    handle_runs_list_route(handler, query)


def handle_run_detail_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/run."""
    from .server_run_detail_reads import handle_run_detail_route

    handle_run_detail_route(handler, query)


def handle_fleet_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/fleet."""
    from .api import build_fleet_payload

    context = _load_context_from_query(handler, query)
    if context is None:
        return

    handler._send_json(build_fleet_payload(context))


def handle_proposals_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/proposals."""
    from .api import build_proposals_payload

    context = _load_context_from_query(handler, query)
    if context is None:
        return

    handler._send_json(build_proposals_payload(context))


def handle_cluster_detail_dispatch(
    handler: HealthUIRequestHandler,
    query: str,
    path_params: dict[str, str],
) -> None:
    """Dispatch adapter for GET /api/cluster-detail."""
    from urllib.parse import parse_qs

    from .api import build_cluster_detail_payload

    params = parse_qs(query)
    label = params.get("cluster_label", [None])[0]

    context = _load_context_from_query(handler, query)
    if context is None:
        return

    handler._send_json(build_cluster_detail_payload(context, cluster_label=label))


# Note: handle_notifications_dispatch is in api_notifications_dispatch.py


# =============================================================================
# Helper utilities
# =============================================================================


def _load_context_from_query(
    handler: HealthUIRequestHandler,
    query: str,
) -> UIIndexContext | None:
    """Load UI context with run_id from query parameters.

    Args:
        handler: The HTTP request handler instance
        query: Query string containing optional run_id param

    Returns:
        UI context or None if not available
    """
    from urllib.parse import parse_qs

    params = parse_qs(query)
    selected_run_id = params.get("run_id", [None])[0]
    return handler._load_context(requested_run_id=selected_run_id)
