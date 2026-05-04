"""LLM/provider stats and policy serialization for UI consumers."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..datetime_utils import parse_iso_to_utc
from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
)
from ..external_analysis.config import (
    AutoDrilldownPolicy,
    ExternalAnalysisSettings,
)
from .ui_serialization import _LLM_ACTIVITY_LIMIT  # noqa: E402
from .ui_shared import _relative_path

if TYPE_CHECKING:
    from .loop import DrilldownArtifact

# Scope constants for LLM stats aggregation
_SCOPE_CURRENT_RUN = "current_run"
_SCOPE_RETAINED_HISTORY = "retained_history"

# UTC-aware sentinel for sorting (datetime.min is naive, cannot compare with aware datetimes)
_EPOCH_SENTINEL = datetime.min.replace(tzinfo=UTC)


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

def _build_llm_stats(external_analysis: dict[str, object], scope: str = _SCOPE_CURRENT_RUN) -> dict[str, object]:
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
    historical_entries = entries or _collect_historical_external_analysis_entries(external_analysis_dir)
    return _compute_llm_stats(historical_entries, _SCOPE_RETAINED_HISTORY)

def _collect_historical_external_analysis_entries(
    directory: Path,
) -> list[Mapping[str, object]]:
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

def _compute_llm_stats(entries: Sequence[object], scope: str) -> dict[str, object]:
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

def _serialize_llm_activity(entries: Sequence[Mapping[str, object]], root_dir: Path, limit: int = _LLM_ACTIVITY_LIMIT) -> dict[str, object]:
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
            "summary": _coerce_optional_str(entry.get("summary")),
            "error_summary": _coerce_optional_str(entry.get("error_summary")),
            "skip_reason": _coerce_optional_str(entry.get("skip_reason")),
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

def _build_llm_policy(
    settings: ExternalAnalysisSettings | None,
    artifacts: Sequence[ExternalAnalysisArtifact],
    drilldown_count: int,
) -> dict[str, object]:
    config = settings or ExternalAnalysisSettings()
    policy = config.auto_drilldown
    auto_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.purpose == ExternalAnalysisPurpose.AUTO_DRILLDOWN
    ]
    used_statuses = {ExternalAnalysisStatus.SUCCESS, ExternalAnalysisStatus.FAILED}
    used_calls = sum(1 for artifact in auto_artifacts if artifact.status in used_statuses)
    successful_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.SUCCESS)
    failed_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.FAILED)
    skipped_calls = sum(1 for artifact in auto_artifacts if artifact.status == ExternalAnalysisStatus.SKIPPED)
    budget_exhausted: bool | None = None
    if policy.enabled and policy.max_per_run > 0:
        if len(auto_artifacts) >= policy.max_per_run and drilldown_count > len(auto_artifacts):
            budget_exhausted = True
        elif drilldown_count <= len(auto_artifacts):
            budget_exhausted = False
    return {
        "auto_drilldown": {
            "enabled": policy.enabled,
            "provider": policy.provider or "default",
            "maxPerRun": policy.max_per_run,
            "usedThisRun": used_calls,
            "successfulThisRun": successful_calls,
            "failedThisRun": failed_calls,
            "skippedThisRun": skipped_calls,
            "budgetExhausted": budget_exhausted,
        }
    }

def _build_provider_execution(
    settings: ExternalAnalysisSettings | None,
    artifacts: Sequence[ExternalAnalysisArtifact],
    drilldowns: Sequence[DrilldownArtifact],
    review_config: Mapping[str, object] | None,
) -> dict[str, object]:
    config = settings or ExternalAnalysisSettings()
    auto_policy = config.auto_drilldown
    return {
        "auto_drilldown": _build_auto_drilldown_execution(
            auto_policy, artifacts, len(drilldowns)
        ),
        "review_enrichment": _build_review_enrichment_execution(
            artifacts, review_config
        ),
    }

def _execution_counts_for_purpose(
    artifacts: Sequence[ExternalAnalysisArtifact],
    purpose: ExternalAnalysisPurpose,
) -> tuple[int, int, int]:
    success = 0
    failed = 0
    skipped = 0
    for artifact in artifacts:
        if artifact.purpose != purpose:
            continue
        status = artifact.status
        if status == ExternalAnalysisStatus.SUCCESS:
            success += 1
        elif status == ExternalAnalysisStatus.FAILED:
            failed += 1
        elif status == ExternalAnalysisStatus.SKIPPED:
            skipped += 1
    return success, failed, skipped

def _build_auto_drilldown_execution(
    policy: AutoDrilldownPolicy,
    artifacts: Sequence[ExternalAnalysisArtifact],
    eligible_count: int,
) -> dict[str, object]:
    succeeded, failed, skipped = _execution_counts_for_purpose(
        artifacts, ExternalAnalysisPurpose.AUTO_DRILLDOWN
    )
    attempted = succeeded + failed + skipped
    eligible: int | None = eligible_count if policy.enabled else None
    unattempted: int | None = None
    if eligible is not None and eligible > attempted:
        unattempted = eligible - attempted
    budget_limited: int | None = None
    if (
        eligible is not None
        and policy.max_per_run > 0
        and attempted >= policy.max_per_run
        and eligible > attempted
    ):
        budget_limited = eligible - attempted
    notes_parts: list[str] = []
    if budget_limited:
        notes_parts.append(
            f"Reached max per run ({policy.max_per_run}) before processing {budget_limited} eligible drilldown(s)."
        )
    elif unattempted:
        notes_parts.append(
            f"{unattempted} eligible drilldown(s) were not processed by the provider log."
        )
    notes = " ".join(notes_parts) if notes_parts else None
    return {
        "enabled": policy.enabled,
        "provider": policy.provider or "default",
        "maxPerRun": policy.max_per_run,
        "eligible": eligible,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "unattempted": unattempted,
        "budgetLimited": budget_limited,
        "notes": notes,
    }

def _extract_review_run_config(run_config: Mapping[str, object] | None) -> tuple[bool | None, str | None]:
    run_enabled: bool | None = None
    run_provider: str | None = None
    if isinstance(run_config, Mapping):
        if "enabled" in run_config:
            run_enabled = bool(run_config.get("enabled"))
        if "provider" in run_config:
            provider_raw = str(run_config.get("provider") or "").strip()
            run_provider = provider_raw or None
    return run_enabled, run_provider

def _build_review_enrichment_execution(
    artifacts: Sequence[ExternalAnalysisArtifact],
    run_config: Mapping[str, object] | None,
) -> dict[str, object]:
    succeeded, failed, skipped = _execution_counts_for_purpose(
        artifacts, ExternalAnalysisPurpose.REVIEW_ENRICHMENT
    )
    attempted = succeeded + failed + skipped
    run_enabled, run_provider = _extract_review_run_config(run_config)
    if run_enabled is None:
        eligible: int | None = None
    elif not run_enabled:
        eligible = 0
    elif run_provider:
        eligible = 1
    else:
        eligible = 0
    unattempted: int | None = None
    if eligible is not None and eligible > attempted:
        unattempted = eligible - attempted
    notes = None
    if unattempted and run_provider:
        notes = (
            f"Run configuration enabled review enrichment for '{run_provider}', but no artifact was recorded."
        )
    elif unattempted:
        notes = "Run configuration enabled review enrichment, but no artifact was recorded."
    return {
        "enabled": run_enabled,
        "eligible": eligible,
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "unattempted": unattempted,
        "budgetLimited": None,
        "notes": notes,
    }

def _percentile_value(values: list[float], percentile: float) -> int:
    if not values:
        return 0
    idx = math.ceil((percentile / 100) * len(values)) - 1
    idx = max(0, min(idx, len(values) - 1))
    return int(values[idx])

