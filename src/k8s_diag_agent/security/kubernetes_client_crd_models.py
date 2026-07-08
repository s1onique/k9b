"""CRD and Node projection models for Kubernetes API responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NodeSummary:
    """Minimal summary projection for node collection.

    Contains only the fields needed for health assessment.
    """
    name: str
    uid: str
    conditions: tuple[str, ...]  # e.g. "Ready=True", "MemoryPressure=False"
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
    "CrdSummary",
    "NodeSummary",
]
