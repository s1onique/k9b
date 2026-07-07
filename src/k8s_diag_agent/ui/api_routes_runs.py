"""Run and fleet route definitions.

Split from api_routes_incidents.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from .api_contract_types import APIOperation, APIResponse, APISchema

# =============================================================================
# Run and fleet endpoints
# =============================================================================

RUN_ROUTES: tuple[APIOperation, ...] = (
    APIOperation(
        method="GET",
        path="/api/runs",
        summary="List runs",
        description="List all diagnostic runs with pagination.",
        tags=("incidents",),
        operation_id="list_runs",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_runs_list_dispatch",
        query_params=("limit", "page", "cluster_label"),
        responses=(
            APIResponse(
                status_code=200,
                description="List of runs",
                schema=APISchema(
                    type="object",
                    properties={
                        "runs": {"type": "array", "items": {"type": "object"}},
                        "total": {"type": "integer"},
                    },
                ),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/run",
        summary="Get selected run detail",
        description="Get details for the selected run.",
        tags=("incidents",),
        operation_id="get_run_detail",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_run_detail_dispatch",
        query_params=("run_id",),
        responses=(
            APIResponse(
                status_code=200,
                description="Run details",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/fleet",
        summary="Get fleet overview",
        description="Get overview of all clusters in the fleet.",
        tags=("incidents",),
        operation_id="get_fleet",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_fleet_dispatch",
        responses=(
            APIResponse(
                status_code=200,
                description="Fleet overview",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/proposals",
        summary="Get proposals",
        description="Get diagnostic proposals for the current run.",
        tags=("incidents",),
        operation_id="get_proposals",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_proposals_dispatch",
        responses=(
            APIResponse(
                status_code=200,
                description="Proposals list",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/cluster-detail",
        summary="Get cluster detail",
        description="Get detailed information for a specific cluster.",
        tags=("incidents",),
        operation_id="get_cluster_detail",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_cluster_detail_dispatch",
        query_params=("cluster_label",),
        responses=(
            APIResponse(
                status_code=200,
                description="Cluster detail",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/notifications",
        summary="List notifications",
        description="List notifications with optional filters.",
        tags=("incidents",),
        operation_id="list_notifications",
        handler="k8s_diag_agent.ui.api_notifications_dispatch:handle_notifications_dispatch",
        query_params=("kind", "cluster_label", "search", "limit", "page"),
        responses=(
            APIResponse(
                status_code=200,
                description="Notifications list",
                schema=APISchema(
                    type="object",
                    properties={
                        "notifications": {"type": "array", "items": {"type": "object"}},
                        "total": {"type": "integer"},
                    },
                ),
            ),
        ),
    ),
)
