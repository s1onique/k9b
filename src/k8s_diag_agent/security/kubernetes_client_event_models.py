"""Event-related projection models for Kubernetes API responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class EventProjection:
    """Minimal projection of a Kubernetes Event."""
    namespace: str
    name: str
    event_type: str | None
    reason: str
    message: str
    involved_object_kind: str
    involved_object_name: str
    creation_timestamp: datetime | None = None
    count: int = 1
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    source_component: str | None = None
    source_host: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventProjection:
        """Create from a Kubernetes Event dict."""
        metadata = data.get("metadata") or {}
        involved = data.get("involvedObject") or {}
        source = data.get("source") or {}

        ts = metadata.get("creationTimestamp")
        creation_ts: datetime | None = None
        if ts:
            try:
                creation_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        first_ts = data.get("firstTimestamp")
        first_timestamp: datetime | None = None
        if first_ts:
            try:
                first_timestamp = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        last_ts = data.get("lastTimestamp")
        last_timestamp: datetime | None = None
        if last_ts:
            try:
                last_timestamp = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return cls(
            namespace=str(metadata.get("namespace") or ""),
            name=str(metadata.get("name") or ""),
            event_type=data.get("type"),
            reason=str(data.get("reason") or ""),
            message=str(data.get("message") or ""),
            involved_object_kind=str(involved.get("kind") or ""),
            involved_object_name=str(involved.get("name") or ""),
            creation_timestamp=creation_ts,
            count=int(data.get("count") or 1),
            first_timestamp=first_timestamp,
            last_timestamp=last_timestamp,
            source_component=source.get("component"),
            source_host=source.get("host"),
        )


__all__ = [
    "EventProjection",
]
