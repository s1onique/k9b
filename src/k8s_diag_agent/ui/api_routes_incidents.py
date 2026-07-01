"""Incident, run, fleet, and next-check route definitions.

Split from api_routes_registry.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from .api_contract_types import APIOperation, APIResponse, APISchema

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


# =============================================================================
# Next-check endpoints
# =============================================================================

NEXTCHECK_ROUTES: tuple[APIOperation, ...] = (
    APIOperation(
        method="POST",
        path="/api/deterministic-next-check/promote",
        summary="Promote deterministic next-check",
        description="Promote a deterministic next-check candidate.",
        tags=("incidents",),
        operation_id="promote_deterministic_next_check",
        responses=(
            APIResponse(
                status_code=200,
                description="Promotion successful",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/next-check-execution",
        summary="Execute next-check",
        description="Execute a next-check with manual input.",
        tags=("incidents",),
        operation_id="execute_next_check",
        responses=(
            APIResponse(
                status_code=200,
                description="Execution completed",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/next-check-approval",
        summary="Approve next-check",
        description="Approve a next-check for execution.",
        tags=("incidents",),
        operation_id="approve_next_check",
        responses=(
            APIResponse(
                status_code=200,
                description="Approval recorded",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/next-check-execution-usefulness",
        summary="Record next-check usefulness feedback",
        description="Record operator feedback on next-check usefulness.",
        tags=("incidents",),
        operation_id="record_next_check_usefulness",
        responses=(
            APIResponse(
                status_code=200,
                description="Feedback recorded",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/alertmanager-relevance-feedback",
        summary="Record AlertManager relevance feedback",
        description="Record operator feedback on AlertManager source relevance.",
        tags=("incidents",),
        operation_id="record_alertmanager_relevance_feedback",
        responses=(
            APIResponse(
                status_code=200,
                description="Feedback recorded",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/run-batch-next-check-execution",
        summary="Batch execute next-checks",
        description="Execute multiple next-checks in batch.",
        tags=("incidents",),
        operation_id="run_batch_next_check_execution",
        responses=(
            APIResponse(
                status_code=200,
                description="Batch execution completed",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/runs/{run_id}/alertmanager-sources/{source_id}/action",
        summary="Perform AlertManager source action",
        description="Perform an action (promote/disable) on an AlertManager source.",
        tags=("incidents",),
        operation_id="perform_alertmanager_source_action",
        path_params=("run_id", "source_id"),
        responses=(
            APIResponse(
                status_code=200,
                description="Action performed",
                schema=APISchema(type="object"),
            ),
        ),
    ),
)
