"""Normalized alert signal domain model for Alertmanager and vmalert ingestion.

This module provides the internal contract for representing alert signals
as distinct from incidents. Alerts are signals that may open, update,
correlate with, or enrich an incident.

Design principles:
- Alerts are not incidents: they are signals that may influence incidents
- Stable internal representation independent of provider payload shapes
- Bounded fields to prevent unbounded artifact growth
- Pure domain model: no I/O, no external calls

Non-goals for this module:
- Alert-to-incident promotion (handled by future ACT)
- Webhook endpoint implementation (handled by future ACT)
- LLM-based classification
"""

from __future__ import annotations

# Re-export all public symbols from split modules for backward compatibility
from .incident_alert_signal_contract import (
    MAX_ANNOTATION_COUNT,
    MAX_KEY_LENGTH,
    MAX_LABEL_COUNT,
    MAX_TOTAL_ANNOTATION_BYTES,
    MAX_TOTAL_LABEL_BYTES,
    MAX_VALUE_LENGTH,
    AlertCorrelationHints,
    AlertSignal,
    AlertSourceType,
    AlertStatus,
    TruncationMetadata,
)
from .incident_alert_signal_helpers import (
    bound_annotations,
    bound_labels,
)

__all__ = [
    # Bounds constants
    "MAX_LABEL_COUNT",
    "MAX_ANNOTATION_COUNT",
    "MAX_KEY_LENGTH",
    "MAX_VALUE_LENGTH",
    "MAX_TOTAL_LABEL_BYTES",
    "MAX_TOTAL_ANNOTATION_BYTES",
    # Enums
    "AlertSourceType",
    "AlertStatus",
    # Models
    "AlertSignal",
    "AlertCorrelationHints",
    "TruncationMetadata",
    # Utilities
    "bound_labels",
    "bound_annotations",
]
