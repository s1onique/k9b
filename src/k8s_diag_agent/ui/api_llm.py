"""LLM serialization functions for the operator UI.

This module contains serializer functions for LLM-related payloads:
- LLM call statistics summary
- LLM activity log entries and summary
- LLM policy configuration and runtime state

Extracted from api.py to establish a clean separation of concerns.
These functions are re-exported from api.py for backward compatibility.

Ownership reminder:
    - Payload TypedDict classes live in api_payloads.py.
    - Serializer functions live here.
    - api.py is the public serialization surface.
"""

from __future__ import annotations

from .api_payloads import (
    LLMActivityPayload,
    LLMPolicyPayload,
    LLMStatsPayload,
)
from .model import (
    LLMActivityView,
    LLMPolicyView,
    LLMStatsView,
)


def _serialize_llm_stats(stats: LLMStatsView) -> LLMStatsPayload:
    """Serialize LLM call statistics view to payload dict."""
    return {
        "totalCalls": stats.total_calls,
        "successfulCalls": stats.successful_calls,
        "failedCalls": stats.failed_calls,
        "lastCallTimestamp": stats.last_call_timestamp,
        "p50LatencyMs": stats.p50_latency_ms,
        "p95LatencyMs": stats.p95_latency_ms,
        "p99LatencyMs": stats.p99_latency_ms,
        "providerBreakdown": [
            {
                "provider": entry.provider,
                "calls": entry.calls,
                "failedCalls": entry.failed_calls,
            }
            for entry in stats.provider_breakdown
        ],
        "scope": stats.scope,
    }


def _serialize_llm_activity(activity: LLMActivityView) -> LLMActivityPayload:
    """Serialize LLM activity view to payload dict."""
    return {
        "entries": [
            {
                "timestamp": entry.timestamp,
                "runId": entry.run_id,
                "runLabel": entry.run_label,
                "clusterLabel": entry.cluster_label,
                "toolName": entry.tool_name,
                "provider": entry.provider,
                "purpose": entry.purpose,
                "status": entry.status,
                "latencyMs": entry.latency_ms,
                "artifactPath": entry.artifact_path,
                "summary": entry.summary,
                "errorSummary": entry.error_summary,
                "skipReason": entry.skip_reason,
            }
            for entry in activity.entries
        ],
        "summary": {"retainedEntries": activity.summary.retained_entries},
    }


def _serialize_llm_policy(policy: LLMPolicyView | None) -> LLMPolicyPayload | None:
    """Serialize LLM policy view to payload dict."""
    if not policy or not policy.auto_drilldown:
        return None
    auto = policy.auto_drilldown
    return {
        "autoDrilldown": {
            "enabled": auto.enabled,
            "provider": auto.provider,
            "maxPerRun": auto.max_per_run,
            "usedThisRun": auto.used_this_run,
            "successfulThisRun": auto.successful_this_run,
            "failedThisRun": auto.failed_this_run,
            "skippedThisRun": auto.skipped_this_run,
            "budgetExhausted": auto.budget_exhausted,
        }
    }
