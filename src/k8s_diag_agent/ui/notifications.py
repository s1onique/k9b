"""Notification history helpers for the UI server."""

from __future__ import annotations

import json
import math
import time as time_module
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..health.notifications import NotificationArtifact
from ..structured_logging import emit_structured_log

DEFAULT_NOTIFICATION_LIMIT = 50

# Logging component identifier
_COMPONENT = "ui-notifications"


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
    total_start = time_module.perf_counter()
    
    # Counters for observability
    counters: dict[str, int] = {
        "notification_files_considered": 0,
        "notification_files_rejected_by_metadata": 0,
        "notification_files_fully_parsed": 0,
        "notification_records_matched": 0,
        "notification_records_returned": 0,
    }

    notifications_dir = root_dir / "notifications"
    
    # Pre-normalize filters
    kind_filter = _normalize_filter_value(kind)
    cluster_filter = _normalize_filter_value(cluster_label)
    search_term = (search or "").strip().lower()
    
    # Compute limit and page
    limit_value = limit if isinstance(limit, int) and limit > 0 else DEFAULT_NOTIFICATION_LIMIT
    page_value = page if isinstance(page, int) and page > 0 else 1
    offset = (page_value - 1) * limit_value
    
    # Timing: load phase - optimized with filtering during load
    load_start = time_module.perf_counter()
    records = _load_notification_records_optimized(
        notifications_dir,
        kind_filter=kind_filter,
        cluster_filter=cluster_filter,
        search_term=search_term,
        counters=counters,
    )
    load_duration_ms = (time_module.perf_counter() - load_start) * 1000
    
    # Timing: filter phase (now lightweight - records already filtered during load)
    filter_start = time_module.perf_counter()
    # Records already filtered during load - just count them
    filtered = records
    filter_duration_ms = (time_module.perf_counter() - filter_start) * 1000
    counters["notification_records_matched"] = len(filtered)
    
    # Timing: sort phase - skip if already sorted by filename (newest first)
    sort_start = time_module.perf_counter()
    # Files are already processed in reverse chronological order (newest first)
    # Only need to sort if we have search term or complex filters that might have
    # disrupted order
    needs_sort = bool(search_term or cluster_filter)
    if needs_sort:
        filtered.sort(key=_notification_sort_key, reverse=True)
    sort_duration_ms = (time_module.perf_counter() - sort_start) * 1000
    counters["sort_applied"] = 1 if needs_sort else 0
    
    # Timing: pagination phase
    paginate_start = time_module.perf_counter()
    total = len(filtered)
    sliced = filtered[offset : offset + limit_value]
    
    # Timing: payload build phase
    payload_build_start = time_module.perf_counter()
    entries = [
        _build_notification_entry(root_dir, artifact, path)
        for artifact, path in sliced
    ]
    payload_build_duration_ms = (time_module.perf_counter() - payload_build_start) * 1000
    counters["notification_records_returned"] = len(entries)
    paginate_duration_ms = (time_module.perf_counter() - paginate_start) * 1000
    
    total_pages = max(1, math.ceil(total / limit_value)) if total else 1
    total_duration_ms = (time_module.perf_counter() - total_start) * 1000
    
    result = {
        "notifications": entries,
        "total": total,
        "limit": limit_value,
        "page": page_value,
        "total_pages": total_pages,
    }
    
    # Emit structured log with timing breakdown
    emit_structured_log(
        component=_COMPONENT,
        message="/api/notifications query completed with timing",
        run_id="",
        run_label="",
        severity="DEBUG",
        metadata={
            "path": "/api/notifications",
            "total_duration_ms": round(total_duration_ms, 2),
            "load_duration_ms": round(load_duration_ms, 2),
            "filter_duration_ms": round(filter_duration_ms, 2),
            "sort_duration_ms": round(sort_duration_ms, 2),
            "paginate_duration_ms": round(paginate_duration_ms, 2),
            "payload_build_duration_ms": round(payload_build_duration_ms, 2),
            # Counters
            "notification_files_considered": counters["notification_files_considered"],
            "notification_files_rejected_by_metadata": counters["notification_files_rejected_by_metadata"],
            "notification_files_fully_parsed": counters["notification_files_fully_parsed"],
            "notification_records_matched": counters["notification_records_matched"],
            "notification_records_returned": counters["notification_records_returned"],
            # Additional telemetry
            "sort_applied": counters.get("sort_applied", 0),
            "early_termination": counters.get("early_termination", 0),
            # Query params for correlation
            "kind_filter": kind_filter,
            "cluster_filter": cluster_filter,
            "search_term": search_term[:50] if search_term else "",
            "limit": limit_value,
            "page": page_value,
        },
    )
    
    return result


