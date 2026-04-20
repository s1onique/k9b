"""Kubernetes object reference with canonical identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class K8sObjectRef:
    """Canonical reference to a Kubernetes object.

    This combines the object's name/namespace/kind with its native UID
    to provide a durable identity anchor that survives renames and recreations.

    Attributes:
        namespace: Kubernetes namespace (None for cluster-scoped objects).
        kind: Resource kind (e.g., "Deployment", "Pod").
        name: Resource name.
        object_uid: Native Kubernetes metadata.uid (if available).
    """

    namespace: str | None
    kind: str
    name: str
    object_uid: str | None = None

    @property
    def api_version(self) -> str:
        """Return a string representation for API reference."""
        ns_prefix = f"{self.namespace}/" if self.namespace else ""
        return f"{ns_prefix}{self.kind}/{self.name}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON persistence."""
        return {
            "namespace": self.namespace,
            "kind": self.kind,
            "name": self.name,
            "object_uid": self.object_uid,
        }


def build_k8s_object_ref(
    namespace: str | None,
    kind: str,
    name: str,
    object_uid: str | None = None,
) -> K8sObjectRef:
    """Build a canonical reference to a Kubernetes object.

    Args:
        namespace: Kubernetes namespace (None for cluster-scoped).
        kind: Resource kind (e.g., "Deployment", "Pod", "Service").
        name: Resource name.
        object_uid: Native Kubernetes metadata.uid (optional, from API response).

    Returns:
        A K8sObjectRef with canonical identity.

    Invariants:
        - Same object recreated → different object_uid
        - Renamed object → different object_uid (if UIDs are tracked)
    """
    return K8sObjectRef(
        namespace=namespace,
        kind=kind,
        name=name,
        object_uid=object_uid,
    )


def parse_k8s_object_ref(data: dict[str, Any]) -> K8sObjectRef | None:
    """Parse a K8sObjectRef from serialized dict data.

    Args:
        data: Dict that may contain K8s object reference fields.

    Returns:
        K8sObjectRef if required fields are present, None otherwise.
    """
    kind = data.get("kind")
    name = data.get("name")

    if not kind or not name:
        return None

    return build_k8s_object_ref(
        namespace=data.get("namespace"),
        kind=str(kind),
        name=str(name),
        object_uid=data.get("object_uid"),
    )
