"""Live snapshot parsing and health summarization helpers."""

from __future__ import annotations

__all__ = [
    "_extract_items",
    "_int_or_zero",
    "_parse_server_version",
    "_pod_owned_by_job",
    "_summarize_node_conditions",
    "_summarize_pod_health",
]

from collections.abc import Mapping, Sequence
from typing import Any

from .cluster_snapshot import (
    NodeConditionCounts,
    PodHealthCounts,
)


def _extract_items(payload: Any) -> list[Mapping[str, Any]]:
    """Extract items list from kubectl JSON response."""
    if isinstance(payload, Mapping):
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    return []


def _int_or_zero(value: Any) -> int:
    """Convert value to int, returning 0 on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_server_version(output: str) -> str:
    """Parse git version from kubectl version --output json."""
    import json

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "kubectl version output could not be parsed; ensure your kubectl supports `version --output json`."
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("kubectl version output is not a JSON object.")
    server_info: Any = payload.get("serverVersion")
    if not isinstance(server_info, dict):
        raise RuntimeError("kubectl version output is missing the `serverVersion` section.")
    git_version = server_info.get("gitVersion")
    if not isinstance(git_version, str) or not git_version:
        raise RuntimeError(
            "kubectl version output is missing `serverVersion.gitVersion`; ensure the control plane is reachable."
        )
    return git_version


def _pod_owned_by_job(pod: Mapping[str, Any]) -> bool:
    """Check if a pod is owned by a Job."""
    metadata = pod.get("metadata") or {}
    owners = metadata.get("ownerReferences") or []
    for owner in owners:
        if not isinstance(owner, Mapping):
            continue
        if str(owner.get("kind") or "").lower() == "job":
            return True
    return False


def _summarize_node_conditions(
    nodes: Sequence[Mapping[str, Any]]
) -> NodeConditionCounts:
    """Summarize node conditions into NodeConditionCounts."""
    total = len(nodes)
    ready = 0
    not_ready = 0
    memory_pressure = 0
    disk_pressure = 0
    pid_pressure = 0
    network_unavailable = 0
    for node in nodes:
        status = node.get("status") or {}
        conditions = status.get("conditions") or []
        saw_ready = False
        node_ready = False
        for condition in conditions:
            cond_type = condition.get("type")
            cond_status = condition.get("status")
            if cond_type == "Ready":
                saw_ready = True
                if cond_status == "True":
                    node_ready = True
            elif cond_type == "MemoryPressure" and cond_status == "True":
                memory_pressure += 1
            elif cond_type == "DiskPressure" and cond_status == "True":
                disk_pressure += 1
            elif cond_type == "PIDPressure" and cond_status == "True":
                pid_pressure += 1
            elif cond_type == "NetworkUnavailable" and cond_status == "True":
                network_unavailable += 1
        if saw_ready and node_ready:
            ready += 1
        else:
            not_ready += 1
    return NodeConditionCounts(
        total=total,
        ready=ready,
        not_ready=not_ready,
        memory_pressure=memory_pressure,
        disk_pressure=disk_pressure,
        pid_pressure=pid_pressure,
        network_unavailable=network_unavailable,
    )


def _summarize_pod_health(
    pods: Sequence[Mapping[str, Any]]
) -> PodHealthCounts:
    """Summarize pod health into PodHealthCounts."""
    non_running = 0
    pending = 0
    crash_loop_backoff = 0
    image_pull_backoff = 0
    completed_job_pods = 0
    for pod in pods:
        status = pod.get("status") or {}
        phase = str(status.get("phase") or "").lower()
        counted_non_running = False
        if phase == "succeeded" and _pod_owned_by_job(pod):
            completed_job_pods += 1
            continue
        if phase and phase != "running":
            non_running += 1
            counted_non_running = True
        if phase == "pending":
            pending += 1
        container_statuses = status.get("containerStatuses") or []
        for container in container_statuses:
            reason_found: str | None = None
            for attr in ("state", "lastState"):
                state_section = container.get(attr) or {}
                if not isinstance(state_section, Mapping):
                    continue
                waiting = state_section.get("waiting")
                if not isinstance(waiting, Mapping):
                    continue
                reason = str(waiting.get("reason") or "")
                if reason == "CrashLoopBackOff":
                    crash_loop_backoff += 1
                    reason_found = reason
                elif reason == "ImagePullBackOff":
                    image_pull_backoff += 1
                    reason_found = reason
                if reason_found:
                    if not counted_non_running:
                        non_running += 1
                        counted_non_running = True
                    break
            if reason_found:
                break
    return PodHealthCounts(
        non_running=non_running,
        pending=pending,
        crash_loop_backoff=crash_loop_backoff,
        image_pull_backoff=image_pull_backoff,
        completed_job_pods=completed_job_pods,
    )