def _load_notification_records(
    directory: Path,
    *,
    kind_filter: str | None = None,
    cluster_filter: str | None = None,
    counters: dict[str, int] | None = None,
) -> list[tuple[NotificationArtifact, Path]]:
    """Load notification records with optional metadata-pass optimization.
    
    This function implements a two-phase load:
    1. Metadata pass: extract kind from filename to avoid full JSON parse when possible
    2. Full parse: only parse JSON when metadata filtering passes or no filter applies
    
    Args:
        directory: Path to the notifications directory
        kind_filter: Optional kind to filter by (e.g., "warning", "info")
        cluster_filter: Optional cluster_label to filter by (requires full parse)
        counters: Optional dict to track observability metrics
        
    Returns:
        List of (NotificationArtifact, Path) tuples
    """
    entries: list[tuple[NotificationArtifact, Path]] = []
    if not directory.is_dir():
        return entries
    
    # Normalize filters for comparison
    normalized_kind_filter = _normalize_filter_value(kind_filter) if kind_filter else ""
    normalized_cluster_filter = _normalize_filter_value(cluster_filter) if cluster_filter else ""
    
    # Determine if we can skip files based on kind filter alone
    # (cluster_filter requires full JSON parse since it's in the content)
    use_metadata_filter = bool(normalized_kind_filter and not normalized_cluster_filter)
    
    for path in sorted(directory.glob("*.json")):
        if not path.is_file():
            continue
        
        # Increment files considered counter
        if counters is not None:
            counters["notification_files_considered"] += 1
        
        # Metadata pass: try to extract kind from filename
        # Filename format: {timestamp}-{kind}.json
        filename = path.stem  # filename without extension
        if "-" in filename:
            # Split on first dash to get timestamp, rest is kind
            # Format is {timestamp}-{kind} where timestamp is like 20260407T120000
            parts = filename.split("-", 1)
            if len(parts) == 2:
                filename_kind = parts[1].lower()
                
                # If we have a kind filter and filename kind doesn't match, skip full parse
                if use_metadata_filter and filename_kind != normalized_kind_filter:
                    if counters is not None:
                        counters["notification_files_rejected_by_metadata"] += 1
                    continue
        
        # Either no metadata filter, or metadata filter passed - do full parse
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        
        # Update parse counter
        if counters is not None:
            counters["notification_files_fully_parsed"] += 1
        
        try:
            artifact = NotificationArtifact.from_dict(raw)
        except ValueError:
            continue
        
        # Apply cluster filter if needed (requires full parse since it's in content)
        if normalized_cluster_filter:
            artifact_cluster = _normalize_filter_value(artifact.cluster_label)
            if artifact_cluster != normalized_cluster_filter:
                continue
        
        entries.append((artifact, path))
    
    return entries


def _load_notification_records_optimized(
    directory: Path,
    *,
    kind_filter: str = "",
    cluster_filter: str = "",
    search_term: str = "",
    counters: dict[str, int] | None = None,
) -> list[tuple[NotificationArtifact, Path]]:
    """Optimized notification loading with filtering during load.
    
    Key optimizations:
    1. Filter during load - apply filters as we parse, not after (eliminates post-load filtering)
    2. Skip sorting when possible - files are already in reverse chronological order
    3. Metadata-first rejection - skip full parse when kind filter can be determined from filename
    
    Note: Early termination was removed to preserve total count accuracy.
    
    Args:
        directory: Path to the notifications directory
        kind_filter: Normalized kind filter (empty = no filter)
        cluster_filter: Normalized cluster filter (empty = no filter)
        search_term: Normalized search term (empty = no filter)
        counters: Optional dict to track observability metrics
        
    Returns:
        List of (NotificationArtifact, Path) tuples in reverse chronological order
    """
    entries: list[tuple[NotificationArtifact, Path]] = []
    if not directory.is_dir():
        return entries
    
    # Can skip full parse based on metadata alone if only kind filter (no cluster, no search)
    # This is an optimization to avoid parsing files that won't match
    use_filename_kind_filter = bool(kind_filter and not cluster_filter and not search_term)
    
    # Use reversed sorted glob to get newest first
    # This avoids needing to sort later for the common case
    all_files = sorted(directory.glob("*.json"), reverse=True)
    
    for path in all_files:
        if not path.is_file():
            continue
        
        # Increment files considered counter
        if counters is not None:
            counters["notification_files_considered"] += 1
        
        filename = path.stem
        filename_kind = ""
        
        # Try to extract kind from filename for metadata-based filtering
        # Filename format: {timestamp}-{kind}.json (e.g., 20260406T130007-degraded-health.json)
        if "-" in filename:
            parts = filename.split("-", 1)
            if len(parts) == 2:
                filename_kind = parts[1].lower()
                
                # If we can use metadata filter and filename kind doesn't match, skip full parse
                # This is safe because kind is in the filename
                if use_filename_kind_filter and filename_kind != kind_filter:
                    if counters is not None:
                        counters["notification_files_rejected_by_metadata"] += 1
                    continue
        
        # Full parse required - either no metadata filter, or metadata passed
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        
        # Update parse counter
        if counters is not None:
            counters["notification_files_fully_parsed"] += 1
        
        try:
            artifact = NotificationArtifact.from_dict(raw)
        except ValueError:
            continue
        
        # Apply filters during load (not after) - this ensures correctness for all filter combinations
        
        # Kind filter - always apply (even if metadata filter was skipped due to cluster/search)
        if kind_filter:
            artifact_kind = artifact.kind.lower()
            if artifact_kind != kind_filter:
                continue
        
        # Cluster filter (requires content)
        if cluster_filter:
            artifact_cluster = _normalize_filter_value(artifact.cluster_label)
            if artifact_cluster != cluster_filter:
                continue
        
        # Search term (requires content)
        if search_term and not _matches_search(artifact, search_term):
            continue
        
        # All filters passed - add to results
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
