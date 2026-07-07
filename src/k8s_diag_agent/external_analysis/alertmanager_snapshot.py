"""Normalized Alertmanager snapshot and compact summarizer for run artifacts.

This module is a thin compatibility facade that re-exports from split submodules.
Split in ACT-K9B-ALERTMANAGER-SNAPSHOT-SPLIT01 to reduce file sizes.

Submodules:
- alertmanager_snapshot_contract: Dataclasses, enums, constants
- alertmanager_snapshot_normalize: Payload parsing, normalization, compact conversion
- alertmanager_snapshot_evidence: Evidence preservation helpers
- alertmanager_snapshot_rendering: Formatting and display helpers
"""

from __future__ import annotations

# Re-export all public symbols from submodules for backward compatibility
from .alertmanager_snapshot_contract import (
    SENSITIVE_KEY_PATTERNS,
    AlertmanagerCompact,
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    ClusterAlertSummary,
    NormalizedAlert,
)

# Re-export evidence helpers
from .alertmanager_snapshot_evidence import (
    redact_sensitive_annotations,
)

# Re-export functions from normalize module
from .alertmanager_snapshot_normalize import (
    _compute_deterministic_fingerprint,
    _extract_receiver,
    _extract_state,
    _is_sensitive_key,
    _truncate_string,
    create_error_snapshot,
    normalize_alertmanager_payload,
    snapshot_to_compact,
)

# Re-export rendering helpers
from .alertmanager_snapshot_rendering import (
    format_compact_summary,
    format_snapshot_summary,
)

__all__ = [
    # Contract types
    "AlertmanagerStatus",
    "NormalizedAlert",
    "AlertmanagerSnapshot",
    "ClusterAlertSummary",
    "AlertmanagerCompact",
    "SENSITIVE_KEY_PATTERNS",
    # Normalize functions
    "normalize_alertmanager_payload",
    "snapshot_to_compact",
    "create_error_snapshot",
    "_truncate_string",
    "_compute_deterministic_fingerprint",
    "_extract_state",
    "_extract_receiver",
    "_is_sensitive_key",
    # Evidence helpers
    "redact_sensitive_annotations",
    # Rendering helpers
    "format_snapshot_summary",
    "format_compact_summary",
]
