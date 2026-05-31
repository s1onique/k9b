"""LLM/provider activity payload contracts.

LLM call statistics, policy state, activity logs, and provider execution
branch summaries for the UI layer.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = [
    "AutoDrilldownPolicyPayload",
    "LLMActivityEntryPayload",
    "LLMActivityPayload",
    "LLMActivitySummaryPayload",
    "LLMPolicyPayload",
    "LLMProviderEntry",
    "LLMStatsPayload",
    "ProviderExecutionBranchPayload",
    "ProviderExecutionPayload",
]


class LLMProviderEntry(TypedDict):
    """Single provider breakdown entry in LLM stats."""

    provider: str
    calls: int
    failedCalls: int


class LLMStatsPayload(TypedDict):
    """Payload for LLM call statistics."""

    totalCalls: int
    successfulCalls: int
    failedCalls: int
    lastCallTimestamp: str | None
    p50LatencyMs: int | None
    p95LatencyMs: int | None
    p99LatencyMs: int | None
    providerBreakdown: list[LLMProviderEntry]
    scope: str


class AutoDrilldownPolicyPayload(TypedDict):
    """Payload for auto-drilldown policy state."""

    enabled: bool
    provider: str
    maxPerRun: int
    usedThisRun: int
    successfulThisRun: int
    failedThisRun: int
    skippedThisRun: int
    budgetExhausted: bool | None


class LLMPolicyPayload(TypedDict):
    """Payload for LLM policy state."""

    autoDrilldown: AutoDrilldownPolicyPayload


class LLMActivityEntryPayload(TypedDict, total=False):
    """Single LLM activity log entry."""

    timestamp: str | None
    runId: str | None
    runLabel: str | None
    clusterLabel: str | None
    toolName: str | None
    provider: str | None
    purpose: str | None
    status: str | None
    latencyMs: int | None
    artifactPath: str | None
    summary: str | None
    errorSummary: str | None
    skipReason: str | None


class LLMActivitySummaryPayload(TypedDict):
    """Summary section of LLM activity payload."""

    retainedEntries: int


class LLMActivityPayload(TypedDict):
    """Payload for LLM activity log."""

    entries: list[LLMActivityEntryPayload]
    summary: LLMActivitySummaryPayload


class ProviderExecutionBranchPayload(TypedDict, total=False):
    """Payload for a single provider execution branch."""

    enabled: bool | None
    provider: str | None
    maxPerRun: int | None
    eligible: int | None
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    unattempted: int | None
    budgetLimited: int | None
    notes: str | None


class ProviderExecutionPayload(TypedDict, total=False):
    """Payload for provider execution branch summary."""

    autoDrilldown: ProviderExecutionBranchPayload
    reviewEnrichment: ProviderExecutionBranchPayload
