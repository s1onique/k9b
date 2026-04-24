"""Import smoke tests for API payload backward compatibility.

Tests that representative payloads can be imported from both:
- The canonical source: k8s_diag_agent.ui.api_payloads
- The legacy re-export: k8s_diag_agent.ui.api

This ensures the first modularization slice preserves import compatibility
before serializer extraction begins.
"""

from __future__ import annotations

import pytest


# === Canonical source imports ===
def test_import_run_payload_from_api_payloads() -> None:
    """RunPayload can be imported from the canonical api_payloads module."""
    from k8s_diag_agent.ui.api_payloads import RunPayload

    assert RunPayload is not None
    # Basic smoke: can instantiate with required fields
    payload: RunPayload = {
        "runId": "test-run",
        "label": "Test Run",
        "timestamp": "2024-01-01T00:00:00Z",
        "collectorVersion": "1.0.0",
        "clusterCount": 3,
        "drilldownCount": 2,
        "proposalCount": 5,
        "externalAnalysisCount": 1,
        "notificationCount": 0,
        "artifacts": [],
        "runStats": {
            "lastRunDurationSeconds": None,
            "totalRuns": 10,
            "p50RunDurationSeconds": None,
            "p95RunDurationSeconds": None,
            "p99RunDurationSeconds": None,
        },
        "llmStats": {
            "totalCalls": 0,
            "successfulCalls": 0,
            "failedCalls": 0,
            "lastCallTimestamp": None,
            "p50LatencyMs": None,
            "p95LatencyMs": None,
            "p99LatencyMs": None,
            "providerBreakdown": [],
            "scope": "test",
        },
        "historicalLlmStats": None,
        "llmActivity": {
            "entries": [],
            "summary": {"retainedEntries": 0},
        },
        "llmPolicy": None,
        "reviewEnrichment": None,
        "reviewEnrichmentStatus": None,
        "providerExecution": None,
        "nextCheckExecutionHistory": [],
        "freshness": None,
        "nextCheckPlan": None,
        "nextCheckQueue": [],
        "nextCheckQueueExplanation": None,
        "deterministicNextChecks": None,
        "plannerAvailability": None,
        "diagnosticPackReview": None,
        "diagnosticPack": None,
        "alertmanagerCompact": None,
        "alertmanagerSources": None,
    }
    assert payload["runId"] == "test-run"


def test_import_runs_list_payload_from_api_payloads() -> None:
    """RunsListPayload can be imported from the canonical api_payloads module."""
    from k8s_diag_agent.ui.api_payloads import RunsListPayload

    assert RunsListPayload is not None
    payload: RunsListPayload = {
        "runs": [],
        "totalCount": 0,
    }
    assert payload["totalCount"] == 0


def test_import_next_check_plan_payload_from_api_payloads() -> None:
    """NextCheckPlanPayload can be imported from the canonical api_payloads module."""
    from k8s_diag_agent.ui.api_payloads import NextCheckPlanPayload

    assert NextCheckPlanPayload is not None
    payload: NextCheckPlanPayload = {
        "status": "planned",
        "summary": None,
        "artifactPath": None,
        "reviewPath": None,
        "enrichmentArtifactPath": None,
        "candidateCount": 0,
        "candidates": [],
        "orphanedApprovals": [],
        "outcomeCounts": [],
        "orphanedApprovalCount": 0,
    }
    assert payload["status"] == "planned"


def test_import_next_check_queue_item_payload_from_api_payloads() -> None:
    """NextCheckQueueItemPayload can be imported from the canonical api_payloads module."""
    from k8s_diag_agent.ui.api_payloads import NextCheckQueueItemPayload

    assert NextCheckQueueItemPayload is not None
    payload: NextCheckQueueItemPayload = {
        "candidateId": None,
        "candidateIndex": None,
        "description": "Test candidate",
        "targetCluster": None,
        "priorityLabel": None,
        "suggestedCommandFamily": None,
        "safeToAutomate": True,
        "requiresOperatorApproval": False,
        "approvalState": None,
        "executionState": None,
        "outcomeStatus": None,
        "latestArtifactPath": None,
        "queueStatus": "pending",
        "sourceReason": None,
        "expectedSignal": None,
        "normalizationReason": None,
        "safetyReason": None,
        "approvalReason": None,
        "duplicateReason": None,
        "blockingReason": None,
        "targetContext": None,
        "commandPreview": None,
        "planArtifactPath": None,
        "sourceType": None,
        "failureClass": None,
        "failureSummary": None,
        "suggestedNextOperatorMove": None,
        "resultClass": None,
        "resultSummary": None,
        "workstream": None,
    }
    assert payload["description"] == "Test candidate"


