"""TypedDict payload definitions for notification contracts.

This module contains pure data contracts (TypedDict definitions) for notification
list and entry responses.

Ownership:
    - All TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.
    - Serialization logic lives in api.py and related modules.

Extraction rationale:
    - Notification contracts are self-contained with minimal dependencies.
    - Extracting them establishes the notification contract boundary.
    - Keeping notification contracts in a dedicated module makes it easier to
      audit notification API contracts without filtering through unrelated payloads.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "NotificationDetail",
    "NotificationEntry",
    "NotificationsPayload",
]


class NotificationDetail(TypedDict):
    """A key-value detail pair in a notification."""

    label: str
    value: str


class NotificationEntry(TypedDict):
    """Payload for a single notification entry."""

    kind: str
    summary: str
    timestamp: str
    runId: str | None
    clusterLabel: str | None
    context: str | None
    details: list[NotificationDetail]
    artifactPath: str | None
    # Immutable artifact identity (UUIDv7); None for legacy artifacts
    artifactId: str | None


class NotificationsPayload(TypedDict):
    """Payload for the notifications list response."""

    notifications: list[NotificationEntry]
