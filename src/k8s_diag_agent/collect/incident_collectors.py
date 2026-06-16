"""Collection functions for incident snapshot capture.

This module contains functions for executing kubectl commands
and collecting Kubernetes resources for incident evidence.
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Sequence

from .incident_models import DeploymentSummary, EventSummary, PodSummary
from .incident_parsers import (
    parse_deployment_summary,
    parse_event_summary,
    parse_pod_summary,
)
from .live_snapshot_helpers import _extract_items

_logger = logging.getLogger(__name__)

# Subprocess timeout for kubectl commands
KUBECTL_COMMAND_TIMEOUT_SECONDS = 60

# Default lookback for events
DEFAULT_SINCE_HOURS = 2


def kubectl(context: str | None, *args: str) -> str:
    """Execute a kubectl command with optional context."""
    command = ["kubectl"]
    if context:
        command.extend(["--context", context])
    command.extend(args)
    return _run_command(command)


def _run_command(command: Sequence[str]) -> str:
    """Execute a command with timeout."""
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=KUBECTL_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"`{command[0]}` timed out after {KUBECTL_COMMAND_TIMEOUT_SECONDS}s"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command `{command[0]}` not found") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr if exc.stderr else exc.stdout
        raise RuntimeError(f"`{command[0]}` failed: {stderr[:200]}") from exc
    return result.stdout


def collect_pods(
    namespace: str,
    context: str | None,
) -> tuple[list[PodSummary], list[str]]:
    """Collect pod evidence for namespace."""
    errors: list[str] = []
    try:
        output = kubectl(context, "get", "pods", "-n", namespace, "-o", "json")
    except RuntimeError as exc:
        errors.append(f"pods_collection: {exc}")
        return [], errors

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"pods_parse: {exc}")
        return [], errors

    items = _extract_items(payload)
    pods: list[PodSummary] = []

    for item in items:
        pod_summary = parse_pod_summary(item)
        pods.append(pod_summary)

    return pods, errors


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
