"""Type definitions for the OpenAPI contract registry.

This module contains the dataclass definitions used by the API contract.
Split from api_contract.py to keep file sizes below LLM-friendly thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class APISchema:
    """Schema definition for a response or request body."""

    type: str
    description: str = ""
    items: dict[str, Any] | None = None
    properties: dict[str, Any] | None = None
    required: list[str] | None = None
    additional_properties: bool | None = None


@dataclass(frozen=True)
class APIResponse:
    """Response definition for an API operation."""

    status_code: int | str
    description: str
    schema: APISchema | None = None
    content_type: str = "application/json"


@dataclass(frozen=True)
class APIOperation:
    """Definition for a single API operation (method + path)."""

    method: str  # GET, POST, PUT, PATCH, DELETE
    path: str
    summary: str
    description: str = ""
    tags: tuple[str, ...] = ()
    operation_id: str = ""
    requires_auth: bool = True
    request_schema: APISchema | None = None
    responses: tuple[APIResponse, ...] = ()
    path_params: tuple[str, ...] = ()  # Param names in path
    query_params: tuple[str, ...] = ()  # Param names in query string
    # Subset of query_params that must be supplied. Used by OpenAPI generation to
    # emit `required: True` so callers (including the generated TypeScript client)
    # treat the parameter as mandatory. Defaults to empty so existing optional
    # query params (limit/page/etc.) keep their existing semantics.
    required_query_params: tuple[str, ...] = ()
    # Dispatch metadata - use string import paths to avoid circular imports
    handler: str = ""  # Lazy import path, e.g., "k8s_diag_agent.ui.api_openapi:handle_openapi_json"
    match: str = "exact"  # "exact" or "template"
