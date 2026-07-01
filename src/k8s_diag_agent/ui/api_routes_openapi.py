"""OpenAPI endpoint route definitions.

Split from api_routes_registry.py to keep file sizes below LLM-friendly thresholds.
These routes are public (no auth required) to allow API exploration.
"""

from __future__ import annotations

from .api_contract_types import APIOperation, APIResponse, APISchema

# =============================================================================
# OpenAPI endpoints (public - no auth required)
# =============================================================================

OPENAPI_ROUTES: tuple[APIOperation, ...] = (
    APIOperation(
        method="GET",
        path="/api/openapi.json",
        summary="Get OpenAPI schema",
        description="Returns the OpenAPI 3.1 schema as JSON for API introspection.",
        tags=("openapi",),
        operation_id="get_openapi_schema",
        requires_auth=False,
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_openapi_json_dispatch",
        responses=(
            APIResponse(
                status_code=200,
                description="OpenAPI 3.1 schema",
                schema=APISchema(
                    type="object",
                    description="OpenAPI 3.1 schema document",
                ),
            ),
        ),
    ),
    APIOperation(
        method="GET",
        path="/api/docs",
        summary="API documentation browser",
        description="Returns an API reference HTML page that loads /api/openapi.json.",
        tags=("openapi",),
        operation_id="get_api_docs",
        requires_auth=False,
        handler="k8s_diag_agent.ui.api_dispatch_adapters:handle_openapi_docs_dispatch",
        responses=(
            APIResponse(
                status_code=200,
                description="API reference HTML page",
                schema=APISchema(
                    type="string",
                    description="HTML document",
                ),
            ),
        ),
    ),
)
