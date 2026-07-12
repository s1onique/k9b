"""Request schema helpers for OpenAPI requestBody definitions.

This module provides helper functions for building request body schemas
for POST endpoints in the API contract registry.

All helpers produce APISchema dataclasses that can be assigned to
APIOperation.request_schema fields.

Usage:
    from .api_request_schemas import (
        json_request_body,
        string_schema,
        object_schema,
        nullable_string_schema,
        array_schema,
    )

    APIOperation(
        method="POST",
        path="/api/next-check-execution",
        request_schema=json_request_body(
            description="Execute a next-check candidate.",
            schema=object_schema(
                properties={
                    "candidateId": string_schema(),
                    "clusterLabel": string_schema(),
                },
                required=("candidateId", "clusterLabel"),
            ),
        ),
        ...
    )
"""

from __future__ import annotations

from typing import Any

from .api_contract_types import APISchema


def string_schema(description: str | None = None) -> APISchema:
    """Create a string schema."""
    return APISchema(type="string", description=description or "")


def nullable_string_schema(description: str | None = None) -> APISchema:
    """Create a nullable string schema (string or null)."""
    return APISchema(
        type="string",
        description=description or "",
    )


def integer_schema(description: str | None = None) -> APISchema:
    """Create an integer schema."""
    return APISchema(type="integer", description=description or "")


def boolean_schema(description: str | None = None) -> APISchema:
    """Create a boolean schema."""
    return APISchema(type="boolean", description=description or "")


def number_schema(description: str | None = None) -> APISchema:
    """Create a number schema."""
    return APISchema(type="number", description=description or "")


def array_schema(
    items: APISchema,
    description: str | None = None,
) -> APISchema:
    """Create an array schema with the given item schema."""
    return APISchema(
        type="array",
        description=description or "",
        items={"type": items.type},  # Simplified for OpenAPI output
    )


def object_schema(
    properties: dict[str, APISchema],
    *,
    required: tuple[str, ...] = (),
    description: str | None = None,
    additional_properties: bool = False,
) -> APISchema:
    """Create an object schema with the given properties.

    Args:
        properties: Mapping of property names to their schemas.
        required: Tuple of required property names.
        description: Optional description for the schema.
        additional_properties: If True, allows additional properties.
            Defaults to False (no additional properties).

    Returns:
        An APISchema suitable for use as a request_schema. This matches the
        pattern used in api_routes_auth_health.py lines 72-80 for the login
        endpoint, where .properties contains the field name -> schema mappings.
    """
    # Build field schemas - preserve all schema attributes including nested additional_properties
    field_schemas: dict[str, dict[str, Any]] = {}
    for name, schema in properties.items():
        field_schema: dict[str, Any] = {"type": schema.type}
        if schema.description:
            field_schema["description"] = schema.description
        # Preserve additional_properties for nested object schemas
        if schema.additional_properties is not None:
            field_schema["additionalProperties"] = schema.additional_properties
        field_schemas[name] = field_schema

    # _build_schema_dict copies schema.properties verbatim to result["properties"]
    # So APISchema.properties must be the field schemas dict directly
    # (same pattern as login schema in api_routes_auth_health.py)
    return APISchema(
        type="object",
        description=description or "",
        properties=field_schemas,
        required=list(required) if required else None,
        additional_properties=additional_properties,
    )


def json_request_body(
    description: str,
    schema: APISchema,
    *,
    required: bool = True,
) -> APISchema:
    """Create a JSON request body schema.

    The schema is returned as an APISchema that will be serialized
    into the OpenAPI requestBody object with content-type application/json.

    Args:
        description: Human-readable description of the request body.
        schema: The schema for the request body content.
        required: Whether the request body is required. Defaults to True.
    """
    # Return the schema with description attached for request body use
    # The api_contract.py _build_operation_dict will wrap this appropriately
    return schema


# =============================================================================
# Pre-built request schemas for common operations
# =============================================================================

# -----------------------------------------------------------------------------
# Incident snapshot
# -----------------------------------------------------------------------------

INCIDENT_SNAPSHOT_REQUEST_SCHEMA = object_schema(
    properties={
        "namespace": string_schema("Kubernetes namespace to capture snapshot for"),
        # Use sinceHours (camelCase) to match frontend wire format - backend must accept this
        "sinceHours": integer_schema("Hours to look back for events (default: 2)"),
    },
    required=("namespace",),
    description="Incident snapshot capture request",
)


# -----------------------------------------------------------------------------
# Incident review packet
# -----------------------------------------------------------------------------

INCIDENT_REVIEW_PACKET_REQUEST_SCHEMA = object_schema(
    properties={
        "bundle": object_schema(
            properties={},
            description="Incident evidence bundle",
            additional_properties=True,
        ),
        "format": string_schema("Output format (default: markdown)"),
    },
    required=("bundle",),
    description="Incident review packet generation request",
)


# -----------------------------------------------------------------------------
# Next-check execution
# -----------------------------------------------------------------------------

