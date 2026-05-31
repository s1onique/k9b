"""Notification record loading and filtering helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ..health.artifact_readers import try_read_notification_artifact
from ..health.notifications import NotificationArtifact

__all__ = [
    "_count_matching_records",
    "_load_notification_records",
    "_load_notification_records_optimized",
    "_matches_search",
    "_normalize_filter_value",
]


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
    import json

    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


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
        # Use typed reader for consistent artifact parsing
        artifact = try_read_notification_artifact(
            path,
            run_id="",
            artifact_kind="notification",
            log_failures=False,  # Silent scan: skip malformed artifacts without logging
        )

        if artifact is None:
            # Update parse counter for malformed artifacts
            if counters is not None:
                counters["notification_files_fully_parsed"] += 1
            continue

        # Update parse counter
        if counters is not None:
            counters["notification_files_fully_parsed"] += 1

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
    max_records: int | None = None,
) -> tuple[list[tuple[NotificationArtifact, Path]], int]:
    """Optimized notification loading with early termination.

    Key optimizations:
    1. Early termination - stop once we have enough for page 1 (when safe)
    2. Filter during load - apply filters as we parse, not after
    3. Skip sorting when possible - files already in reverse chronological order
    4. Metadata-first rejection - skip full parse when kind filter in filename

    Args:
        directory: Path to the notifications directory
        kind_filter: Normalized kind filter (empty = no filter)
        cluster_filter: Normalized cluster filter (empty = no filter)
        search_term: Normalized search term (empty = no filter)
        counters: Optional dict to track observability metrics
        max_records: Early termination hint - stop after this many matches if set

    Returns:
        Tuple of (list of (NotificationArtifact, Path) tuples, total count)
        Total count is accurate when early termination is NOT used.
    """
    entries: list[tuple[NotificationArtifact, Path]] = []
    total_count = 0

    if not directory.is_dir():
        return entries, 0

    # Early termination is only safe when:
    # - max_records is set (page 1 of unfiltered query)
    # - no cluster filter (cluster is in content)
    # - no search term (search is in content)
    # When these conditions aren't met, we need full scan for accurate total
    use_early_termination = (
        max_records is not None
        and not cluster_filter
        and not search_term
    )

    # Can skip full parse based on metadata alone if only kind filter (no cluster, no search)
    use_filename_kind_filter = bool(kind_filter and not cluster_filter and not search_term)

    # Use reversed sorted glob to get newest first
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
        if "-" in filename:
            parts = filename.split("-", 1)
            if len(parts) == 2:
                filename_kind = parts[1].lower()

                # Metadata-based rejection: skip full parse when kind filter is in filename
                if use_filename_kind_filter and filename_kind != kind_filter:
                    if counters is not None:
                        counters["notification_files_rejected_by_metadata"] += 1
                    continue

        # Full parse required - use typed reader
        artifact = try_read_notification_artifact(
            path,
            run_id="",
            artifact_kind="notification",
            log_failures=False,  # Silent scan: skip malformed artifacts without logging
        )

        if artifact is None:
            # Update parse counter for malformed artifacts
            if counters is not None:
                counters["notification_files_fully_parsed"] += 1
            continue

        # Update parse counter
        if counters is not None:
            counters["notification_files_fully_parsed"] += 1

        # Apply filters during load
        if kind_filter:
            artifact_kind = artifact.kind.lower()
            if artifact_kind != kind_filter:
                continue

        if cluster_filter:
            artifact_cluster = _normalize_filter_value(artifact.cluster_label)
            if artifact_cluster != cluster_filter:
                continue

        if search_term and not _matches_search(artifact, search_term):
            continue

        # All filters passed
        entries.append((artifact, path))
        total_count += 1

        # Early termination: stop once we have enough for page 1
        # Safe ONLY when no content-based filters (cluster, search) - they need full scan
        if use_early_termination and max_records is not None and len(entries) >= max_records:
            if counters is not None:
                counters["early_termination"] = 1
            # Note: total_count is incomplete when early termination triggers
            # Caller must do count pass if accurate total is needed
            break

    # If we didn't use early termination, total_count is accurate
    return entries, total_count


def _count_matching_records(
    directory: Path,
    *,
    kind_filter: str = "",
    cluster_filter: str = "",
    search_term: str = "",
) -> int:
    """Lightweight count pass to get accurate total after early termination.

    Uses metadata from filename where possible to avoid full parse.
    For cluster/search filters, must do full parse but only counts, doesn't build artifacts.
    """
    if not directory.is_dir():
        return 0

    count = 0
    use_filename_kind_filter = bool(kind_filter and not cluster_filter and not search_term)
    all_files = directory.glob("*.json")

    for path in all_files:
        if not path.is_file():
            continue

        filename = path.stem
        filename_kind = ""

        # Try metadata-based filtering first
        if "-" in filename:
            parts = filename.split("-", 1)
            if len(parts) == 2:
                filename_kind = parts[1].lower()

                if use_filename_kind_filter and filename_kind != kind_filter:
                    continue

        # For unfiltered case, just count files (all match)
        if not kind_filter and not cluster_filter and not search_term:
            count += 1
            continue

        # Need content-based filtering - use typed reader
        artifact = try_read_notification_artifact(
            path,
            run_id="",
            artifact_kind="notification",
            log_failures=False,  # Silent scan
        )

        if artifact is None:
            continue

        # Apply remaining filters
        if kind_filter:
            if artifact.kind.lower() != kind_filter:
                continue

        if cluster_filter:
            if _normalize_filter_value(artifact.cluster_label) != cluster_filter:
                continue

        if search_term and not _matches_search(artifact, search_term):
            continue

        count += 1

    return count
