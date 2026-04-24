"""View models for LLM activity (UI layer).

This module contains LLM activity view models extracted from model.py.
It exists to enable incremental modularization without changing behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_int,
    _coerce_optional_str,
)


@dataclass(frozen=True)
class LLMActivityEntryView:
    """View model for a single LLM activity entry."""
    timestamp: str | None
    run_id: str | None
    run_label: str | None
    cluster_label: str | None
    tool_name: str | None
    provider: str | None
    purpose: str | None
    status: str | None
    latency_ms: int | None
    artifact_path: str | None
    summary: str | None
    error_summary: str | None
    skip_reason: str | None


@dataclass(frozen=True)
class LLMActivitySummaryView:
    """View model for LLM activity summary."""
    retained_entries: int


@dataclass(frozen=True)
class LLMActivityView:
    """View model for LLM activity (entries + summary)."""
    entries: tuple[LLMActivityEntryView, ...]
    summary: LLMActivitySummaryView


def _build_llm_activity(raw: object | None) -> LLMActivityView:
    """Build LLMActivityView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return LLMActivityView(
            entries=(),
            summary=LLMActivitySummaryView(retained_entries=0),
        )
    entries_raw = raw.get("entries") or ()
    entries = tuple(
        _build_llm_activity_entry(entry)
        for entry in entries_raw
        if isinstance(entry, Mapping)
    )
    summary = _build_llm_activity_summary(raw.get("summary"))
    return LLMActivityView(entries=entries, summary=summary)


def _build_llm_activity_entry(raw: Mapping[str, object]) -> LLMActivityEntryView:
    """Build LLMActivityEntryView from raw JSON data."""
    return LLMActivityEntryView(
        timestamp=_coerce_optional_str(raw.get("timestamp")),
        run_id=_coerce_optional_str(raw.get("run_id")),
        run_label=_coerce_optional_str(raw.get("run_label")),
        cluster_label=_coerce_optional_str(raw.get("cluster_label")),
        tool_name=_coerce_optional_str(raw.get("tool_name")),
        provider=_coerce_optional_str(raw.get("provider")),
        purpose=_coerce_optional_str(raw.get("purpose")),
        status=_coerce_optional_str(raw.get("status")),
        latency_ms=_coerce_optional_int(raw.get("latency_ms")),
        artifact_path=_coerce_optional_str(raw.get("artifact_path")),
        summary=_coerce_optional_str(raw.get("summary")),
        error_summary=_coerce_optional_str(raw.get("error_summary")),
        skip_reason=_coerce_optional_str(raw.get("skip_reason")),
    )


def _build_llm_activity_summary(raw: object | None) -> LLMActivitySummaryView:
    """Build LLMActivitySummaryView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return LLMActivitySummaryView(retained_entries=0)
    return LLMActivitySummaryView(retained_entries=_coerce_int(raw.get("retained_entries")))
