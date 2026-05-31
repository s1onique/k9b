"""Notification payload building and timestamp utilities."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..datetime_utils import parse_iso_to_utc
from ..health.notifications import NotificationArtifact

__all__ = [
    "_build_notification_entry",
    "_notification_sort_key",
    "_parse_timestamp",
    "_relative_path",
]


def _notification_sort_key(record: tuple[NotificationArtifact, Path]) -> datetime:
    artifact, path = record
    timestamp = _parse_timestamp(artifact.timestamp)
    if timestamp:
        return timestamp
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except OSError:
        return datetime(1970, 1, 1, tzinfo=UTC)


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO timestamp string to timezone-aware UTC datetime.

    Uses centralized datetime_utils to ensure all parsed datetimes
    are timezone-aware UTC for safe comparison operations.
    """
    if not isinstance(value, str):
        return None
    # Try strptime formats first (these are legacy formats)
    for fmt in (
        "%Y%m%dT%H%M%S",
        "%Y%m%dT%H%M%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    # Use centralized parser for ISO format
    return parse_iso_to_utc(value)


def _build_notification_entry(
    root_dir: Path, artifact: NotificationArtifact, path: Path
) -> dict[str, Any]:
    details = _detail_entries(artifact.details)
    relative_path = _relative_path(root_dir, path)
    return {
        "kind": artifact.kind,
        "summary": artifact.summary,
        "timestamp": artifact.timestamp,
        "runId": artifact.run_id,
        "clusterLabel": artifact.cluster_label,
        "context": artifact.context,
        "details": [{"label": label, "value": value} for label, value in details],
        "artifactPath": relative_path,
    }


def _detail_entries(details: Mapping[str, object] | None) -> list[tuple[str, str]]:
    """Extract sorted label-value pairs from notification details."""
    entries: list[tuple[str, str]] = []
    if not isinstance(details, Mapping):
        return entries
    for key in sorted(details):
        value = details.get(key)
        entries.append((str(key), _stringify_value(value)))
    return entries


def _stringify_value(value: object | None) -> str:
    """Convert a detail value to a display string."""
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _relative_path(base: Path, target: Path) -> str | None:
    try:
        return str(target.relative_to(base))
    except (ValueError, OSError):
        return str(target)