NEXT_CHECK_EXECUTION_REQUEST_SCHEMA = object_schema(
    properties={
        "candidateId": string_schema("Unique candidate identifier"),
        "candidateIndex": integer_schema("Zero-based index of candidate in plan"),
        "clusterLabel": string_schema("Target cluster label"),
        "planArtifactPath": nullable_string_schema("Explicit plan artifact path"),
    },
    required=("clusterLabel",),
    description="Next-check execution request",
)


# -----------------------------------------------------------------------------
# Next-check approval
# -----------------------------------------------------------------------------

NEXT_CHECK_APPROVAL_REQUEST_SCHEMA = object_schema(
    properties={
        "candidateId": string_schema("Unique candidate identifier"),
        "candidateIndex": integer_schema("Zero-based index of candidate in plan"),
        "clusterLabel": string_schema("Target cluster label"),
    },
    required=("clusterLabel",),
    description="Next-check approval request",
)


# -----------------------------------------------------------------------------
# Deterministic next-check promotion
# -----------------------------------------------------------------------------

DETERMINISTIC_PROMOTION_REQUEST_SCHEMA = object_schema(
    properties={
        "clusterLabel": string_schema("Cluster label for the promoted check"),
        "description": string_schema("Description of the deterministic check"),
        "method": nullable_string_schema("Execution method (e.g., kubectl, helm)"),
        "evidenceNeeded": array_schema(
            items=string_schema("Evidence description"),
            description="List of evidence items needed",
        ),
        "workstream": nullable_string_schema("Workstream (incident, evidence, drift)"),
        "urgency": nullable_string_schema("Urgency level (high, medium, low)"),
        "whyNow": nullable_string_schema("Reason this check is needed now"),
        "topProblem": nullable_string_schema("Top problem statement"),
        "priorityScore": number_schema("Priority score for ordering"),
        "context": nullable_string_schema("Target context/path"),
    },
    required=("clusterLabel", "description"),
    description="Deterministic next-check promotion request",
)


# -----------------------------------------------------------------------------
# Usefulness feedback
# -----------------------------------------------------------------------------

USEFULNESS_FEEDBACK_REQUEST_SCHEMA = object_schema(
    properties={
        "artifactPath": string_schema("Path to the execution artifact"),
        "usefulnessClass": string_schema("Usefulness class (useful, partial, noisy, empty)"),
        "usefulnessSummary": nullable_string_schema("Optional summary of usefulness"),
        "reviewStage": nullable_string_schema("Stage at which feedback is given"),
        "workstream": nullable_string_schema("Workstream context"),
        "problemClass": nullable_string_schema("Problem classification"),
        "judgmentScope": nullable_string_schema("Scope of judgment"),
        "reviewerConfidence": nullable_string_schema("Reviewer confidence level"),
    },
    required=("artifactPath", "usefulnessClass"),
    description="Usefulness feedback request",
)


# -----------------------------------------------------------------------------
# AlertManager relevance feedback
# -----------------------------------------------------------------------------

ALERTMANAGER_RELEVANCE_FEEDBACK_REQUEST_SCHEMA = object_schema(
    properties={
        "artifactPath": string_schema("Path to the execution artifact"),
        "alertmanagerRelevance": string_schema("Relevance class (relevant, not_relevant, noisy, unsure)"),
        "alertmanagerRelevanceSummary": nullable_string_schema("Optional relevance summary"),
    },
    required=("artifactPath", "alertmanagerRelevance"),
    description="AlertManager relevance feedback request",
)


# -----------------------------------------------------------------------------
# Batch next-check execution
# -----------------------------------------------------------------------------

BATCH_EXECUTION_REQUEST_SCHEMA = object_schema(
    properties={
        "runId": string_schema("Run ID to execute batch for"),
        "dryRun": boolean_schema("If true, only compute eligibility without executing"),
    },
    required=("runId",),
    description="Batch next-check execution request",
)


# -----------------------------------------------------------------------------
# AlertManager source action
# -----------------------------------------------------------------------------

ALERTMANAGER_SOURCE_ACTION_REQUEST_SCHEMA = object_schema(
    properties={
        "sourceId": string_schema("AlertManager source identifier (may contain slashes)"),
        "action": string_schema("Action to perform (promote, disable)"),
        "clusterLabel": string_schema("Cluster label for override persistence"),
        "reason": nullable_string_schema("Optional reason for audit trail"),
    },
    required=("sourceId", "action", "clusterLabel"),
    description="AlertManager source action request. sourceId is in body to support slashes in identifiers.",
)


# -----------------------------------------------------------------------------
# AlertManager source probe
# -----------------------------------------------------------------------------

ALERTMANAGER_SOURCE_PROBE_REQUEST_SCHEMA = object_schema(
    properties={
        "sourceId": string_schema(
            "AlertManager source identifier (may contain slashes)"
        ),
    },
    required=("sourceId",),
    description=(
        "AlertManager source probe request. sourceId is in body to keep the "
        "POST path stable regardless of the source identifier content."
    ),
)
