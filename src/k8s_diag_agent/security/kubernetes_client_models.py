"""Typed projection models for Kubernetes API responses.

This module is a compatibility facade that re-exports models from focused submodules.
The actual implementations live in:
- kubernetes_client_pod_models.py: Pod, ContainerStatus, PodSummary
- kubernetes_client_event_models.py: EventProjection
- kubernetes_client_workload_models.py: Deployment, Namespace, Secret, ServiceAccount, StatefulSet
- kubernetes_client_crd_models.py: CrdSummary, NodeSummary
- kubernetes_client_pagination_models.py: PaginationMetadata, BoundedPodLogResult

These models are small projections of Kubernetes objects, used to prevent
raw Kubernetes object graph leakage into downstream artifacts.
"""

from __future__ import annotations

# Re-export all models from submodules for backward compatibility
from .kubernetes_client_crd_models import CrdSummary, NodeSummary
from .kubernetes_client_event_models import EventProjection
from .kubernetes_client_pagination_models import BoundedPodLogResult, PaginationMetadata
from .kubernetes_client_pod_models import (
    ContainerStatusProjection,
    PodProjection,
    PodSummary,
)
from .kubernetes_client_workload_models import (
    DeploymentProjection,
    NamespaceProjection,
    SecretProjection,
    ServiceAccountProjection,
    StatefulSetSummary,
)

__all__ = [
    # Pod models
    "ContainerStatusProjection",
    "PodProjection",
    "PodSummary",
    # Event models
    "EventProjection",
    # Workload models
    "DeploymentProjection",
    "NamespaceProjection",
    "SecretProjection",
    "ServiceAccountProjection",
    "StatefulSetSummary",
    # CRD/Node models
    "CrdSummary",
    "NodeSummary",
    # Pagination models
    "PaginationMetadata",
    "BoundedPodLogResult",
]
