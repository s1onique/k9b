"""Collection functions for incident snapshot capture.

This module contains functions for executing kubectl commands
and collecting Kubernetes resources for incident evidence.

All kubectl invocations use bounded execution to prevent memory growth
from large collections.

Read-only tool output is projected through the budget and spill infrastructure
to ensure bounded LLM-visible context.

Reference: ACT-K9B-HOLMESGPT-TOOL-INFRA-PRODUCTION-SEAM01
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..security.kubectl_subprocess import (
    run_kubectl,
)
from .incident_models import DeploymentSummary, EventSummary, PodSummary
from .incident_parsers import (
    parse_deployment_summary,
    parse_event_summary,
    parse_pod_summary,
)
from .live_snapshot_helpers import _extract_items
from .tool_output_projection import project_read_only_tool_output
from .tool_spill_types import ToolOutputSpillResult

_logger = logging.getLogger(__name__)

# Subprocess timeout for kubectl commands
KUBECTL_COMMAND_TIMEOUT_SECONDS = 60

# Default lookback for events
DEFAULT_SINCE_HOURS = 2


def kubectl(context: str | None, *args: str) -> str:
    """Execute a kubectl command with optional context.

    Uses bounded execution to prevent memory growth from large collections.
    """
    command = ["kubectl"]
    if context:
        command.extend(["--context", context])
    command.extend(args)
    return run_kubectl(
        command,
        timeout_seconds=KUBECTL_COMMAND_TIMEOUT_SECONDS,
    )


def _build_projection_metadata(
    spill_result: ToolOutputSpillResult,
    source_tool: str,
) -> dict[str, Any]:
    """Build projection metadata from spill result.

    This metadata is operator-visible and describes the spill/truncation state.

    Args:
        spill_result: Result from spill_tool_output()
        source_tool: Source tool identifier

    Returns:
        Metadata dict with spill, truncation, and provenance info
    """
    return {
        "source_tool": source_tool,
        "schema_version": spill_result.schema_version,
        "spill_occurred": spill_result.spill_occurred,
        "spill_reason": spill_result.spill_reason,
        "raw_artifact_id": spill_result.raw_artifact_id,
        "raw_artifact_path": spill_result.raw_artifact_path,
        "raw_size_bytes": spill_result.raw_size_bytes,
        "llm_visible_size_bytes": spill_result.llm_visible_size_bytes,
        "content_type": spill_result.content_type,
        "error": spill_result.error,
        "provenance": spill_result.provenance,
    }


def collect_pods(
    namespace: str,
    context: str | None,
    artifact_dir: Path | None = None,
) -> tuple[list[PodSummary], list[str], dict[str, Any]]:
    """Collect pod evidence for namespace.

    Args:
        namespace: Kubernetes namespace
        context: Kubernetes context (None for default)
        artifact_dir: Optional directory for tool output artifacts

    Returns:
        Tuple of (pods, errors, projection_metadata).
        The projection_metadata contains spill/budget info for observability.
    """
    errors: list[str] = []
    projection_metadata: dict[str, Any] = {}
    try:
        output = kubectl(context, "get", "pods", "-n", namespace, "-o", "json")
    except RuntimeError as exc:
        errors.append(f"pods_collection: {exc}")
        return [], errors, projection_metadata

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"pods_parse: {exc}")
        return [], errors, projection_metadata

    # Project output through budget and spill infrastructure
    spill_result = project_read_only_tool_output(
        source_tool="kubectl_get",
        raw_output=payload,
        artifact_dir=artifact_dir,
        provenance={"namespace": namespace, "resource": "pods"},
    )
    projection_metadata = _build_projection_metadata(spill_result, "kubectl_get")

    items = _extract_items(payload)
    pods: list[PodSummary] = []

    for item in items:
        pod_summary = parse_pod_summary(item)
        pods.append(pod_summary)

    return pods, errors, projection_metadata


def collect_deployments(
    namespace: str,
    context: str | None,
) -> tuple[list[DeploymentSummary], list[str]]:
    """Collect deployment evidence for namespace."""
    errors: list[str] = []
    try:
        output = kubectl(context, "get", "deployments", "-n", namespace, "-o", "json")
    except RuntimeError as exc:
        errors.append(f"deployments_collection: {exc}")
        return [], errors

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"deployments_parse: {exc}")
        return [], errors

    items = _extract_items(payload)
    deployments: list[DeploymentSummary] = []

    for item in items:
        deployment_summary = parse_deployment_summary(item)
        deployments.append(deployment_summary)

    return deployments, errors


def collect_events(
    namespace: str,
    context: str | None,
    since_hours: int,
) -> tuple[list[EventSummary], list[str]]:
    """Collect event evidence for namespace."""
    errors: list[str] = []
    try:
        output = kubectl(
            context,
            "get",
            "events",
            "-n",
            namespace,
            "--field-selector",
            f"lastTimestamp>=now-{since_hours}h",
            "-o",
            "json",
        )
    except RuntimeError:
        # Fallback without time filter
        try:
            output = kubectl(context, "get", "events", "-n", namespace, "-o", "json")
        except RuntimeError as exc:
            errors.append(f"events_collection: {exc}")
            return [], errors

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"events_parse: {exc}")
        return [], errors

    items = _extract_items(payload)
    events: list[EventSummary] = []

    for item in items:
        event_summary = parse_event_summary(item)
        events.append(event_summary)

    return events, errors


__all__ = [
    "collect_pods",
    "collect_deployments",
    "collect_events",
    "kubectl",
    "DEFAULT_SINCE_HOURS",
]
