"""Evidence preservation logic for Alertmanager snapshots.

This module contains:
- Evidence-preservation logic
- Raw-field retention
- Compact artifact shaping

Note: Most evidence preservation logic is integrated into alertmanager_snapshot_normalize.py
for atomicity. This module provides supplementary helpers if needed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .alertmanager_snapshot_contract import SENSITIVE_KEY_PATTERNS


def _is_sensitive_key_standalone(key: str) -> bool:
    """Check if an annotation key is sensitive and should be redacted.
    
    This is a standalone version for cases where the full normalize module
    is not available. Uses SENSITIVE_KEY_PATTERNS from contract module.
    """
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in SENSITIVE_KEY_PATTERNS)


def redact_sensitive_annotations(
    annotations: Mapping[str, Any],
    max_length: int = 200,
) -> tuple[tuple[str, str], ...]:
    """Redact sensitive keys from annotations mapping.
    
    Returns sorted tuple of (key, value) pairs with sensitive values redacted.
    """
    result: list[tuple[str, str]] = []
    for k, v in sorted(annotations.items()):
        k_str = str(k)
        v_str = str(v)
        if not k_str:
            continue
        if _is_sensitive_key_standalone(k_str):
            v_str = "[REDACTED]"
        if len(v_str) > max_length:
            v_str = v_str[:max_length - 3] + "..."
        result.append((k_str, v_str))
    return tuple(result)
