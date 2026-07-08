"""Workload-related projection models for Kubernetes API responses.

These models cover Deployments, StatefulSets, Namespaces, Secrets, and ServiceAccounts.
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


__all__ = [
    "DeploymentProjection",
    "NamespaceProjection",
    "SecretProjection",
    "ServiceAccountProjection",
    "StatefulSetSummary",
]
