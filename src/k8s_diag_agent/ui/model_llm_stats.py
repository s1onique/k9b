"""View models for LLM statistics (UI layer).

This module contains LLM statistics view models extracted from model.py.
It exists to enable incremental modularization without changing behavior.

Moved symbols:
- ProviderBreakdownEntry
- LLMStatsView
- _build_llm_stats_view
- _build_optional_llm_stats_view
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_int,
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class ProviderBreakdownEntry:
    """View model for a single provider's call statistics."""
    provider: str
    calls: int
    failed_calls: int


@dataclass(frozen=True)
class LLMStatsView:
    """View model for LLM call statistics summary."""
    total_calls: int
    successful_calls: int
    failed_calls: int
    last_call_timestamp: str | None
    p50_latency_ms: int | None
    p95_latency_ms: int | None
    p99_latency_ms: int | None
    provider_breakdown: tuple[ProviderBreakdownEntry, ...]
    scope: str = "current_run"


def _build_llm_stats_view(raw: object | None) -> LLMStatsView:
    """Build LLMStatsView from raw JSON data."""
    if not isinstance(raw, Mapping):
        return LLMStatsView(
            total_calls=0,
            successful_calls=0,
            failed_calls=0,
            last_call_timestamp=None,
            p50_latency_ms=None,
            p95_latency_ms=None,
            p99_latency_ms=None,
            provider_breakdown=(),
        )
    breakdown_raw = raw.get("providerBreakdown") or ()
    breakdown = tuple(
        ProviderBreakdownEntry(
            provider=_coerce_str(entry.get("provider")),
            calls=_coerce_int(entry.get("calls")),
            failed_calls=_coerce_int(entry.get("failedCalls")),
        )
        for entry in breakdown_raw
        if isinstance(entry, Mapping)
    )
    scope_value = _coerce_optional_str(raw.get("scope")) or "current_run"
    return LLMStatsView(
        total_calls=_coerce_int(raw.get("totalCalls")),
        successful_calls=_coerce_int(raw.get("successfulCalls")),
        failed_calls=_coerce_int(raw.get("failedCalls")),
        last_call_timestamp=_coerce_optional_str(raw.get("lastCallTimestamp")),
        p50_latency_ms=_coerce_optional_int(raw.get("p50LatencyMs")),
        p95_latency_ms=_coerce_optional_int(raw.get("p95LatencyMs")),
        p99_latency_ms=_coerce_optional_int(raw.get("p99LatencyMs")),
        provider_breakdown=breakdown,
        scope=scope_value,
    )


def _build_optional_llm_stats_view(raw: object | None) -> LLMStatsView | None:
    """Build LLMStatsView from raw JSON data, or None if input is not a Mapping."""
    if not isinstance(raw, Mapping):
        return None
    return _build_llm_stats_view(raw)
