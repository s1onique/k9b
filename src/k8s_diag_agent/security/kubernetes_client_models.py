"""Typed projection models for Kubernetes API responses.

These models are small projections of Kubernetes objects, used to prevent
raw Kubernetes object graph leakage into downstream artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NamespaceProjection:
    """Minimal projection of a Kubernetes Namespace."""
    name: str
    uid: str
    creation_timestamp: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NamespaceProjection:
        """Create from a Kubernetes Namespace dict."""
        metadata = data.get("metadata") or {}
        ts = metadata.get("creationTimestamp")
        creation_ts: datetime | None = None
        if ts:
            try:
                creation_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
        return cls(
            name=str(metadata.get("name") or ""),
            uid=str(metadata.get("uid") or ""),
            creation_timestamp=creation_ts,
        )


@dataclass(frozen=True)
class PodProjection:
    """Minimal projection of a Kubernetes Pod."""
    namespace: str
    name: str
    uid: str
    node_name: str | None = None
    phase: str | None = None
    ip: str | None = None
    host_ip: str | None = None
    creation_timestamp: datetime | None = None
    labels: dict[str, str] = field(default_factory=dict)
    restart_count: int = 0
    container_statuses: tuple[ContainerStatusProjection, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PodProjection:
        """Create from a Kubernetes Pod dict."""
        metadata = data.get("metadata") or {}
        spec = data.get("spec") or {}
        status = data.get("status") or {}

        ts = metadata.get("creationTimestamp")
        creation_ts: datetime | None = None
        if ts:
            try:
                creation_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        container_statuses_list: list[ContainerStatusProjection] = []
        container_statuses_data = status.get("containerStatuses") or []
        for cs_data in container_statuses_data:
            container_statuses_list.append(ContainerStatusProjection.from_dict(cs_data))

        return cls(
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            uid=str(metadata.get("uid") or ""),
            node_name=spec.get("nodeName"),
            phase=status.get("phase"),
            ip=status.get("podIP"),
            host_ip=status.get("hostIP"),
            creation_timestamp=creation_ts,
            labels=dict(metadata.get("labels") or {}),
            restart_count=sum(
                cs.get("restartCount", 0)
                for cs in container_statuses_data
            ),
            container_statuses=tuple(container_statuses_list),
        )


@dataclass(frozen=True)
class ContainerStatusProjection:
    """Minimal projection of a ContainerStatus."""
    name: str
    ready: bool
    restart_count: int
    state: str | None = None
    image: str | None = None
    image_id: str | None = None
    container_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContainerStatusProjection:
        """Create from a ContainerStatus dict."""
        state_data = data.get("state") or {}
        state_str: str | None = None
        if "running" in state_data:
            state_str = "running"
        elif "waiting" in state_data:
            state_str = "waiting"
        elif "terminated" in state_data:
            state_str = "terminated"

        return cls(
            name=str(data.get("name") or ""),
            ready=bool(data.get("ready", False)),
            restart_count=int(data.get("restartCount") or 0),
            state=state_str,
            image=data.get("image"),
            image_id=data.get("imageID"),
            container_id=data.get("containerID"),
        )


@dataclass(frozen=True)
class EventProjection:
    """Minimal projection of a Kubernetes Event."""
    namespace: str
    name: str
    event_type: str | None
    reason: str
    message: str
    involved_object_kind: str
    involved_object_name: str
    creation_timestamp: datetime | None = None
    count: int = 1
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    source_component: str | None = None
    source_host: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventProjection:
        """Create from a Kubernetes Event dict."""
        metadata = data.get("metadata") or {}
        involved = data.get("involvedObject") or {}
        source = data.get("source") or {}

        ts = metadata.get("creationTimestamp")
        creation_ts: datetime | None = None
        if ts:
            try:
                creation_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        first_ts = data.get("firstTimestamp")
        first_timestamp: datetime | None = None
        if first_ts:
            try:
                first_timestamp = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        last_ts = data.get("lastTimestamp")
        last_timestamp: datetime | None = None
        if last_ts:
            try:
                last_timestamp = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return cls(
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            event_type=data.get("type"),
            reason=str(data.get("reason") or ""),
            message=str(data.get("message") or ""),
            involved_object_kind=str(involved.get("kind") or ""),
            involved_object_name=str(involved.get("name") or ""),
            creation_timestamp=creation_ts,
            count=int(data.get("count") or 1),
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
            source_component=source.get("component"),
            source_host=source.get("host"),
        )


@dataclass(frozen=True)
class DeploymentProjection:
    """Minimal projection of a Kubernetes Deployment."""
    namespace: str
    name: str
    uid: str
    replicas: int = 0
    ready_replicas: int = 0
    available_replicas: int = 0
    unavailable_replicas: int = 0
    creation_timestamp: datetime | None = None
    labels: dict[str, str] = field(default_factory=dict)
    env_vars: dict[str, str] = field(default_factory=dict)
    image_pull_secrets: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeploymentProjection:
        """Create from a Kubernetes Deployment dict."""
        metadata = data.get("metadata") or {}
        spec = data.get("spec") or {}
        status = data.get("status") or {}

        ts = metadata.get("creationTimestamp")
        creation_ts: datetime | None = None
        if ts:
            try:
                creation_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Extract env vars from first container
        env_vars: dict[str, str] = {}
        containers = spec.get("template", {}).get("spec", {}).get("containers", [])
        if containers:
            for env_entry in containers[0].get("env") or []:
                name = env_entry.get("name")
                value = env_entry.get("value")
                if name and value is not None:
                    env_vars[str(name)] = str(value)

        # Extract image pull secrets from pod template
        pod_spec = spec.get("template", {}).get("spec", {})
        pull_secrets = [
            str(s.get("name") or "")
            for s in pod_spec.get("imagePullSecrets", [])
            if s.get("name")
        ]

        return cls(
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            uid=str(metadata.get("uid") or ""),
            replicas=int(spec.get("replicas") or 0),
            ready_replicas=int(status.get("readyReplicas") or 0),
            available_replicas=int(status.get("availableReplicas") or 0),
            unavailable_replicas=int(status.get("unavailableReplicas") or 0),
            creation_timestamp=creation_ts,
            labels=dict(metadata.get("labels") or {}),
            env_vars=env_vars,
            image_pull_secrets=tuple(pull_secrets),
        )


@dataclass(frozen=True)
class SecretProjection:
    """Minimal projection of a Kubernetes Secret."""
    namespace: str
    name: str
    uid: str
    secret_type: str
    creation_timestamp: datetime | None = None
    # Omit data/byte_content for memory safety - only expose metadata

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecretProjection:
        """Create from a Kubernetes Secret dict (metadata only, no data)."""
        metadata = data.get("metadata") or {}

        ts = metadata.get("creationTimestamp")
        creation_ts: datetime | None = None
        if ts:
            try:
                creation_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return cls(
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            uid=str(metadata.get("uid") or ""),
            secret_type=str(data.get("type") or ""),
            creation_timestamp=creation_ts,
        )


@dataclass(frozen=True)
class ServiceAccountProjection:
    """Minimal projection of a Kubernetes ServiceAccount."""
    namespace: str
    name: str
    uid: str
    creation_timestamp: datetime | None = None
    image_pull_secrets: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceAccountProjection:
        """Create from a Kubernetes ServiceAccount dict."""
        metadata = data.get("metadata") or {}

        ts = metadata.get("creationTimestamp")
        creation_ts: datetime | None = None
        if ts:
            try:
                creation_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        pull_secrets = [
            str(s.get("name") or "")
            for s in data.get("imagePullSecrets") or []
            if s.get("name")
        ]

        return cls(
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            uid=str(metadata.get("uid") or ""),
            creation_timestamp=creation_ts,
            image_pull_secrets=tuple(pull_secrets),
        )


@dataclass(frozen=True)
class PaginationMetadata:
    """Metadata about pagination results."""
    total: int | None = None
    remaining: int = 0
    truncated: bool = False
    continuation_token: str | None = None
    items_returned: int = 0


@dataclass(frozen=True)
class BoundedPodLogResult:
    """Result from bounded pod log collection."""
    logs: str
    truncated: bool
    truncation_reason: str | None = None
    bytes_read: int = 0
    bytes_limit: int = 0
    tail_lines: int | None = None
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class PodSummary:
    """Minimal summary projection for health-loop pod collection.

    This is a compact projection that contains only the fields needed
    for health assessment, excluding full pod manifests to prevent OOM.
    """
    namespace: str
    name: str
    phase: str | None
    reason: str | None  # e.g., "Evicted", "Error", "OOMKilled"
    node_name: str | None
    owner_kind: str | None
    owner_name: str | None
    restart_count: int
    waiting_reasons: tuple[str, ...]
    terminated_reasons: tuple[str, ...]
    created_at: datetime | None

    @classmethod
    def from_pod_dict(cls, data: dict[str, Any]) -> PodSummary:
        """Create from a Kubernetes Pod dict (extracted from API response).

        Args:
            data: Pod dictionary from kubernetes.client.V1Pod or JSON

        Returns:
            PodSummary with only diagnostically-relevant fields
        """
        metadata = data.get("metadata") or {}
        spec = data.get("spec") or {}
        status = data.get("status") or {}

        # Extract owner reference (workload parent)
        owner_kind: str | None = None
        owner_name: str | None = None
        owner_refs = metadata.get("ownerReferences") or []
        if owner_refs and isinstance(owner_refs, list) and len(owner_refs) > 0:
            owner_kind = str(owner_refs[0].get("kind") or "")
            owner_name = str(owner_refs[0].get("name") or "")

        # Extract container reasons
        waiting_reasons: list[str] = []
        terminated_reasons: list[str] = []
        container_statuses = status.get("containerStatuses") or []
        for container in container_statuses:
            for attr in ("state", "lastState"):
                state = container.get(attr) or {}
                waiting = state.get("waiting") or {}
                waiting_reason = str(waiting.get("reason") or "")
                if waiting_reason:
                    waiting_reasons.append(waiting_reason)
                terminated = state.get("terminated") or {}
                terminated_reason = str(terminated.get("reason") or "")
                if terminated_reason:
                    terminated_reasons.append(terminated_reason)

        # Parse creation timestamp
        ts = metadata.get("creationTimestamp")
        creation_ts: datetime | None = None
        if ts:
            try:
                creation_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return cls(
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            phase=str(status.get("phase") or "") or None,
            reason=str(status.get("reason") or "") or None,
            node_name=spec.get("nodeName"),
            owner_kind=owner_kind or None,
            owner_name=owner_name or None,
            restart_count=int(sum(
                cs.get("restartCount", 0)
                for cs in container_statuses
            )),
            waiting_reasons=tuple(waiting_reasons),
            terminated_reasons=tuple(terminated_reasons),
            created_at=creation_ts,
        )


@dataclass(frozen=True)
class StatefulSetSummary:
    """Minimal summary projection for statefulset collection.

    Contains only the fields needed for rollout status assessment.
    """
    namespace: str
    name: str
    replicas: int = 0
    ready_replicas: int = 0
    available_replicas: int = 0
    updated_replicas: int = 0
    current_replicas: int = 0
    observed_generation: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatefulSetSummary:
        """Create from a Kubernetes StatefulSet dict."""
        metadata = data.get("metadata") or {}
        spec = data.get("spec") or {}
        status = data.get("status") or {}

        return cls(
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            replicas=int(spec.get("replicas") or 0),
            ready_replicas=int(status.get("readyReplicas") or 0),
            available_replicas=int(status.get("availableReplicas") or 0),
            updated_replicas=int(status.get("updatedReplicas") or 0),
            current_replicas=int(status.get("currentReplicas") or 0),
            observed_generation=status.get("observedGeneration"),
        )


@dataclass(frozen=True)
class NodeSummary:
    """Minimal summary projection for node collection.

    Contains only the fields needed for health assessment.
    """
    name: str
    uid: str
    conditions: tuple[str, ...]  # e.g., "Ready=True", "MemoryPressure=False"
    kubelet_version: str | None
    internal_ip: str | None
    external_ip: str | None
    allocatable_cpu: str | None
    allocatable_memory: str | None
    capacity_cpu: str | None
    capacity_memory: str | None
    unschedulable: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeSummary:
        """Create from a Kubernetes Node dict."""
        metadata = data.get("metadata") or {}
        status = data.get("status") or {}
        spec = data.get("spec") or {}

        # Extract conditions
        conditions: list[str] = []
        for condition in status.get("conditions") or []:
            cond_type = str(condition.get("type") or "")
            cond_status = str(condition.get("status") or "")
            conditions.append(f"{cond_type}={cond_status}")

        # Extract addresses
        internal_ip: str | None = None
        external_ip: str | None = None
        for addr in status.get("addresses") or []:
            addr_type = str(addr.get("type") or "")
            addr_value = str(addr.get("address") or "")
            if addr_type == "InternalIP":
                internal_ip = addr_value
            elif addr_type == "ExternalIP":
                external_ip = addr_value

        # Extract node info
        node_info = status.get("nodeInfo") or {}
        kubelet_version = str(node_info.get("kubeletVersion") or "") or None

        # Extract allocatable
        allocatable = status.get("allocatable") or {}
        capacity = status.get("capacity") or {}

        return cls(
            name=str(metadata.get("name") or ""),
            uid=str(metadata.get("uid") or ""),
            conditions=tuple(conditions),
            kubelet_version=kubelet_version,
            internal_ip=internal_ip,
            external_ip=external_ip,
            allocatable_cpu=allocatable.get("cpu"),
            allocatable_memory=allocatable.get("memory"),
            capacity_cpu=capacity.get("cpu"),
            capacity_memory=capacity.get("memory"),
            unschedulable=bool(spec.get("unschedulable", False)),
        )


@dataclass(frozen=True)
class CrdSummary:
    """Minimal summary projection for CRD collection.

    Contains only the metadata needed for CRD inventory.
    """
    name: str
    group: str
    versions: tuple[str, ...]
    storage_version: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CrdSummary:
        """Create from a Kubernetes CRD dict."""
        metadata = data.get("metadata") or {}
        spec = data.get("spec") or {}

        # Extract API group
        group = str(spec.get("group") or "")

        # Extract versions
        versions: list[str] = []
        for v in spec.get("versions") or []:
            if isinstance(v, dict):
                versions.append(str(v.get("name") or ""))
            else:
                versions.append(str(v))
        versions.sort()

        # Extract storage version
        storage_version: str | None = None
        for v in spec.get("versions") or []:
            if isinstance(v, dict) and v.get("storage"):
                storage_version = str(v.get("name") or "")
                break

        return cls(
            name=str(metadata.get("name") or ""),
            group=group,
            versions=tuple(versions),
            storage_version=storage_version,
        )


__all__ = [
    "NamespaceProjection",
    "PodProjection",
    "ContainerStatusProjection",
    "EventProjection",
    "DeploymentProjection",
    "SecretProjection",
    "ServiceAccountProjection",
    "PaginationMetadata",
    "BoundedPodLogResult",
    "PodSummary",
    "StatefulSetSummary",
    "NodeSummary",
    "CrdSummary",
]
