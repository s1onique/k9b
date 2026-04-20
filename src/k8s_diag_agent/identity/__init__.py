"""Identity primitives for durable canonical identities.

This module provides helpers for generating and deriving canonical identities across:
- Clusters (using kube-system namespace UID)
- Kubernetes objects (using native metadata.uid)
- Inferred entities (using deterministic hashing of defining facts)
- Artifacts (using UUIDv7)
"""

from __future__ import annotations

from .artifact import new_artifact_id
from .cluster import derive_cluster_uid
from .entity import build_deterministic_entity_id
from .k8s_object import build_k8s_object_ref

__all__ = [
    "new_artifact_id",
    "derive_cluster_uid",
    "build_deterministic_entity_id",
    "build_k8s_object_ref",
]
