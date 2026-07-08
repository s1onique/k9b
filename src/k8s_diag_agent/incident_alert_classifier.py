"""Deterministic alert classifier for incident promotion.

This module provides a pure classifier that maps AlertSignal to incident classification.
Classification is deterministic - same signal always produces same classification.

Classification precedence:
1. Explicit k9b.dev/* labels
2. Known alertname mappings
3. Stable entity labels
4. external_alert fallback

Suggested by: ACT-K9B-ALERT-INCIDENT-PROMOTION01
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .incident_alert_signal import AlertSignal

if TYPE_CHECKING:
    pass


# =============================================================================
# Alert Incident Classification Model
# =============================================================================


class AlertIncidentClass(StrEnum):
    """Classification of alert for incident purposes.

    These map to existing CandidateClass values where applicable.
    """
    # Kubernetes pod issues
    CRASH_LOOP = "crash_loop"
    IMAGE_PULL_ERROR = "image_pull_error"
    PENDING_POD = "pending_pod"

    # Kubernetes workload issues
    DEPLOYMENT_UNAVAILABLE = "deployment_unavailable"
    NODE_UNAVAILABLE = "node_unavailable"
    TARGET_UNREACHABLE = "target_unreachable"

    # Generic external alerts
    EXTERNAL_ALERT = "external_alert"


class EntityKind(StrEnum):
    """Kind of entity associated with the alert."""
    POD = "pod"
    DEPLOYMENT = "deployment"
    STATEFULSET = "statefulset"
    DAEMONSET = "daemonset"
    JOB = "job"
    NODE = "node"
    SERVICE = "service"
    CONTAINER = "container"
    INSTANCE = "instance"
    ALERT = "alert"  # Fallback


@dataclass(frozen=True)
class AlertIncidentClassification:
    """Classification result for an alert signal."""

    # Classification
    class_: AlertIncidentClass
    entity_kind: EntityKind

    # Entity identification
    entity_name: str
    namespace: str

    # Optional explicit incident key override
    incident_key: str | None = None

    # Source information
    source_instance: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dict for serialization."""
        return {
            "class": self.class_.value,
            "entity_kind": self.entity_kind.value,
            "entity_name": self.entity_name,
            "namespace": self.namespace,
            "incident_key": self.incident_key,
            "source_instance": self.source_instance,
        }


# =============================================================================
# Classification Mappings
# =============================================================================

# Known alertname to classification mappings
_KNOWN_ALERTNAME_MAPPINGS: dict[str, AlertIncidentClass] = {
    "KubePodCrashLooping": AlertIncidentClass.CRASH_LOOP,
    "KubeDeploymentReplicasMismatch": AlertIncidentClass.DEPLOYMENT_UNAVAILABLE,
    "KubePodNotReady": AlertIncidentClass.PENDING_POD,
    "KubePodImagePullBackOff": AlertIncidentClass.IMAGE_PULL_ERROR,
    "KubeNodeNotReady": AlertIncidentClass.NODE_UNAVAILABLE,
    "TargetDown": AlertIncidentClass.TARGET_UNREACHABLE,
    "EndpointDown": AlertIncidentClass.TARGET_UNREACHABLE,
}

# Stable entity label keys (in priority order for extraction)
_ENTITY_LABEL_KEYS: tuple[str, ...] = (
    "pod",
    "deployment",
    "statefulset",
    "daemonset",
    "job",
    "node",
    "service",
    "container",
    "instance",
)

# k9b.dev label prefixes
_K9B_LABEL_PREFIX = "k9b.dev/"


# =============================================================================
# Classifier Function
# =============================================================================


def classify_alert_signal(signal: AlertSignal) -> AlertIncidentClassification:
    """Classify an alert signal for incident promotion.

    Classification is deterministic - same signal always produces same result.

    Classification precedence:
    1. Explicit k9b.dev/class label
    2. Explicit k9b.dev/incident.key label
    3. Explicit k9b.dev/entity.kind label
    4. Known alertname mappings
    5. Stable entity labels
    6. external_alert fallback

    Args:
        signal: The alert signal to classify

    Returns:
        AlertIncidentClassification with classification result
    """
    labels = dict(signal.labels)

    # 1. Check for explicit k9b.dev/class
    explicit_class = labels.get(f"{_K9B_LABEL_PREFIX}class")
    if explicit_class:
        try:
            class_ = AlertIncidentClass(explicit_class)
        except ValueError:
            class_ = AlertIncidentClass.EXTERNAL_ALERT
    else:
        # 2. Check known alertname mappings
        class_ = _KNOWN_ALERTNAME_MAPPINGS.get(signal.alertname) or AlertIncidentClass.EXTERNAL_ALERT

    # 1b. Check for explicit k9b.dev/incident.key
    explicit_incident_key = labels.get(f"{_K9B_LABEL_PREFIX}incident.key")

    # 3. Check for explicit k9b.dev/entity.kind
    explicit_entity_kind_str = labels.get(f"{_K9B_LABEL_PREFIX}entity.kind")
    if explicit_entity_kind_str:
        try:
            entity_kind = EntityKind(explicit_entity_kind_str)
        except ValueError:
            entity_kind = _infer_entity_kind(signal)
    else:
        entity_kind = _infer_entity_kind(signal)

    # Extract entity name from explicit labels or inference
    explicit_entity_name = labels.get(f"{_K9B_LABEL_PREFIX}entity.name")
    if explicit_entity_name:
        entity_name = explicit_entity_name
    else:
        entity_name = _infer_entity_name(signal, entity_kind)

    # Extract namespace from explicit labels or labels
    explicit_namespace = labels.get(f"{_K9B_LABEL_PREFIX}entity.namespace")
    if explicit_namespace:
        namespace = explicit_namespace
    else:
        namespace = labels.get("namespace", "unknown")

    return AlertIncidentClassification(
        class_=class_,
        entity_kind=entity_kind,
        entity_name=entity_name,
        namespace=namespace,
        incident_key=explicit_incident_key,
        source_instance=signal.source_instance,
    )


def _infer_entity_kind(signal: AlertSignal) -> EntityKind:
    """Infer entity kind from stable labels.

    Args:
        signal: The alert signal

    Returns:
        Inferred EntityKind
    """
    labels = dict(signal.labels)

    for label_key in _ENTITY_LABEL_KEYS:
        if label_key in labels:
            try:
                return EntityKind(label_key)
            except ValueError:
                pass

    # Fallback
    return EntityKind.ALERT


def _infer_entity_name(signal: AlertSignal, entity_kind: EntityKind) -> str:
    """Infer entity name from signal labels.

    Args:
        signal: The alert signal
        entity_kind: The inferred entity kind

    Returns:
        Entity name or alertname as fallback
    """
    labels = dict(signal.labels)

    # Try to get name from the entity kind label
    kind_str = entity_kind.value
    if kind_str in labels:
        return labels[kind_str]

    # Fallback to alertname
    return signal.alertname


__all__ = [
    "AlertIncidentClass",
    "AlertIncidentClassification",
    "EntityKind",
    "classify_alert_signal",
]
