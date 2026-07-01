"""OpenAPI contract registry and schema generator for k9b API.

This module provides a machine-readable API contract for k9b backend endpoints.
It is used by:
- /api/openapi.json endpoint (generated schema)
- /api/docs endpoint (Swagger UI via static HTML)
- test_openapi_contract.py (completeness gate)

The registry defines all /api/* routes with their metadata (tags, summary,
description, auth requirements, response schemas). Routes are documented
at the registry level, not in handler code, to enable contract-first validation.

The routes are defined in api_routes_registry.py and types in api_contract_types.py
to keep each file below LLM-friendly thresholds.
"""

from __future__ import annotations

from typing import Any

from .api_contract_types import APIOperation, APISchema
from .api_routes_registry import API_ROUTES

# =============================================================================
# Helpers
# =============================================================================

def get_all_operation_keys() -> set[tuple[str, str]]:
    """Get all (method, path) tuples from the registry."""
    return {(op.method.lower(), op.path) for op in API_ROUTES}


def get_operation_by_key(method: str, path: str) -> APIOperation | None:
    """Look up an operation by method and path."""
    for op in API_ROUTES:
        if op.method.lower() == method.lower() and op.path == path:
            return op
    return None


def build_openapi_schema() -> dict[str, Any]:
    """Build the complete OpenAPI 3.1 schema from the registry.

    Returns:
        OpenAPI 3.1 schema dict ready for serialization.
    """
    schema: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "k9b API",
            "version": "0.1.0",
            "summary": "k9b backend API",
            "description": (
                "Machine-readable API contract for k9b incidents, snapshots, "
                "diagnosis loop, auth, runtime status, and diagnostics endpoints."
            ),
        },
        "servers": [{"url": "/"}],
        "paths": {},
        "tags": [
            {"name": "auth", "description": "Admin authentication/session endpoints."},
            {"name": "health", "description": "Backend health check and diagnostics."},
            {
                "name": "incidents",
                "description": "Incident listing, detail, snapshots, and review packets.",
            },
            {
                "name": "diagnosis",
                "description": "Read-only automatic/manual diagnosis loop endpoints.",
            },
            {"name": "runtime", "description": "Runtime status and diagnostics endpoints."},
        ],
    }

    # Group operations by path
    paths_dict: dict[str, dict[str, dict[str, Any]]] = {}
    for op in API_ROUTES:
        if op.path not in paths_dict:
            paths_dict[op.path] = {}
        method_lower = op.method.lower()
        paths_dict[op.path][method_lower] = _build_operation_dict(op)

    schema["paths"] = paths_dict
    return schema


def _build_operation_dict(op: APIOperation) -> dict[str, Any]:
    """Build a single operation dict from an APIOperation."""
    operation: dict[str, Any] = {
        "summary": op.summary,
        "description": op.description,
        "operationId": op.operation_id,
        "tags": list(op.tags),
        "responses": {},
    }

    # Add auth requirement
    if not op.requires_auth:
        operation["security"] = []

    # Add path params
    if op.path_params:
        operation["parameters"] = [
            {
                "name": param,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
            for param in op.path_params
        ]

    # Add query params
    if op.query_params:
        params = operation.get("parameters", [])
        for param in op.query_params:
            params.append({
                "name": param,
                "in": "query",
                "required": False,
                "schema": {"type": "string"},
            })
        operation["parameters"] = params

    # Add request body
    if op.request_schema:
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _build_schema_dict(op.request_schema),
                }
            },
        }

    # Add responses
    for resp in op.responses:
        resp_dict: dict[str, Any] = {
            "description": resp.description,
        }
        if resp.schema:
            resp_dict["content"] = {
                resp.content_type: {
                    "schema": _build_schema_dict(resp.schema),
                }
            }
        operation["responses"][str(resp.status_code)] = resp_dict

    return operation


def _build_schema_dict(schema: APISchema) -> dict[str, Any]:
    """Build a JSON Schema dict from an APISchema."""
    result: dict[str, Any] = {"type": schema.type}
    if schema.description:
        result["description"] = schema.description
    if schema.items:
        result["items"] = schema.items
    if schema.properties:
        result["properties"] = schema.properties
    if schema.required:
        result["required"] = schema.required
    return result
