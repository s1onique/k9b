"""Parsing functions for incident snapshot collection.

This module contains functions for parsing Kubernetes API responses
into incident evidence models.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..security.sanitizer import sanitize_payload
from .incident_models import (
    DeploymentSummary,
    EventSummary,
    PodHealthStatus,
    PodSummary,
)
from .live_snapshot_helpers import _int_or_zero

if TYPE_CHECKING:
    pass


def parse_pod_summary(pod: Mapping[str, Any]) -> PodSummary:
    """Parse a pod into a minimal PodSummary."""
    metadata = pod.get("metadata") or {}
    status = pod.get("status") or {}

    name = str(metadata.get("name") or "")
    ns = str(metadata.get("namespace") or "")

    phase = str(status.get("phase") or "Unknown").lower()

    # Get container status for detailed health info
    container_statuses = status.get("containerStatuses") or []
    restart_count = 0
    health_status = PodHealthStatus.UNKNOWN
    reason = None
    message = None
    is_failing = False

    for container in container_statuses:
        restart_count += _int_or_zero(container.get("restartCount"))
        # Check waiting state
        for attr in ("state", "lastState"):
            state_section = container.get(attr) or {}
            if not isinstance(state_section, dict):
                continue
            waiting = state_section.get("waiting")
            if not isinstance(waiting, dict):
                continue
            waiting_reason = str(waiting.get("reason") or "")
            if waiting_reason == "CrashLoopBackOff":
                health_status = PodHealthStatus.CRASH_LOOP
                reason = waiting_reason
                message = str(waiting.get("message") or "")
                is_failing = True
            elif waiting_reason == "ImagePullBackOff":
                health_status = PodHealthStatus.IMAGE_PULL_ERROR
                reason = waiting_reason
                message = str(waiting.get("message") or "")
                is_failing = True

    # Set phase-based status if not already set
    if health_status == PodHealthStatus.UNKNOWN:
        if phase == "running":
            health_status = PodHealthStatus.RUNNING
        elif phase == "pending":
            health_status = PodHealthStatus.PENDING
            is_failing = True
        elif phase in ("failed", "succeeded"):
            health_status = PodHealthStatus.FAILED
            is_failing = phase == "failed"

    # Extract image refs
    spec = pod.get("spec") or {}
    containers = spec.get("containers") or []
    image_refs: list[str] = []
    for container in containers:
        image = container.get("image")
        if image:
            image_refs.append(str(image))

    # Get node
    node = spec.get("nodeName")

    # Get reason/message from pod status conditions
    conditions = status.get("conditions") or []
    readiness_not_ready = False
    for cond in conditions:
        if str(cond.get("type") or "") == "Ready":
            if cond.get("status") != "True":
                readiness_not_ready = True
                if not is_failing:
                    is_failing = True
                    reason = "NotReady"
                    message = str(cond.get("message") or "")

    # Set READINESS_FAILURE status if running but not ready (after checking container statuses)
    if health_status == PodHealthStatus.RUNNING and readiness_not_ready:
        health_status = PodHealthStatus.READINESS_FAILURE
        is_failing = True
        if not reason:
            reason = "ReadinessFailure"
        if not message:
            message = "Pod is Running but not Ready"

    # Sanitize the summary
    sanitized_message = message
    if message:
        sanitized = sanitize_payload(message)
        if isinstance(sanitized, str):
            sanitized_message = sanitized

    return PodSummary(
        name=name,
        namespace=ns,
        phase=phase,
        health_status=health_status,
        restart_count=restart_count,
        node=node,
        image_refs=tuple(image_refs),
        reason=reason,
        message=sanitized_message,
        is_failing=is_failing,
    )


def parse_deployment_summary(deployment: Mapping[str, Any]) -> DeploymentSummary:
    """Parse a deployment into a minimal DeploymentSummary."""
    metadata = deployment.get("metadata") or {}
    spec = deployment.get("spec") or {}
    status = deployment.get("status") or {}

    name = str(metadata.get("name") or "")
    ns = str(metadata.get("namespace") or "")

    replicas = _int_or_zero(spec.get("replicas"))
    available_replicas = _int_or_zero(status.get("availableReplicas"))
    ready_replicas = _int_or_zero(status.get("readyReplicas"))
    updated_replicas = _int_or_zero(status.get("updatedReplicas"))

    # available = all replicas are available
    available = available_replicas >= replicas and replicas > 0

    return DeploymentSummary(
        name=name,
        namespace=ns,
        replicas=replicas,
        available_replicas=available_replicas,
        ready_replicas=ready_replicas,
        updated_replicas=updated_replicas,
        available=available,
    )


def parse_event_summary(event: Mapping[str, Any]) -> EventSummary:
    """Parse an event into a minimal EventSummary."""
    metadata = event.get("metadata") or {}
    involved = event.get("involvedObject") or {}

    # Sanitize message to prevent credential leakage
    raw_message = str(event.get("message") or "")
    sanitized_message = raw_message
    if raw_message:
        sanitized = sanitize_payload(raw_message)
        if isinstance(sanitized, str):
            sanitized_message = sanitized

    return EventSummary(
        namespace=str(metadata.get("namespace") or ""),
        name=str(metadata.get("name") or ""),
        type=str(event.get("type") or "Normal"),
        reason=str(event.get("reason") or ""),
        message=sanitized_message,
        involved_object_kind=str(involved.get("kind") or ""),
        involved_object_name=str(involved.get("name") or ""),
        count=_int_or_zero(event.get("count")),
        last_timestamp=str(
            metadata.get("lastTimestamp") or metadata.get("eventTime") or ""
        ),
    )


__all__ = [
    "parse_pod_summary",
    "parse_deployment_summary",
    "parse_event_summary",
]