def test_import_alertmanager_compact_payload_from_api_payloads() -> None:
    """AlertmanagerCompactPayload can be imported from the canonical api_payloads module."""
    from k8s_diag_agent.ui.api_payloads import AlertmanagerCompactPayload

    assert AlertmanagerCompactPayload is not None
    payload: AlertmanagerCompactPayload = {
        "status": "ok",
        "alert_count": 5,
        "severity_counts": {"critical": 2, "warning": 3},
        "state_counts": {"firing": 4, "resolved": 1},
        "top_alert_names": ["PodNotReady", "HighMemoryUsage"],
        "affected_namespaces": ["default", "kube-system"],
        "affected_clusters": ["prod-cluster-1"],
        "affected_services": ["nginx", "redis"],
        "truncated": False,
        "captured_at": "2024-01-01T00:00:00Z",
        "by_cluster": [],
    }
    assert payload["alert_count"] == 5


def test_import_review_enrichment_payload_from_api_payloads() -> None:
    """ReviewEnrichmentPayload can be imported from the canonical api_payloads module."""
    from k8s_diag_agent.ui.api_payloads import ReviewEnrichmentPayload

    assert ReviewEnrichmentPayload is not None
    payload: ReviewEnrichmentPayload = {
        "status": "completed",
        "provider": "test-provider",
        "timestamp": "2024-01-01T00:00:00Z",
        "summary": "Test enrichment summary",
        "triageOrder": ["cluster-a", "cluster-b"],
        "topConcerns": ["Memory pressure", "Network issues"],
        "evidenceGaps": ["Missing metrics"],
        "nextChecks": ["kubectl top nodes"],
        "focusNotes": ["Focus on production clusters"],
        "alertmanagerEvidenceReferences": None,
        "artifactPath": "/path/to/enrichment.json",
        "errorSummary": None,
        "skipReason": None,
    }
    assert payload["status"] == "completed"


# === Legacy re-export imports ===
def test_import_run_payload_from_api() -> None:
    """RunPayload can be imported from the legacy api re-export."""
    from k8s_diag_agent.ui.api import RunPayload

    assert RunPayload is not None


def test_import_runs_list_payload_from_api() -> None:
    """RunsListPayload can be imported from the legacy api re-export."""
    from k8s_diag_agent.ui.api import RunsListPayload

    assert RunsListPayload is not None


def test_import_next_check_plan_payload_from_api() -> None:
    """NextCheckPlanPayload can be imported from the legacy api re-export."""
    from k8s_diag_agent.ui.api import NextCheckPlanPayload

    assert NextCheckPlanPayload is not None


def test_import_next_check_queue_item_payload_from_api() -> None:
    """NextCheckQueueItemPayload can be imported from the legacy api re-export."""
    from k8s_diag_agent.ui.api import NextCheckQueueItemPayload

    assert NextCheckQueueItemPayload is not None


def test_import_alertmanager_compact_payload_from_api() -> None:
    """AlertmanagerCompactPayload can be imported from the legacy api re-export."""
    from k8s_diag_agent.ui.api import AlertmanagerCompactPayload

    assert AlertmanagerCompactPayload is not None


def test_import_review_enrichment_payload_from_api() -> None:
    """ReviewEnrichmentPayload can be imported from the legacy api re-export."""
    from k8s_diag_agent.ui.api import ReviewEnrichmentPayload

    assert ReviewEnrichmentPayload is not None


# === Identity tests: both import paths yield the same class ===
def test_run_payload_identity() -> None:
    """Both import paths yield the same RunPayload class."""
    from k8s_diag_agent.ui.api import RunPayload as FromApi
    from k8s_diag_agent.ui.api_payloads import RunPayload as FromPayloads

    assert FromApi is FromPayloads


def test_runs_list_payload_identity() -> None:
    """Both import paths yield the same RunsListPayload class."""
    from k8s_diag_agent.ui.api import RunsListPayload as FromApi
    from k8s_diag_agent.ui.api_payloads import RunsListPayload as FromPayloads

    assert FromApi is FromPayloads


def test_next_check_plan_payload_identity() -> None:
    """Both import paths yield the same NextCheckPlanPayload class."""
    from k8s_diag_agent.ui.api import NextCheckPlanPayload as FromApi
    from k8s_diag_agent.ui.api_payloads import NextCheckPlanPayload as FromPayloads

    assert FromApi is FromPayloads


def test_next_check_queue_item_payload_identity() -> None:
    """Both import paths yield the same NextCheckQueueItemPayload class."""
    from k8s_diag_agent.ui.api import NextCheckQueueItemPayload as FromApi
    from k8s_diag_agent.ui.api_payloads import NextCheckQueueItemPayload as FromPayloads

    assert FromApi is FromPayloads


def test_alertmanager_compact_payload_identity() -> None:
    """Both import paths yield the same AlertmanagerCompactPayload class."""
    from k8s_diag_agent.ui.api import AlertmanagerCompactPayload as FromApi
    from k8s_diag_agent.ui.api_payloads import (
        AlertmanagerCompactPayload as FromPayloads,
    )

    assert FromApi is FromPayloads


def test_review_enrichment_payload_identity() -> None:
    """Both import paths yield the same ReviewEnrichmentPayload class."""
    from k8s_diag_agent.ui.api import ReviewEnrichmentPayload as FromApi
    from k8s_diag_agent.ui.api_payloads import (
        ReviewEnrichmentPayload as FromPayloads,
    )

    assert FromApi is FromPayloads
