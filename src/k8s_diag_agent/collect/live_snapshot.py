"""Live cluster snapshot helpers using kubectl/helm."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from ..identity.cluster import derive_cluster_uid
from .cluster_snapshot import (
    ClusterHealthSignals,
    ClusterSnapshot,
    ClusterSnapshotMetadata,
    CollectionStatus,
    CRDRecord,
    HelmReleaseRecord,
    NodeConditionCounts,
    PodHealthCounts,
    WarningEventSummary,
)


def list_kube_contexts() -> list[str]:
    output = _run_command(["kubectl", "config", "get-contexts", "-o", "name"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def collect_cluster_snapshot(context: str) -> ClusterSnapshot:
    """Collect cluster data while recording Helm/CRD issues instead of crashing."""
    metadata, node_conditions, pod_counts = _collect_metadata(context)
    helm_releases: dict[str, HelmReleaseRecord] = {}
    helm_error: str | None = None
    try:
        helm_releases = _collect_helm_releases(context)
    except RuntimeError as exc:
        helm_error = str(exc)

    crds: dict[str, CRDRecord] = {}
    missing_evidence: list[str] = []
    try:
        crds = _collect_crds(context)
    except RuntimeError:
        # Record CRD listing failure as missing evidence but keep the rest of the snapshot.
        missing_evidence.append("crd_list")

    job_failures, job_missing = _collect_job_failures(context)
    warning_events, warning_missing = _collect_warning_events(context)
    missing_evidence.extend(job_missing)
    missing_evidence.extend(warning_missing)

    status = CollectionStatus(
        helm_error=helm_error,
        missing_evidence=tuple(missing_evidence),
    )

    health_signals = ClusterHealthSignals(
        node_conditions=node_conditions,
        pod_counts=pod_counts,
        job_failures=job_failures,
        warning_events=warning_events,
    )

    return ClusterSnapshot(
        metadata=metadata,
        workloads={},
        metrics={},
        helm_releases=helm_releases,
        crds=crds,
        collection_status=status,
        health_signals=health_signals,
    )


def _collect_metadata(
    context: str,
) -> tuple[ClusterSnapshotMetadata, NodeConditionCounts, PodHealthCounts]:
    version_output = _kubectl(context, "version", "--output", "json")
    control_plane_version = _parse_server_version(version_output)
    node_payload = json.loads(_kubectl(context, "get", "nodes", "-o", "json"))
    node_items = _extract_items(node_payload)
    pod_payload = json.loads(
        _kubectl(context, "get", "pods", "--all-namespaces", "-o", "json")
    )
    pod_items = _extract_items(pod_payload)

    # Use shared helper for cluster_uid derivation (canonical identity)
    cluster_uid = derive_cluster_uid(context)

    metadata = ClusterSnapshotMetadata(
        cluster_id=context,  # Legacy display field (operator-facing)
        captured_at=datetime.now(UTC),
        control_plane_version=control_plane_version,
        node_count=len(node_items),
        cluster_uid=cluster_uid,  # Canonical identity (kube-system namespace UID)
        pod_count=len(pod_items),
    )
    return metadata, _summarize_node_conditions(node_items), _summarize_pod_health(pod_items)


def _collect_helm_releases(context: str) -> dict[str, HelmReleaseRecord]:
    output = _run_helm_command(context, "list", "--all-namespaces", "--output", "json")
    if not output.strip():
        return {}
    payload = json.loads(output)
    entries = payload if isinstance(payload, list) else []
    releases: dict[str, HelmReleaseRecord] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            release = HelmReleaseRecord.from_dict(entry)
        except KeyError:
            continue
        releases[release.key] = release
    return releases


def _collect_crds(context: str) -> dict[str, CRDRecord]:
    output = _kubectl(context, "get", "crds", "-o", "json")
    if not output.strip():
        return {}
    parsed = json.loads(output)
    items = parsed.get("items") if isinstance(parsed, dict) else []
    results: dict[str, CRDRecord] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") or {}
        name = metadata.get("name")
        if not name:
            continue
        try:
            record = CRDRecord.from_dict({"name": name, "spec": item.get("spec", {})})
        except KeyError:
            continue
        results[record.name] = record
    return results


def _collect_job_failures(context: str) -> tuple[int, tuple[str, ...]]:
    try:
        output = _kubectl(context, "get", "jobs", "--all-namespaces", "-o", "json")
    except RuntimeError:
        return 0, ("jobs",)
    payload = json.loads(output)
    failures = 0
    for entry in _extract_items(payload):
        status = entry.get("status") or {}
        failures += _int_or_zero(status.get("failed"))
    return failures, ()


def _collect_warning_events(
    context: str, limit: int = 6
) -> tuple[tuple[WarningEventSummary, ...], tuple[str, ...]]:
    try:
        output = _kubectl(
            context,
            "get",
            "events",
            "--all-namespaces",
            "--field-selector",
            "type=Warning",
            "--sort-by=.metadata.creationTimestamp",
            "-o",
            "json",
        )
    except RuntimeError:
        return (), ("events",)
    payload = json.loads(output)
    items = _extract_items(payload)
    sorted_items = sorted(
        items,
        key=lambda event: str(
            (event.get("metadata") or {}).get("creationTimestamp") or ""
        ),
        reverse=True,
    )
    events: list[WarningEventSummary] = []
    for entry in sorted_items:
        if len(events) >= limit:
            break
        metadata = entry.get("metadata") or {}
        namespace = str(metadata.get("namespace") or "")
        reason = str(entry.get("reason") or "")
        message = str(entry.get("message") or "")
        last_seen = str(
            metadata.get("lastTimestamp") or
            metadata.get("eventTime") or
            metadata.get("creationTimestamp") or ""
        )
        events.append(
            WarningEventSummary(
                namespace=namespace,
                reason=reason,
                message=message,
                count=_int_or_zero(entry.get("count")),
                last_seen=last_seen,
            )
        )
    return tuple(events), ()


def _pod_owned_by_job(pod: Mapping[str, Any]) -> bool:
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


def _extract_items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    return []


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _kubectl(context: str, *args: str) -> str:
    return _run_command(["kubectl", *args, "--context", context])


def _run_helm_command(context: str, *args: str) -> str:
    return _run_command(["helm", *args, "--kube-context", context])


def _run_command(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command `{command[0]}` not found. Ensure it is on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"`{command[0]}` failed: {message}") from exc
    return result.stdout


def _parse_server_version(output: str) -> str:
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


# Removed: _derive_cluster_uid moved to identity/cluster.py
