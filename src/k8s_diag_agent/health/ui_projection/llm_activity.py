"""Historical LLM stats aggregation and activity serialization.

This module provides pure derivation helpers for collecting and serializing
historical LLM/provider statistics and activity data from external analysis
artifacts.

Responsibilities:
- Collect historical external analysis entries from disk
- Compute aggregate LLM stats (calls, latency percentiles, provider breakdown)
- Serialize LLM activity entries with de-anonymization support
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ...datetime_utils import parse_iso_to_utc
from ...security.deanonymization import deanonymize_text
from ..ui_serialization import _LLM_ACTIVITY_LIMIT  # noqa: E402
from ..ui_shared import _relative_path

if TYPE_CHECKING:
    pass


# =============================================================================
# Constants: Scope and Sentinel
# =============================================================================

# Scope constants for LLM stats aggregation
_SCOPE_CURRENT_RUN = "current_run"
_SCOPE_RETAINED_HISTORY = "retained_history"

# UTC-aware sentinel for sorting (datetime.min is naive, cannot compare with aware datetimes)
_EPOCH_SENTINEL = datetime.min.replace(tzinfo=UTC)


# =============================================================================
# Re-exports for backward compatibility
# =============================================================================

__all__ = [
    "_SCOPE_CURRENT_RUN",
    "_SCOPE_RETAINED_HISTORY",
    "_EPOCH_SENTINEL",
    "_build_historical_llm_stats",
    "_build_llm_stats",
    "_collect_historical_external_analysis_entries",
    "_coerce_optional_str",
    "_compute_llm_stats",
    "_parse_optional_int",
    "_parse_timestamp",
    "_serialize_llm_activity",
    "_percentile_value",
]


# =============================================================================
# Parsing Helpers
# =============================================================================


def _parse_optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _parse_timestamp(value: object | None) -> datetime | None:
    """Parse an ISO timestamp string to timezone-aware UTC datetime."""
    return parse_iso_to_utc(value)


def _coerce_optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


# =============================================================================
# Historical Entry Collection
# =============================================================================


def _collect_historical_external_analysis_entries(
    directory: Path,
) -> list[Mapping[str, object]]:
    """Collect external analysis entries from JSON artifacts in a directory."""
    entries: list[Mapping[str, object]] = []
    if not directory.is_dir():
        return entries
    for path in sorted(directory.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(raw, Mapping):
            entries.append(raw)
    return entries


# =============================================================================
# Stats Computation
# =============================================================================


def _compute_llm_stats(entries: Sequence[object], scope: str) -> dict[str, object]:
    """Compute aggregate LLM stats from a sequence of entries."""
    total_calls = 0
    successful_calls = 0
    failed_calls = 0
    durations: list[int] = []
    latest_timestamp: datetime | None = None
    latest_timestamp_str: str | None = None
    provider_counts: dict[str, dict[str, int]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        status = str(entry.get("status") or "").lower()
        if status not in ("success", "failed"):
            continue
        total_calls += 1
        if status == "success":
            successful_calls += 1
        if status == "failed":
            failed_calls += 1
        raw_timestamp = entry.get("timestamp")
        timestamp = _parse_timestamp(raw_timestamp)
        if timestamp:
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp
                latest_timestamp_str = raw_timestamp if isinstance(raw_timestamp, str) else latest_timestamp_str
        duration = _parse_optional_int(entry.get("duration_ms"))
        if duration is not None:
            durations.append(duration)
        provider = str(entry.get("tool_name") or "unknown")
        counter = provider_counts.setdefault(provider, {"calls": 0, "failedCalls": 0})
        counter["calls"] += 1
        if status == "failed":
            counter["failedCalls"] += 1
    percentile_values: dict[str, int | None] = {
        "p50": None,
        "p95": None,
        "p99": None,
    }
    if durations:
        float_durations = [float(value) for value in durations]
        float_durations.sort()
        percentile_values["p50"] = _percentile_value(float_durations, 50)
        percentile_values["p95"] = _percentile_value(float_durations, 95)
        percentile_values["p99"] = _percentile_value(float_durations, 99)
    provider_breakdown = [
        {"provider": provider, "calls": data["calls"], "failedCalls": data["failedCalls"]}
        for provider, data in sorted(provider_counts.items())
    ]
    return {
        "totalCalls": total_calls,
        "successfulCalls": successful_calls,
        "failedCalls": failed_calls,
        "lastCallTimestamp": latest_timestamp_str,
        "p50LatencyMs": percentile_values["p50"],
        "p95LatencyMs": percentile_values["p95"],
        "p99LatencyMs": percentile_values["p99"],
        "providerBreakdown": provider_breakdown,
        "scope": scope,
    }


def _build_llm_stats(external_analysis: dict[str, object], scope: str = _SCOPE_CURRENT_RUN) -> dict[str, object]:
    """Build LLM stats for the current run from external analysis data."""
    from ...external_analysis.artifact import ExternalAnalysisPurpose

    artifacts = external_analysis.get("artifacts") or ()
    if not isinstance(artifacts, Sequence):
        artifacts = ()
    filtered = [
        entry
        for entry in artifacts
        if isinstance(entry, Mapping)
        and entry.get("purpose") != ExternalAnalysisPurpose.NEXT_CHECK_PLANNING.value
    ]
    return _compute_llm_stats(filtered, scope)


def _build_historical_llm_stats(
    external_analysis_dir: Path,
    entries: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Build LLM stats from historical external analysis entries."""
    historical_entries = entries or _collect_historical_external_analysis_entries(external_analysis_dir)
    return _compute_llm_stats(historical_entries, _SCOPE_RETAINED_HISTORY)


