"""Next-check and AlertManager source route definitions.

Split from api_routes_incidents.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from .api_contract_types import APIOperation, APIResponse, APISchema
from .api_request_schemas import (
    ALERTMANAGER_RELEVANCE_FEEDBACK_REQUEST_SCHEMA,
    ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA,
    BATCH_EXECUTION_REQUEST_SCHEMA,
    DETERMINISTIC_PROMOTION_REQUEST_SCHEMA,
    NEXT_CHECK_APPROVAL_REQUEST_SCHEMA,
    NEXT_CHECK_EXECUTION_REQUEST_SCHEMA,
    USEFULNESS_FEEDBACK_REQUEST_SCHEMA,
)

# =============================================================================
# Next-check and AlertManager source endpoints
# =============================================================================

NEXTCHECK_ROUTES: tuple[APIOperation, ...] = (
    APIOperation(
        method="POST",
        path="/api/deterministic-next-check/promote",
        summary="Promote deterministic next-check",
        description="Promote a deterministic next-check candidate.",
        tags=("incidents",),
        operation_id="promote_deterministic_next_check",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_deterministic_promotion_dispatch",
        request_schema=DETERMINISTIC_PROMOTION_REQUEST_SCHEMA,
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
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_next_check_execution_dispatch",
        request_schema=NEXT_CHECK_EXECUTION_REQUEST_SCHEMA,
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
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_next_check_approval_dispatch",
        request_schema=NEXT_CHECK_APPROVAL_REQUEST_SCHEMA,
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
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_usefulness_feedback_dispatch",
        request_schema=USEFULNESS_FEEDBACK_REQUEST_SCHEMA,
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
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_relevance_feedback_dispatch",
        request_schema=ALERTMANAGER_RELEVANCE_FEEDBACK_REQUEST_SCHEMA,
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
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_batch_next_check_execution_dispatch",
        request_schema=BATCH_EXECUTION_REQUEST_SCHEMA,
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
        path="/api/runs/{run_id}/alertmanager-sources/action",
        summary="Perform AlertManager source action",
        description="Perform an action (promote/disable) on an AlertManager source. The source_id is in the request body to support slashes in source identifiers.",
        tags=("incidents",),
        operation_id="perform_alertmanager_source_action",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_source_action_dispatch",
        match="template",
        path_params=("run_id",),
        request_schema=ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA,
        responses=(
            APIResponse(
                status_code=200,
                description="Action performed",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    # -----------------------------------------------------------------------------
    # AlertManager sources review packets
    # -----------------------------------------------------------------------------
    APIOperation(
        method="GET",
        path="/api/runs/{run_id}/alertmanager-sources/review-packet",
        summary="Get AlertManager sources review packet",
        description="Get the review packet explaining why multiple AlertManager sources were discovered.",
        tags=("incidents", "alertmanager"),
        operation_id="get_alertmanager_sources_review_packet",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_sources_review_packet_dispatch",
        match="template",
        path_params=("run_id",),
        responses=(
            APIResponse(
                status_code=200,
                description="Review packet generated",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet",
        summary="Get AlertManager source debug packet",
        description="Get a debug packet for a specific AlertManager source with probe and discovery details.",
        tags=("incidents", "alertmanager"),
        operation_id="get_alertmanager_source_debug_packet",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_source_debug_packet_dispatch",
        match="template",
        path_params=("run_id", "source_id"),
        responses=(
            APIResponse(
                status_code=200,
                description="Debug packet generated",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="POST",
        path="/api/runs/{run_id}/alertmanager-sources/{source_id}/debug-packet/probe",
        summary="Probe AlertManager source now",
        description="Run a live probe on the AlertManager source and return updated debug packet.",
        tags=("incidents", "alertmanager"),
        operation_id="probe_alertmanager_source",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_source_debug_packet_probe_dispatch",
        match="template",
        path_params=("run_id", "source_id"),
        responses=(
            APIResponse(
                status_code=200,
                description="Probe completed",
                schema=APISchema(type="object"),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/runs/{run_id}/alertmanager-sources/{source_id}/promotion-review",
        summary="Get AlertManager source promotion review",
        description="Get a pre-promotion review assessing risk before promoting a source to manual.",
        tags=("incidents", "alertmanager"),
        operation_id="get_alertmanager_source_promotion_review",
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_alertmanager_source_promotion_review_dispatch",
        match="template",
        path_params=("run_id", "source_id"),
        responses=(
            APIResponse(
                status_code=200,
                description="Promotion review generated",
                schema=APISchema(type="object"),
            ),
        ),
    ),
)
