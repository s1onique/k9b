"""Temporal fixture helpers for incident report staleness and freshness tests.

This module provides fixtures for testing temporal behavior in the incident report.

Fixtures:
- _fixture_multi_signal_warnings_pods_missing: multi-signal with warnings + missing pods
- _fixture_multi_signal_stale_with_enrichment: multi-signal with stale freshness + enrichment
"""

from __future__ import annotations

from typing import cast

from tests.fixtures.incident_report_fixtures_base import JsonObject
from tests.fixtures.incident_report_fixtures_worklist import (
    _fixture_multi_signal_warnings_pods_missing,
)


def _fixture_multi_signal_stale_with_enrichment() -> dict[str, object]:
    """Build a UI index combining degraded workload + stale freshness + provider enrichment.

    This fixture tests the incident report's ability to correctly handle:
    - Stale evidence warnings
    - Provider-assisted content in inferences (not facts)
    - Multiple signals (workload + enrichment)

    Expected outcomes:
    - status: degraded
    - staleEvidenceWarnings: non-empty ("Run freshness is stale")
    - facts: non-empty (deterministic drilldown facts only)
    - inferences: non-empty (provider enrichment AND assessment hypotheses)
    - enrichment in inferences NOT facts (critical invariant)
    - unknowns: non-empty
    - recommendations: non-empty

    Protects against: stale evidence being silently hidden or enrichment leaking to facts.
    """
    index = _fixture_multi_signal_warnings_pods_missing()
    run_entry = cast(JsonObject, index["run"])

    # Mark run data as stale
    run_entry["timestamp"] = "2026-01-01T00:20:00Z"  # 20 minutes ago
    run_entry["collector_version"] = "1.0"

    # Add provider-assisted review enrichment
    run_entry["review_enrichment"] = {
        "status": "success",
        "provider": "llamacpp",
        "timestamp": "2026-01-01T00:15:00Z",
        "summary": "High ingress latency detected; consider scaling the gateway. Pod crash patterns suggest memory misconfiguration.",
        "triageOrder": ["cluster-multi"],
        "topConcerns": ["ingress latency", "memory misconfiguration"],
        "evidenceGaps": ["CDN metrics", "memory profiling data"],
        "nextChecks": ["Collect ingress logs", "Check memory limits"],
        "focusNotes": ["Prioritize ingress investigation and memory configuration review"],
        "artifactPath": "external-analysis/run-multi-review-enrichment-llamacpp.json",
        "errorSummary": None,
        "skipReason": None,
    }
    run_entry["review_enrichment_config"] = {"enabled": True, "provider": "llamacpp"}

    # Update run stats to reflect longer interval
    run_stats = cast(dict[str, object], index["run_stats"])
    run_stats["last_run_duration_seconds"] = 1200  # 20 minutes
    run_stats["total_runs"] = 10

    # Update cluster missing evidence to include more signals
    clusters = cast(list[dict[str, object]], index["clusters"])
    if clusters:
        clusters[0]["missing_evidence"] = ["events", "pod_logs", "node_metrics"]

    # Update assessment to have more hypotheses
    assessment = cast(dict[str, object], index["latest_assessment"])
    assessment["missing_evidence"] = ["events", "pod_logs", "node_metrics"]
    assessment["hypotheses"] = [
        {
            "description": "Resource pressure on nodes causing OOM kills and restarts",
            "confidence": "medium",
            "probable_layer": "infrastructure",
            "what_would_falsify": "Node metrics show sufficient allocatable resources",
        },
        {
            "description": "Application misconfiguration with incorrect resource limits",
            "confidence": "medium",
            "probable_layer": "workload",
            "what_would_falsify": "Resource limits are appropriately sized",
        },
    ]

    return index
