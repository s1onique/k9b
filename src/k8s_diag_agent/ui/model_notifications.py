"""Notification view models and builders extracted from model.py.

This module contains notification-related UI model types extracted from model.py
to enable focused modularization while preserving behavior and import compatibility.

Symbols extracted:
- NotificationView: notification dataclass
- _build_notification_history: builder for notification history tuples
- _build_notification_details: builder for notification details tuples
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model_primitives import (
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class NotificationView:
    """View model for a single notification."""

    kind: str
    summary: str
    timestamp: str
    run_id: str | None
    cluster_label: str | None
    context: str | None
    details: tuple[tuple[str, str], ...]
    artifact_path: str | None
    artifact_id: str | None = None  # Immutable artifact identity (UUIDv7); None for legacy


def _build_notification_history(raw: object | None) -> tuple[NotificationView, ...]:
    """Build a tuple of NotificationView from raw notification history data.

    Args:
        raw: Raw notification history data (list/dict or None)

    Returns:
        Tuple of NotificationView objects. Empty tuple if input is not a Sequence.
    """
    if not isinstance(raw, Sequence):
        return ()
    entries: list[NotificationView] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        entries.append(
            NotificationView(
                kind=_coerce_str(entry.get("kind")),
                summary=_coerce_str(entry.get("summary")),
                timestamp=_coerce_str(entry.get("timestamp")),
                run_id=_coerce_optional_str(entry.get("run_id")),
                cluster_label=_coerce_optional_str(entry.get("cluster_label")),
                context=_coerce_optional_str(entry.get("context")),
                details=_build_notification_details(entry.get("details")),
                artifact_path=_coerce_optional_str(entry.get("artifact_path")),
                artifact_id=_coerce_optional_str(entry.get("artifact_id")),
            )
        )
    return tuple(entries)


def _build_notification_details(raw: object | None) -> tuple[tuple[str, str], ...]:
    """Build a tuple of (label, value) string tuples from raw notification details.

    Args:
        raw: Raw details data (list/dict or None)

    Returns:
        Tuple of (label, value) tuples. Empty tuple if input is not a Sequence.
    """
    if not isinstance(raw, Sequence):
        return ()
    details: list[tuple[str, str]] = []
    for detail in raw:
        if not isinstance(detail, Mapping):
            continue
        label = _coerce_str(detail.get("label"))
        value = _coerce_str(detail.get("value"))
        details.append((label, value))
    return tuple(details)
