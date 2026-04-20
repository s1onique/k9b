"""Identity primitives for durable canonical identities.

This module provides helpers for generating and deriving canonical identities across:
- Clusters (using kube-system namespace UID)
- Kubernetes objects (using native metadata.uid)
- Inferred entities (using deterministic hashing of defining facts)
- Artifacts (using UUIDv7)
- Alertmanager sources (canonical entity IDs and operator-intent keys)
"""

from __future__ import annotations

from .alertmanager_source import (
    build_alertmanager_canonical_entity_id,
    build_alertmanager_canonical_human_id,
    build_alertmanager_operator_intent_key,
    extract_alertmanager_source_facts,
    get_canonical_identity_summary,
)
from .artifact import new_artifact_id
from .cluster import derive_cluster_uid
from .entity import build_deterministic_entity_id
from .k8s_object import build_k8s_object_ref

__all__ = [
    "new_artifact_id",
    "derive_cluster_uid",
    "build_deterministic_entity_id",
    "build_k8s_object_ref",
    # Alertmanager source identity helpers
    "extract_alertmanager_source_facts",
    "build_alertmanager_canonical_entity_id",
    "build_alertmanager_canonical_human_id",
    "build_alertmanager_operator_intent_key",
    "get_canonical_identity_summary",
]
