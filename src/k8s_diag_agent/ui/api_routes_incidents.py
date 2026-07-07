"""Incident management route definitions.

Split from api_routes_incidents.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from .api_contract_types import APIOperation, APIResponse, APISchema
from .api_request_schemas import (
    INCIDENT_REVIEW_PACKET_REQUEST_SCHEMA,
    INCIDENT_SNAPSHOT_REQUEST_SCHEMA,
)

# =============================================================================
# Incident management endpoints
# =============================================================================

INCIDENT_ROUTES: tuple[APIOperation, ...] = (
    APIOperation(
        method="GET",
        path="/api/incidents",
        summary="List incidents",
        description="List all incidents with optional status filter.",
        tags=("incidents",),
        operation_id="list_incidents",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_incidents_list_dispatch",
        query_params=("status", "limit", "page"),
        responses=(
            APIResponse(
                status_code=200,
                description="List of incidents",
                schema=APISchema(
                    type="object",
                    properties={
                        "incidents": {"type": "array", "items": {"type": "object"}},
                        "total": {"type": "integer"},
                    },
                ),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/incidents/{incident_id}",
        summary="Get incident detail",
        description="Get details for a specific incident by ID.",
        tags=("incidents",),
        operation_id="get_incident_detail",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_incident_detail_dispatch",
        match="template",
        path_params=("incident_id",),
        responses=(
            APIResponse(
                status_code=200,
                description="Incident details",
                schema=APISchema(
                    type="object",
                    description="Incident object",
                ),
            ),
            APIResponse(status_code=404, description="Incident not found"),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/incidents/{incident_id}/automatic-diagnosis-review/handoff",
        summary="Get automatic diagnosis review handoff",
        description="Get the handoff artifact for automatic diagnosis review.",
        tags=("incidents", "diagnosis"),
        operation_id="get_incident_diagnosis_review_handoff",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_incident_handoff_dispatch",
        match="template",
        path_params=("incident_id",),
        responses=(
            APIResponse(
                status_code=200,
                description="Diagnosis review handoff",
                schema=APISchema(type="object"),
            ),
            APIResponse(status_code=404, description="Incident or handoff not found"),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/incidents/snapshot",
        summary="Capture incident snapshot",
        description="Capture a cluster snapshot for the current state.",
        tags=("incidents",),
        operation_id="capture_incident_snapshot",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_incident_snapshot_dispatch",
        request_schema=INCIDENT_SNAPSHOT_REQUEST_SCHEMA,
        responses=(
            APIResponse(
                status_code=200,
                description="Snapshot captured",
                schema=APISchema(
                    type="object",
                    properties={
                        "snapshot_id": {"type": "string"},
                        "incident_id": {"type": "string"},
                    },
                ),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/incidents/review-packet",
        summary="Generate incident review packet",
        description="Generate a diagnostic review packet for an incident.",
        tags=("incidents",),
        operation_id="create_incident_review_packet",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_incident_review_packet_dispatch",
        request_schema=INCIDENT_REVIEW_PACKET_REQUEST_SCHEMA,
        responses=(
            APIResponse(
                status_code=200,
                description="Review packet generated",
                schema=APISchema(
                    type="object",
                    properties={
                        "review_packet_id": {"type": "string"},
                        "incident_id": {"type": "string"},
                    },
                ),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/incidents/{incident_id}/diagnosis-loop/one-pass",
        summary="Run one-pass diagnosis loop",
        description="Execute a single pass of the diagnosis loop for an incident.",
        tags=("incidents", "diagnosis"),
        operation_id="run_incident_diagnosis_loop",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_incident_diagnosis_loop_dispatch",
        match="template",
        path_params=("incident_id",),
        responses=(
            APIResponse(
                status_code=200,
                description="Diagnosis loop completed",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/incidents/{incident_id}/one-pass-diagnosis",
        summary="Run one-pass diagnosis service",
        description="Execute one-pass diagnosis using the diagnosis service.",
        tags=("incidents", "diagnosis"),
        operation_id="run_incident_one_pass_diagnosis",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_incident_one_pass_diagnosis_dispatch",
        match="template",
        path_params=("incident_id",),
        responses=(
            APIResponse(
                status_code=200,
                description="Diagnosis completed",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/incidents/{incident_id}/automatic-diagnosis-loop/one-pass",
        summary="Run automatic diagnosis loop one-pass",
        description="Execute automatic diagnosis loop one-pass using the real collector.",
        tags=("incidents", "diagnosis"),
        operation_id="run_incident_automatic_diagnosis_loop",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_incident_automatic_diagnosis_loop_dispatch",
        match="template",
        path_params=("incident_id",),
        responses=(
            APIResponse(
                status_code=200,
                description="Automatic diagnosis completed",
                schema=APISchema(type="object"),
            ),
        ),
    ),
)
