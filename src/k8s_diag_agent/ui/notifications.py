"""Notification history helpers for the UI server."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..health.notifications import NotificationArtifact

DEFAULT_NOTIFICATION_LIMIT = 50


def query_notifications(
    root_dir: Path,
    *,
    kind: str | None = None,
    cluster_label: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    page: int | None = None,
) -> dict[str, Any]:
    """Return a newest-first slice of retained notifications with filtering."""

    notifications_dir = root_dir / "notifications"
    records = _load_notification_records(notifications_dir)
    kind_filter = _normalize_filter_value(kind)
    cluster_filter = _normalize_filter_value(cluster_label)
    search_term = (search or "").strip().lower()
    filtered = []
    for artifact, path in records:
        if kind_filter and artifact.kind.lower() != kind_filter:
            continue
        if cluster_filter and (artifact.cluster_label or "").lower() != cluster_filter:
            continue
        if search_term and not _matches_search(artifact, search_term):
            continue
        filtered.append((artifact, path))
    filtered.sort(key=_notification_sort_key, reverse=True)

    total = len(filtered)
    limit_value = limit if isinstance(limit, int) and limit > 0 else DEFAULT_NOTIFICATION_LIMIT
    page_value = page if isinstance(page, int) and page > 0 else 1
    offset = (page_value - 1) * limit_value
    sliced = filtered[offset : offset + limit_value]
    entries = [
        _build_notification_entry(root_dir, artifact, path)
        for artifact, path in sliced
    ]
    total_pages = max(1, math.ceil(total / limit_value)) if total else 1
    return {
        "notifications": entries,
        "total": total,
        "limit": limit_value,
        "page": page_value,
        "total_pages": total_pages,
    }


def _load_notification_records(directory: Path) -> list[tuple[NotificationArtifact, Path]]:
    entries: list[tuple[NotificationArtifact, Path]] = []
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("*.json")):
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        try:
            artifact = NotificationArtifact.from_dict(raw)
        except ValueError:
            continue
        entries.append((artifact, path))
    return entries


def _normalize_filter_value(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().lower()


def _matches_search(artifact: NotificationArtifact, term: str) -> bool:
    detail_values = " ".join(
        f"{label} {value}"
        for label, value in _detail_entries(artifact.details)
    )
    haystack = " ".join(
        filter(
            None,
            [
                artifact.summary,
                artifact.context,
                artifact.run_id,
                artifact.cluster_label,
                detail_values,
            ],
        )
    )
    return term in haystack.lower()


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
    if not isinstance(value, str):
        return None
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
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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
    entries: list[tuple[str, str]] = []
    if not isinstance(details, Mapping):
        return entries
    for key in sorted(details):
        value = details.get(key)
        entries.append((str(key), _stringify_value(value)))
    return entries


def _stringify_value(value: object | None) -> str:
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
    except Exception:
        return str(target)
