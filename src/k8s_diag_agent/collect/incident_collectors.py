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
from typing import TYPE_CHECKING, Any

from ..kubernetes_auth import resolve_process_auth_mode
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
from .tool_projection_metadata import (
    build_tool_projection_metadata,
)
from .tool_spill_types import ToolOutputSpillResult

if TYPE_CHECKING:
    from ..kubernetes_auth import AuthMode

_logger = logging.getLogger(__name__)

# Subprocess timeout for kubectl commands
KUBECTL_COMMAND_TIMEOUT_SECONDS = 60

# Default lookback for events
DEFAULT_SINCE_HOURS = 2


# Local alias for backward compatibility; delegates to shared helper
_resolve_auth_mode = resolve_process_auth_mode


def kubectl(context: str | None, *args: str, auth_mode: AuthMode | None = None) -> str:
    """Execute a kubectl command with optional context.

    Uses bounded execution to prevent memory growth from large collections.

    Args:
        context: Kubernetes context (None for in-cluster default)
        *args: kubectl arguments
        auth_mode: Auth mode for in-cluster authentication. When None,
            falls back to process-level auth mode resolution.
    """
    command = ["kubectl"]
    if context:
        command.extend(["--context", context])
    command.extend(args)
    return run_kubectl(
        command,
        timeout_seconds=KUBECTL_COMMAND_TIMEOUT_SECONDS,
        auth_mode=auth_mode,
    )


def _build_projection_metadata(
    spill_result: ToolOutputSpillResult,
    source_tool: str,
) -> dict[str, Any]:
    """Build projection metadata from spill result.

    DEPRECATED: Use build_tool_projection_metadata() from tool_projection_metadata instead.
    This wrapper maintains backward compatibility while delegating to the canonical implementation.

    Args:
        spill_result: Result from spill_tool_output()
        source_tool: Source tool identifier

    Returns:
        Metadata dict with spill, truncation, and provenance info
    """
    # Delegate to canonical implementation
    metadata = build_tool_projection_metadata(spill_result, source_tool)
    return metadata.to_dict()


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
        auth_mode = _resolve_auth_mode()
        output = kubectl(context, "get", "pods", "-n", namespace, "-o", "json", auth_mode=auth_mode)
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
    artifact_dir: Path | None = None,
) -> tuple[list[DeploymentSummary], list[str], dict[str, Any]]:
    """Collect deployment evidence for namespace.

    Args:
        namespace: Kubernetes namespace
        context: Kubernetes context (None for default)
        artifact_dir: Optional directory for tool output artifacts

    Returns:
        Tuple of (deployments, errors, projection_metadata).
        The projection_metadata contains spill/budget info for observability.
    """
    errors: list[str] = []
    projection_metadata: dict[str, Any] = {}
    try:
        auth_mode = _resolve_auth_mode()
        output = kubectl(context, "get", "deployments", "-n", namespace, "-o", "json", auth_mode=auth_mode)
    except RuntimeError as exc:
        errors.append(f"deployments_collection: {exc}")
        return [], errors, projection_metadata

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"deployments_parse: {exc}")
        return [], errors, projection_metadata

    # Project output through budget and spill infrastructure
    spill_result = project_read_only_tool_output(
        source_tool="kubectl_get",
        raw_output=payload,
        artifact_dir=artifact_dir,
        provenance={"namespace": namespace, "resource": "deployments"},
    )
    projection_metadata = _build_projection_metadata(spill_result, "kubectl_get")

    items = _extract_items(payload)
    deployments: list[DeploymentSummary] = []

    for item in items:
        deployment_summary = parse_deployment_summary(item)
        deployments.append(deployment_summary)

    return deployments, errors, projection_metadata


def collect_events(
    namespace: str,
    context: str | None,
    since_hours: int,
    artifact_dir: Path | None = None,
) -> tuple[list[EventSummary], list[str], dict[str, Any]]:
    """Collect event evidence for namespace.

    Args:
        namespace: Kubernetes namespace
        context: Kubernetes context (None for default)
        since_hours: Lookback window for events
        artifact_dir: Optional directory for tool output artifacts

    Returns:
        Tuple of (events, errors, projection_metadata).
        The projection_metadata contains spill/budget info for observability.
    """
    errors: list[str] = []
    projection_metadata: dict[str, Any] = {}
    auth_mode = _resolve_auth_mode()
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
            auth_mode=auth_mode,
        )
    except RuntimeError:
        # Fallback without time filter
        try:
            output = kubectl(context, "get", "events", "-n", namespace, "-o", "json", auth_mode=auth_mode)
        except RuntimeError as exc:
            errors.append(f"events_collection: {exc}")
            return [], errors, projection_metadata

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"events_parse: {exc}")
        return [], errors, projection_metadata

    # Project output through budget and spill infrastructure
    spill_result = project_read_only_tool_output(
        source_tool="kubectl_events",
        raw_output=payload,
        artifact_dir=artifact_dir,
        provenance={"namespace": namespace, "resource": "events"},
    )
    projection_metadata = _build_projection_metadata(spill_result, "kubectl_events")

    items = _extract_items(payload)
    events: list[EventSummary] = []

    for item in items:
        event_summary = parse_event_summary(item)
        events.append(event_summary)

    return events, errors, projection_metadata


__all__ = [
    "collect_pods",
    "collect_deployments",
    "collect_events",
    "kubectl",
    "DEFAULT_SINCE_HOURS",
]