# =============================================================================
# Activity Serialization
# =============================================================================


def _serialize_llm_activity(
    entries: Sequence[Mapping[str, object]],
    root_dir: Path,
    limit: int = _LLM_ACTIVITY_LIMIT,
    alias_mapping: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Serialize LLM activity entries with de-anonymization support."""
    normalized: list[tuple[datetime | None, dict[str, object]]] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        timestamp_value = entry.get("timestamp")
        timestamp = _parse_timestamp(timestamp_value)
        if isinstance(timestamp_value, str):
            timestamp_str = timestamp_value
        elif timestamp:
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = None

        # FIX: De-anonymize text fields to prevent provider aliases from leaking to UI
        summary = _coerce_optional_str(entry.get("summary"))
        if summary and alias_mapping:
            summary = deanonymize_text(summary, alias_mapping)
        error_summary = _coerce_optional_str(entry.get("error_summary"))
        if error_summary and alias_mapping:
            error_summary = deanonymize_text(error_summary, alias_mapping)
        skip_reason = _coerce_optional_str(entry.get("skip_reason"))
        if skip_reason and alias_mapping:
            skip_reason = deanonymize_text(skip_reason, alias_mapping)

        activity_entry: dict[str, object] = {
            "timestamp": timestamp_str,
            "run_id": _coerce_optional_str(entry.get("run_id")),
            "run_label": _coerce_optional_str(entry.get("run_label")),
            "cluster_label": _coerce_optional_str(entry.get("cluster_label")),
            "tool_name": _coerce_optional_str(entry.get("tool_name")),
            "provider": _coerce_optional_str(entry.get("provider")),
            "purpose": _coerce_optional_str(entry.get("purpose")),
            "status": _coerce_optional_str(entry.get("status")),
            "latency_ms": _parse_optional_int(entry.get("duration_ms")),
            "artifact_path": _relative_path(root_dir, entry.get("artifact_path")),
            "summary": summary,
            "error_summary": error_summary,
            "skip_reason": skip_reason,
        }
        normalized.append((timestamp, activity_entry))
    sorted_entries = sorted(
        normalized,
        key=lambda item: item[0] or _EPOCH_SENTINEL,
        reverse=True,
    )
    trimmed_entries = [payload for _, payload in sorted_entries[:limit]]
    return {
        "entries": trimmed_entries,
        "summary": {"retained_entries": len(normalized)},
    }


# =============================================================================
# Percentile Calculation
# =============================================================================


def _percentile_value(values: list[float], percentile: float) -> int:
    """Calculate a percentile value from a sorted list of floats."""
    if not values:
        return 0
    idx = math.ceil((percentile / 100) * len(values)) - 1
    idx = max(0, min(idx, len(values) - 1))
    return int(values[idx])
