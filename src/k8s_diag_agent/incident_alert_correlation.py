"""Alert incident correlation key builder for incident promotion.

This module builds deterministic correlation keys for alert-to-incident matching.

Rules:
- explicit k9b.dev/incident.key wins
- otherwise source_instance + class + namespace + entity_kind + entity_name
- never use Alertmanager groupKey alone
- never include dynamic metric values
- normalize case and empty values deterministically

Suggested by: ACT-K9B-ALERT-INCIDENT-PROMOTION01
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .incident_alert_classifier import AlertIncidentClassification
from .incident_alert_signal import AlertSignal

if TYPE_CHECKING:
    pass


def build_alert_incident_correlation_key(
    signal: AlertSignal,
    classification: AlertIncidentClassification,
) -> str:
    """Build a deterministic correlation key for alert-to-incident matching.

    Rules:
    - Explicit k9b.dev/incident.key wins
    - Otherwise: source_instance + class + namespace + entity_kind + entity_name
    - Never use Alertmanager groupKey alone
    - Never include dynamic metric values
    - Normalize case and empty values deterministically

    Example keys:
    - alertmanager-main:crash_loop:prod:pod:checkout-7d8f
    - alertmanager-main:deployment_unavailable:prod:deployment:checkout
    - alertmanager-main:target_unreachable:monitoring:service:prometheus

    Args:
        signal: The alert signal
        classification: The classification result

    Returns:
        Deterministic correlation key string
    """
    # Explicit incident key wins
    if classification.incident_key:
        return _normalize_key_component(classification.incident_key)

    # Build from components: source_instance + class + namespace + entity_kind + entity_name
    source = _normalize_key_component(classification.source_instance or "unknown")
    class_val = classification.class_.value
    namespace = _normalize_key_component(classification.namespace)
    entity_kind = classification.entity_kind.value
    entity_name = _normalize_key_component(classification.entity_name)

    # Format: source:class:namespace:entity_kind:entity_name
    return f"{source}:{class_val}:{namespace}:{entity_kind}:{entity_name}"


def _normalize_key_component(value: str) -> str:
    """Normalize a key component for deterministic output.

    - Lowercase
    - Replace non-alphanumeric with hyphens
    - Collapse multiple hyphens
    - Remove leading/trailing hyphens

    Args:
        value: Raw value to normalize

    Returns:
        Normalized component
    """
    import re

    if not value:
        return "unknown"

    # Lowercase
    normalized = value.lower()

    # Replace non-alphanumeric (except hyphens) with hyphens
    normalized = re.sub(r"[^a-z0-9-]", "-", normalized)

    # Collapse multiple hyphens
    normalized = re.sub(r"-+", "-", normalized)

    # Remove leading/trailing hyphens
    normalized = normalized.strip("-")

    # Handle empty after normalization
    if not normalized:
        return "unknown"

    return normalized


__all__ = [
    "build_alert_incident_correlation_key",
]
