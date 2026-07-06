"""Content kind-specific projection handlers.

This module provides projection functions for each content kind.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .projection_builder import ProjectionBuilder, ProjectionConfig


def project_lab_result(
    content_id: str,
    file_path: Path,
    data: dict[str, Any],
    config: ProjectionConfig | None = None,
) -> list[Any]:
    """Create projections for a lab result.

    Args:
        content_id: Unique content ID.
        file_path: Source file path.
        data: Parsed file content.
        config: Projection configuration.

    Returns:
        List of projection records.
    """
    if config is None:
        config = ProjectionConfig()

    builder = (
        ProjectionBuilder(content_id, "lab_result", config)
        .add_status("ok" if data.get("ok") else "failed")
        .add_safe_title(f"Lab result: {data.get('scenario', 'unknown')}")
        .add_safe_summary(
            f"Scenario: {data.get('scenario', 'unknown')}, "
            f"Cluster mode: {data.get('cluster_mode', 'unknown')}"
        )
        .add_timestamp_field("created_at", data.get("started_at"))
        .add_timestamp_field("updated_at", data.get("finished_at"))
    )

    # Add counts if available
    if "incident_id" in data:
        builder.add_field("object_name", data.get("incident_id"))

    projections = [builder.build_summary()]

    detail = builder.build_detail()
    if detail:
        projections.append(detail)

    return projections


def project_trace_capture_summary(
    content_id: str,
    file_path: Path,
    data: dict[str, Any],
    config: ProjectionConfig | None = None,
) -> list[Any]:
    """Create projections for a trace capture summary.

    Args:
        content_id: Unique content ID.
        file_path: Source file path.
        data: Parsed file content.
        config: Projection configuration.

    Returns:
        List of projection records.
    """
    if config is None:
        config = ProjectionConfig()

    builder = (
        ProjectionBuilder(content_id, "trace_capture_summary", config)
        .add_safe_title(f"Trace capture: {data.get('trace_count', 0)} traces")
        .add_safe_summary(
            f"Service: {data.get('service_name', 'unknown')}, "
            f"Traces: {data.get('trace_count', 0)}, "
            f"Spans: {data.get('span_count', 0)}"
        )
        .add_timestamp_field("created_at", data.get("generated_at"))
        .add_field(
            "counts",
            {
                "traces": data.get("trace_count", 0),
                "spans": data.get("span_count", 0),
                "http_spans": data.get("http_span_count", 0),
            },
        )
    )

    projections = [builder.build_summary()]

    detail = builder.build_detail()
    if detail:
        projections.append(detail)

    return projections


def project_perf_baseline_summary(
    content_id: str,
    file_path: Path,
    data: dict[str, Any],
    config: ProjectionConfig | None = None,
) -> list[Any]:
    """Create projections for a performance baseline summary.

    Args:
        content_id: Unique content ID.
        file_path: Source file path.
        data: Parsed file content.
        config: Projection configuration.

    Returns:
        List of projection records.
    """
    if config is None:
        config = ProjectionConfig()

    builder = (
        ProjectionBuilder(content_id, "perf_baseline_summary", config)
        .add_safe_title(
            f"Perf baseline: {data.get('iteration_count', 0)} iterations"
        )
        .add_safe_summary(
            f"Endpoints: {data.get('endpoint_count', 0)}, "
            f"Iterations: {data.get('iteration_count', 0)}, "
            f"Slowest: {data.get('slowest_endpoint', 'unknown')}"
        )
        .add_timestamp_field("created_at", data.get("generated_at"))
        .add_field(
            "counts",
            {
                "traces": data.get("total_traces", 0),
                "spans": data.get("total_spans", 0),
                "iterations": data.get("iteration_count", 0),
                "endpoints": data.get("endpoint_count", 0),
            },
        )
    )

    projections = [builder.build_summary()]

    detail = builder.build_detail()
    if detail:
        projections.append(detail)

    return projections


def project_incident(
    content_id: str,
    file_path: Path,
    data: dict[str, Any],
    config: ProjectionConfig | None = None,
) -> list[Any]:
    """Create projections for an incident.

    Args:
        content_id: Unique content ID.
        file_path: Source file path.
        data: Parsed file content.
        config: Projection configuration.

    Returns:
        List of projection records.
    """
    if config is None:
        config = ProjectionConfig()

    # Extract safe fields
    title = data.get("title") or data.get("name") or str(content_id)
    summary = data.get("summary") or data.get("description", "")
    status = data.get("status", "unknown")
    severity = data.get("severity", "unknown")

    builder = (
        ProjectionBuilder(content_id, "incident", config)
        .add_status(status)
        .add_severity(severity)
        .add_safe_title(title)
        .add_safe_summary(summary)
        .add_namespace(data.get("namespace"))
        .add_timestamp_field("created_at", data.get("created_at"))
        .add_timestamp_field("updated_at", data.get("updated_at"))
    )

    projections = [builder.build_summary()]

    detail = builder.build_detail()
    if detail:
        projections.append(detail)

    return projections


def project_generic(
    content_id: str,
    content_kind: str,
    file_path: Path,
    data: dict[str, Any],
    config: ProjectionConfig | None = None,
) -> list[Any]:
    """Create projections for generic content.

    Uses a safe subset of available fields.

    Args:
        content_id: Unique content ID.
        content_kind: Type of content.
        file_path: Source file path.
        data: Parsed file content.
        config: Projection configuration.

    Returns:
        List of projection records.
    """
    if config is None:
        config = ProjectionConfig()

    builder = ProjectionBuilder(content_id, content_kind, config)

    # Extract common safe fields
    title = data.get("title") or data.get("name") or file_path.name
    summary = data.get("summary") or data.get("description", "")

    builder.add_safe_title(title).add_safe_summary(summary)

    # Try to add timestamps
    for ts_field in ["created_at", "updated_at", "generated_at", "timestamp"]:
        if ts_field in data:
            builder.add_timestamp_field("created_at", data[ts_field])
            break

    projections = [builder.build_summary()]

    detail = builder.build_detail()
    if detail:
        projections.append(detail)

    return projections


# Projection handler registry
_PROJECTION_HANDLERS: dict[str, Any] = {
    "lab_result": project_lab_result,
    "trace_capture_summary": project_trace_capture_summary,
    "perf_baseline_summary": project_perf_baseline_summary,
    "incident": project_incident,
}


def create_projections(
    content_id: str,
    content_kind: str,
    file_path: Path,
    data: dict[str, Any],
    config: ProjectionConfig | None = None,
) -> list[Any]:
    """Create projections for content.

    Dispatches to the appropriate content-kind handler.

    Args:
        content_id: Unique content ID.
        content_kind: Type of content.
        file_path: Source file path.
        data: Parsed file content.
        config: Projection configuration.

    Returns:
        List of projection records.
    """
    handler = _PROJECTION_HANDLERS.get(content_kind)
    if handler:
        return handler(content_id, file_path, data, config)  # type: ignore[no-any-return]

    # Fall back to generic handler
    return project_generic(content_id, content_kind, file_path, data, config)
