"""Branded pagination primitives for incident diagnosis.

This module defines the core branded types used at pagination boundaries:
- OpaqueCursorToken: Serialized cursor token
- FirstObservedAtKey: Exact database ordering key (timestamp text)
- DiagnosisIncidentId: Unique incident identifier
- CursorResetReasonCode: Coded reset reason
- BackendProtocolErrorCode: Coded backend error

These types make invalid pagination states unrepresentable by giving
semantically different strings distinct static types.
"""

from __future__ import annotations

from typing import NewType

# =============================================================================
# Branded Primitive Types
# =============================================================================


OpaqueCursorToken = NewType("OpaqueCursorToken", str)
"""Serialized cursor token from encode_cursor().

This is the only type that should be stored in persistence or transmitted
over the wire. Never construct directly from arbitrary strings.
"""

FirstObservedAtKey = NewType("FirstObservedAtKey", str)
"""EXACT database ordering key for timestamp.

This is the verbatim text stored in SQLite, used to construct cursors
and compare ordering keys. Must NOT be reconstructed from datetime.
"""

DiagnosisIncidentId = NewType("DiagnosisIncidentId", str)
"""Unique incident identifier at pagination boundaries."""

CursorResetReasonCode = NewType("CursorResetReasonCode", str)
"""Coded reason for cursor reset (e.g., 'legacy_format')."""

BackendProtocolErrorCode = NewType("BackendProtocolErrorCode", str)
"""Coded error from backend protocol violations."""


__all__ = [
    "OpaqueCursorToken",
    "FirstObservedAtKey",
    "DiagnosisIncidentId",
    "CursorResetReasonCode",
    "BackendProtocolErrorCode",
]
