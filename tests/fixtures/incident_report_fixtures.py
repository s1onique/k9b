"""Golden fixture helpers for incident report and operator worklist quality tests.

This module provides deterministic fixture builders that construct synthetic UI index
structures for testing the incidentReport and operatorWorklist payload builders.

Purpose
-------
- Provide replayable, deterministic run-state fixtures for regression testing
- Protect against provider-assisted content leaking into facts
- Protect against stale evidence being silently hidden
- Protect against fabricated "unknown" artifact paths
- Protect against null commands being converted to fake runnable strings

Hard gates enforced by tests
---------------------------
1. Provider-assisted review enrichment must not appear in facts
2. Unknowns/missing evidence must be explicit
3. Stale evidence must create staleEvidenceWarnings
4. sourceArtifactRefs must be real links or empty, never fake "unknown" paths
5. Deterministic next checks with no executable command must keep command null
6. Queue/worklist items with executable command must expose command, target/context,
   reason, expected evidence, safety note, and state

How to add a new fixture
------------------------
1. Choose the fixture pattern that best matches your scenario:
   - healthy_no_incident: no degraded clusters, no provider enrichment
   - degraded_single_cluster: assessment + drilldown, missing evidence, worklist items
   - stale_provider_enriched_degraded: stale freshness, review_enrichment present
   - deterministic_only_no_command: deterministic next checks, no queue items

2. Call the builder function to get a dict-structured UI index
3. Pass to build_ui_context() from k8s_diag_agent.ui.model
4. Call the target builder (_build_incident_report_payload or _build_operator_worklist_payload)

Fixture naming convention
------------------------
- Builder functions: _fixture_<scenario_name>
- Return type: dict[str, object] (UI index structure)
- Each builder documents what it protects and what the expected output is

Example usage
-------------
    from tests.fixtures.incident_report_fixtures import (
        _fixture_healthy_no_incident,
        _fixture_degraded_single_cluster,
        _fixture_stale_provider_enriched_degraded,
        _fixture_deterministic_only_no_command,
    )
    from k8s_diag_agent.ui.model import build_ui_context
    from k8s_diag_agent.ui.api_incident_report import (
        _build_incident_report_payload,
        _build_operator_worklist_payload,
    )

    # Test degraded run
    index = _fixture_degraded_single_cluster()
    context = build_ui_context(index)
    report = _build_incident_report_payload(context, _freshness("fresh"))
    assert report["status"] == "degraded"
    assert report["facts"]
    assert report["unknowns"]  # missing evidence surfaces here
    assert report["recommendedActions"]  # actions present
    assert report["sourceArtifactRefs"]  # real paths only

    # Test stale provider-enriched run
    index = _fixture_stale_provider_enriched_degraded()
    context = build_ui_context(index)
    report = _build_incident_report_payload(context, _freshness("stale"))
    assert report["staleEvidenceWarnings"]
    enrichment_in_inferences = any(
        "enrichment" in str(i.get("basis", [])) for i in report["inferences"]
    )
    assert enrichment_in_inferences
    enrichment_in_facts = any(
        "enrichment" in str(f["statement"]).lower() for f in report["facts"]
    )
    assert not enrichment_in_facts  # must NOT be in facts

    # Test deterministic items have null command
    index = _fixture_deterministic_only_no_command()
    context = build_ui_context(index)
    worklist = _build_operator_worklist_payload(context)
    assert worklist is not None
    for item in worklist["items"]:
        assert item["command"] is None  # no fake runnable command

    # Test queue item with command
    index = _fixture_degraded_single_cluster()
    context = build_ui_context(index)
    worklist = _build_operator_worklist_payload(context)
    assert worklist is not None
    queue_items = [i for i in worklist["items"] if "queue-" in str(i.get("id", ""))]
    if queue_items:
        item = queue_items[0]
        assert item["command"] is not None
        assert item["targetCluster"] is not None
        assert item["targetContext"] is not None
        assert item["reason"] is not None
        assert item["expectedEvidence"] is not None
        assert item["safetyNote"] is not None
        assert item["approvalState"] is not None
        assert item["executionState"] is not None
        assert item["feedbackState"] is not None
"""

from __future__ import annotations

from typing import Any, TypeAlias, cast

JsonObject: TypeAlias = dict[str, Any]


def _freshness(status: str) -> dict[str, Any]:
    """Return a freshness payload with the given status."""
    return {
        "ageSeconds": 600,
        "expectedIntervalSeconds": 300,
        "status": status,
    }


def _fixture_healthy_no_incident() -> dict[str, object]:
    """Build a UI index for a healthy run with no degraded clusters.

    Expected outcomes:
    - status: healthy
    - title: "No degraded clusters detected"
    - facts: contains the "No degraded clusters or incidents detected" honest statement
    - inferences: empty
    - unknowns: empty
    - staleEvidenceWarnings: empty
    - recommendedActions: empty
    - sourceArtifactRefs: empty or minimal

    Protects against: inventing concern where none exists.
    """
    return {
        "run": {
            "run_id": "run-healthy",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 0,
            "proposal_count": 0,
            "external_analysis_count": 0,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 0,
                "successfulCalls": 0,
                "failedCalls": 0,
                "lastCallTimestamp": None,
                "p50LatencyMs": None,
                "p95LatencyMs": None,
                "p99LatencyMs": None,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": None,
            "planner_availability": None,
            "next_check_queue": [],
            "next_check_execution_history": [],
            "deterministic_next_checks": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 30,
            "total_runs": 1,
            "p50_run_duration_seconds": 30,
            "p95_run_duration_seconds": 30,
            "p99_run_duration_seconds": 30,
        },
        "clusters": [
            {
                "label": "cluster-healthy",
                "context": "cluster-healthy",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "healthy",
                "warnings": 0,
                "non_running_pods": 0,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-healthy.json",
                    "assessment": "assessments/cluster-healthy.json",
                    "drilldown": None,
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "healthy", "count": 1}],
            "degraded_clusters": [],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": None,
        "latest_assessment": {
            "cluster_label": "cluster-healthy",
            "context": "cluster-healthy",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "healthy",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": None,
            "overall_confidence": "high",
            "probable_layer_of_origin": None,
            "artifact_path": "assessments/cluster-healthy.json",
            "snapshot_path": "snapshots/cluster-healthy.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 0,
            "missing": 1,
            "coverage": [
                {
                    "label": "cluster-healthy",
                    "context": "cluster-healthy",
                    "available": False,
                    "timestamp": None,
                    "artifact_path": None,
                }
            ],
            "missing_clusters": ["cluster-healthy"],
        },
        "notification_history": [],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


# =============================================================================
# Adaptation Effect Regression Fixtures (Epic: BETA-G5 Feedback Adaptation Provenance)
# =============================================================================


def _fixture_useful_result_hypothesis_strengthened() -> dict[str, object]:
    """Build a UI index with useful feedback that strengthens the leading hypothesis.

    Expected outcomes:
    - worklist: non-empty with executed/reviewed item
    - executed item has usefulnessClass: useful
    - adaptationEffect: hypothesis_strengthened
    - adaptationSummary includes hypothesis strengthening context
    - itemState: reviewed

    Protects against: useful feedback not being linked to adaptation provenance.
    """
    index = _fixture_executed_with_usefulness()
    run_entry = cast(JsonObject, index["run"])

    # The executed-with-usefulness fixture already has usefulnessClass: useful
    # Update execution history to have strong useful signal
    history = cast(list[dict[str, object]], run_entry["next_check_execution_history"])
    if history:
        history[0]["usefulnessClass"] = "useful"
        history[0]["usefulnessSummary"] = "Found key crash events confirming CrashLoopBackOff pattern"
        history[0]["resultClass"] = "useful-signal"
        history[0]["resultSummary"] = "Captured pod events showing repeated crash restarts."

    # Update queue item to have the usefulness fields
    queue = cast(list[dict[str, object]], run_entry["next_check_queue"])
    if queue:
        queue[0]["usefulnessClass"] = "useful"
        queue[0]["usefulnessSummary"] = "Found key crash events"
        queue[0]["resultClass"] = "useful-signal"
        queue[0]["resultSummary"] = "Captured pod events showing repeated crash restarts."
        queue[0]["executionState"] = "executed-success"
        queue[0]["queueStatus"] = "completed"

    return index


def _fixture_noisy_result_no_material_change() -> dict[str, object]:
    """Build a UI index with noisy feedback that has no material change.

    Expected outcomes:
    - worklist: non-empty with executed/reviewed item
    - executed item has usefulnessClass: noisy
    - adaptationEffect: no_material_change
    - adaptationSummary honestly represents no diagnostic impact
    - itemState: reviewed
    - feedback doesn't silently rewrite facts

    Protects against: noisy feedback being treated as useful or changing diagnosis.
    """
    return {
        "run": {
            "run_id": "run-noisy",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 1,
                "successfulCalls": 1,
                "failedCalls": 0,
                "lastCallTimestamp": "2026-01-01T00:00:30Z",
                "p50LatencyMs": 450,
                "p95LatencyMs": 890,
                "p99LatencyMs": 1200,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-noisy-next-check-plan.json",
                "summary": "1 candidate.",
                "candidateCount": 1,
                "candidates": [
                    {
                        "description": "Collect detailed pod logs",
                        "targetCluster": "cluster-noisy",
                        "sourceReason": "CrashLoopBackOff investigation",
                        "expectedSignal": "Crash logs with stack traces",
                        "suggestedCommandFamily": "kubectl-logs",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-logs",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "executed-success",
                        "outcomeStatus": "executed-success",
                        "latestArtifactPath": "runs/health/external-analysis/run-noisy-exec-0.json",
                        "latestTimestamp": "2026-01-01T00:05:00Z",
                        "targetContext": "cluster-noisy · default",
                        "commandPreview": "kubectl logs pod/my-pod --context cluster-noisy",
                    }
                ],
                "outcomeCounts": [{"status": "executed-success", "count": 1}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "1 candidate.",
                "artifactPath": "runs/health/external-analysis/run-noisy-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-logs",
                    "candidateIndex": 0,
                    "description": "Collect detailed pod logs",
                    "targetCluster": "cluster-noisy",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "executed-success",
                    "outcomeStatus": "executed-success",
                    "latestArtifactPath": "runs/health/external-analysis/run-noisy-exec-0.json",
                    "sourceReason": "CrashLoopBackOff investigation",
                    "expectedSignal": "Crash logs with stack traces",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-noisy · default",
                    "commandPreview": "kubectl logs pod/my-pod --context cluster-noisy",
                    "planArtifactPath": "runs/health/external-analysis/run-noisy-next-check-plan.json",
                    "queueStatus": "completed",
                    "usefulnessClass": "noisy",
                    "usefulnessSummary": "Logs contained only routine startup messages, no crash details",
                    "resultClass": "noisy-signal",
                    "resultSummary": "Captured routine logs without crash details.",
                }
            ],
            "next_check_execution_history": [
                {
                    "timestamp": "2026-01-01T00:05:00Z",
                    "clusterLabel": "cluster-noisy",
                    "candidateDescription": "Collect detailed pod logs",
                    "commandFamily": "kubectl-logs",
                    "status": "success",
                    "durationMs": 620,
                    "artifactPath": "runs/health/external-analysis/run-noisy-exec-0.json",
                    "timedOut": False,
                    "stdoutTruncated": False,
                    "stderrTruncated": False,
                    "outputBytesCaptured": 840,
                    "resultClass": "noisy-signal",
                    "resultSummary": "Captured routine logs without crash details.",
                    "usefulnessClass": "noisy",
                    "usefulnessSummary": "Logs contained only routine startup messages, no crash details",
                    "suggestedNextOperatorMove": "Try collecting events instead.",
                }
            ],
            "deterministic_next_checks": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 5,
            "p50_run_duration_seconds": 40,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": [
            {
                "label": "cluster-noisy",
                "context": "cluster-noisy",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-noisy.json",
                    "assessment": "assessments/cluster-noisy.json",
                    "drilldown": "drilldowns/cluster-noisy.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-noisy"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-noisy",
            "context": "cluster-noisy",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 2,
            "non_running_pods": 1,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {"pattern": "crashloop"},
            "artifact_path": "drilldowns/cluster-noisy.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-noisy",
            "context": "cluster-noisy",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate pod crash",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-noisy.json",
            "snapshot_path": "snapshots/cluster-noisy.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-noisy",
                    "context": "cluster-noisy",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-noisy.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_partial_result_unknown_resolved() -> dict[str, object]:
    """Build a UI index with partial feedback that resolves one unknown.

    Expected outcomes:
    - worklist: non-empty with executed/reviewed item
    - executed item has usefulnessClass: partial
    - adaptationEffect: unknown_resolved
    - adaptationSummary indicates evidence gap was partially filled
    - itemState: reviewed

    Protects against: partial feedback being treated as fully conclusive.
    """
    return {
        "run": {
            "run_id": "run-partial",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 1,
                "successfulCalls": 1,
                "failedCalls": 0,
                "lastCallTimestamp": "2026-01-01T00:00:30Z",
                "p50LatencyMs": 450,
                "p95LatencyMs": 890,
                "p99LatencyMs": 1200,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-partial-next-check-plan.json",
                "summary": "1 candidate.",
                "candidateCount": 1,
                "candidates": [
                    {
                        "description": "Check pod events for CrashLoopBackOff",
                        "targetCluster": "cluster-partial",
                        "sourceReason": "CrashLoopBackOff investigation",
                        "expectedSignal": "Recent crash events",
                        "suggestedCommandFamily": "kubectl-get",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-events",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "executed-success",
                        "outcomeStatus": "executed-success",
                        "latestArtifactPath": "runs/health/external-analysis/run-partial-exec-0.json",
                        "latestTimestamp": "2026-01-01T00:05:00Z",
                        "targetContext": "cluster-partial · default",
                        "commandPreview": "kubectl get events --context cluster-partial",
                    }
                ],
                "outcomeCounts": [{"status": "executed-success", "count": 1}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "1 candidate.",
                "artifactPath": "runs/health/external-analysis/run-partial-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-events",
                    "candidateIndex": 0,
                    "description": "Check pod events for CrashLoopBackOff",
                    "targetCluster": "cluster-partial",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-get",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "executed-success",
                    "outcomeStatus": "executed-success",
                    "latestArtifactPath": "runs/health/external-analysis/run-partial-exec-0.json",
                    "sourceReason": "CrashLoopBackOff investigation",
                    "expectedSignal": "Recent crash events",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-partial · default",
                    "commandPreview": "kubectl get events --context cluster-partial",
                    "planArtifactPath": "runs/health/external-analysis/run-partial-next-check-plan.json",
                    "queueStatus": "completed",
                    "usefulnessClass": "partial",
                    "usefulnessSummary": "Found crash events but exit code missing from logs",
                    "resultClass": "partial-signal",
                    "resultSummary": "Captured pod events showing restarts but exit codes incomplete.",
                }
            ],
            "next_check_execution_history": [
                {
                    "timestamp": "2026-01-01T00:05:00Z",
                    "clusterLabel": "cluster-partial",
                    "candidateDescription": "Check pod events for CrashLoopBackOff",
                    "commandFamily": "kubectl-get",
                    "status": "success",
                    "durationMs": 620,
                    "artifactPath": "runs/health/external-analysis/run-partial-exec-0.json",
                    "timedOut": False,
                    "stdoutTruncated": False,
                    "stderrTruncated": False,
                    "outputBytesCaptured": 1240,
                    "resultClass": "partial-signal",
                    "resultSummary": "Captured pod events showing restarts but exit codes incomplete.",
                    "usefulnessClass": "partial",
                    "usefulnessSummary": "Found crash events but exit code missing from logs",
                    "suggestedNextOperatorMove": "Collect logs to get exit codes.",
                }
            ],
            "deterministic_next_checks": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 5,
            "p50_run_duration_seconds": 40,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": [
            {
                "label": "cluster-partial",
                "context": "cluster-partial",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": ["exit_code"],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-partial.json",
                    "assessment": "assessments/cluster-partial.json",
                    "drilldown": "drilldowns/cluster-partial.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-partial"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-partial",
            "context": "cluster-partial",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 2,
            "non_running_pods": 1,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {"pattern": "crashloop"},
            "artifact_path": "drilldowns/cluster-partial.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-partial",
            "context": "cluster-partial",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": ["exit_code"],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate pod crash",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-partial.json",
            "snapshot_path": "snapshots/cluster-partial.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-partial",
                    "context": "cluster-partial",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-partial.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_executed_result_promotes_action() -> dict[str, object]:
    """Build a UI index with executed feedback that promotes a new action.

    Expected outcomes:
    - worklist: non-empty with executed/reviewed item
    - executed item has usefulnessClass: useful
    - adaptationEffect: recommendation_promoted
    - adaptationSummary indicates a new recommended action was surfaced
    - itemState: reviewed

    Protects against: useful execution not leading to action promotion.
    """
    return {
        "run": {
            "run_id": "run-promote",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 1,
                "successfulCalls": 1,
                "failedCalls": 0,
                "lastCallTimestamp": "2026-01-01T00:00:30Z",
                "p50LatencyMs": 450,
                "p95LatencyMs": 890,
                "p99LatencyMs": 1200,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-promote-next-check-plan.json",
                "summary": "2 candidates.",
                "candidateCount": 2,
                "candidates": [
                    {
                        "description": "Check node resource pressure",
                        "targetCluster": "cluster-promote",
                        "sourceReason": "Multiple pods affected",
                        "expectedSignal": "Node allocatable and current usage",
                        "suggestedCommandFamily": "kubectl-top",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "medium",
                        "priorityLabel": "secondary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-nodes",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "executed-success",
                        "outcomeStatus": "executed-success",
                        "latestArtifactPath": "runs/health/external-analysis/run-promote-exec-0.json",
                        "latestTimestamp": "2026-01-01T00:05:00Z",
                        "targetContext": "cluster-promote",
                        "commandPreview": "kubectl top nodes --context cluster-promote",
                    },
                    {
                        "description": "Collect kubelet logs",
                        "targetCluster": "cluster-promote",
                        "sourceReason": "Node pressure detected from events",
                        "expectedSignal": "Kubelet error messages",
                        "suggestedCommandFamily": "kubectl-logs",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "medium",
                        "priorityLabel": "secondary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-kubelet",
                        "candidateIndex": 1,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "unexecuted",
                        "outcomeStatus": "unexecuted",
                        "latestArtifactPath": None,
                        "latestTimestamp": None,
                        "targetContext": "cluster-promote",
                        "commandPreview": "kubectl logs -n kube-system -l k8s-app=kubelet --context cluster-promote",
                    },
                ],
                "outcomeCounts": [
                    {"status": "executed-success", "count": 1},
                    {"status": "unexecuted", "count": 1},
                ],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "2 candidates.",
                "artifactPath": "runs/health/external-analysis/run-promote-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-nodes",
                    "candidateIndex": 0,
                    "description": "Check node resource pressure",
                    "targetCluster": "cluster-promote",
                    "priorityLabel": "secondary",
                    "suggestedCommandFamily": "kubectl-top",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "executed-success",
                    "outcomeStatus": "executed-success",
                    "latestArtifactPath": "runs/health/external-analysis/run-promote-exec-0.json",
                    "sourceReason": "Multiple pods affected",
                    "expectedSignal": "Node allocatable and current usage",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-promote",
                    "commandPreview": "kubectl top nodes --context cluster-promote",
                    "planArtifactPath": "runs/health/external-analysis/run-promote-next-check-plan.json",
                    "queueStatus": "completed",
                    "usefulnessClass": "useful",
                    "usefulnessSummary": "Found high memory pressure on node-1, elevated risk of OOM",
                    "resultClass": "useful-signal",
                    "resultSummary": "Captured node metrics showing memory pressure on node-1.",
                },
                {
                    "candidateId": "candidate-kubelet",
                    "candidateIndex": 1,
                    "description": "Collect kubelet logs",
                    "targetCluster": "cluster-promote",
                    "priorityLabel": "secondary",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "unexecuted",
                    "outcomeStatus": "unexecuted",
                    "latestArtifactPath": None,
                    "sourceReason": "Node pressure detected from events",
                    "expectedSignal": "Kubelet error messages",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-promote",
                    "commandPreview": "kubectl logs -n kube-system -l k8s-app=kubelet --context cluster-promote",
                    "planArtifactPath": "runs/health/external-analysis/run-promote-next-check-plan.json",
                    "queueStatus": "pending",
                },
            ],
            "next_check_execution_history": [
                {
                    "timestamp": "2026-01-01T00:05:00Z",
                    "clusterLabel": "cluster-promote",
                    "candidateDescription": "Check node resource pressure",
                    "commandFamily": "kubectl-top",
                    "status": "success",
                    "durationMs": 620,
                    "artifactPath": "runs/health/external-analysis/run-promote-exec-0.json",
                    "timedOut": False,
                    "stdoutTruncated": False,
                    "stderrTruncated": False,
                    "outputBytesCaptured": 1840,
                    "resultClass": "useful-signal",
                    "resultSummary": "Captured node metrics showing memory pressure on node-1.",
                    "usefulnessClass": "useful",
                    "usefulnessSummary": "Found high memory pressure on node-1, elevated risk of OOM",
                    "suggestedNextOperatorMove": "Check kubelet logs for error details.",
                }
            ],
            "deterministic_next_checks": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 5,
            "p50_run_duration_seconds": 40,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": [
            {
                "label": "cluster-promote",
                "context": "cluster-promote",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-promote.json",
                    "assessment": "assessments/cluster-promote.json",
                    "drilldown": "drilldowns/cluster-promote.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-promote"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-promote",
            "context": "cluster-promote",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 2,
            "non_running_pods": 1,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {"pattern": "crashloop"},
            "artifact_path": "drilldowns/cluster-promote.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-promote",
            "context": "cluster-promote",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate node resources and kubelet logs",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-promote.json",
            "snapshot_path": "snapshots/cluster-promote.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-promote",
                    "context": "cluster-promote",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-promote.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_executed_result_deprioritizes_action() -> dict[str, object]:
    """Build a UI index with executed feedback that deprioritizes a prior action.

    Expected outcomes:
    - worklist: non-empty with executed/reviewed item
    - executed item has usefulnessClass: noisy (indicates deprioritization signal)
    - adaptationEffect: recommendation_deprioritized
    - adaptationSummary indicates a prior action was downgraded
    - itemState: reviewed

    Protects against: deprioritization signals not being surfaced honestly.
    """
    return {
        "run": {
            "run_id": "run-deprioritize",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 1,
                "successfulCalls": 1,
                "failedCalls": 0,
                "lastCallTimestamp": "2026-01-01T00:00:30Z",
                "p50LatencyMs": 450,
                "p95LatencyMs": 890,
                "p99LatencyMs": 1200,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-deprioritize-next-check-plan.json",
                "summary": "1 candidate.",
                "candidateCount": 1,
                "candidates": [
                    {
                        "description": "Check CNI errors",
                        "targetCluster": "cluster-deprioritize",
                        "sourceReason": "Network connectivity issues",
                        "expectedSignal": "CNI error messages",
                        "suggestedCommandFamily": "kubectl-logs",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "low",
                        "priorityLabel": "secondary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-cni",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "executed-success",
                        "outcomeStatus": "executed-success",
                        "latestArtifactPath": "runs/health/external-analysis/run-deprioritize-exec-0.json",
                        "latestTimestamp": "2026-01-01T00:05:00Z",
                        "targetContext": "cluster-deprioritize",
                        "commandPreview": "kubectl logs -n kube-system -l k8s-app=kube-cni --context cluster-deprioritize",
                    }
                ],
                "outcomeCounts": [{"status": "executed-success", "count": 1}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "1 candidate.",
                "artifactPath": "runs/health/external-analysis/run-deprioritize-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-cni",
                    "candidateIndex": 0,
                    "description": "Check CNI errors",
                    "targetCluster": "cluster-deprioritize",
                    "priorityLabel": "secondary",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "executed-success",
                    "outcomeStatus": "executed-success",
                    "latestArtifactPath": "runs/health/external-analysis/run-deprioritize-exec-0.json",
                    "sourceReason": "Network connectivity issues",
                    "expectedSignal": "CNI error messages",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-deprioritize",
                    "commandPreview": "kubectl logs -n kube-system -l k8s-app=kube-cni --context cluster-deprioritize",
                    "planArtifactPath": "runs/health/external-analysis/run-deprioritize-next-check-plan.json",
                    "queueStatus": "completed",
                    "usefulnessClass": "noisy",
                    "usefulnessSummary": "CNI logs show no errors; network issue not related to CNI",
                    "resultClass": "noisy-signal",
                    "resultSummary": "No CNI errors found; network issue may be elsewhere.",
                }
            ],
            "next_check_execution_history": [
                {
                    "timestamp": "2026-01-01T00:05:00Z",
                    "clusterLabel": "cluster-deprioritize",
                    "candidateDescription": "Check CNI errors",
                    "commandFamily": "kubectl-logs",
                    "status": "success",
                    "durationMs": 620,
                    "artifactPath": "runs/health/external-analysis/run-deprioritize-exec-0.json",
                    "timedOut": False,
                    "stdoutTruncated": False,
                    "stderrTruncated": False,
                    "outputBytesCaptured": 640,
                    "resultClass": "noisy-signal",
                    "resultSummary": "No CNI errors found; network issue may be elsewhere.",
                    "usefulnessClass": "noisy",
                    "usefulnessSummary": "CNI logs show no errors; network issue not related to CNI",
                    "suggestedNextOperatorMove": "Focus on pod-level network policies instead.",
                }
            ],
            "deterministic_next_checks": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 5,
            "p50_run_duration_seconds": 40,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": [
            {
                "label": "cluster-deprioritize",
                "context": "cluster-deprioritize",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-deprioritize.json",
                    "assessment": "assessments/cluster-deprioritize.json",
                    "drilldown": "drilldowns/cluster-deprioritize.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-deprioritize"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-deprioritize",
            "context": "cluster-deprioritize",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 2,
            "non_running_pods": 1,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {"pattern": "crashloop"},
            "artifact_path": "drilldowns/cluster-deprioritize.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-deprioritize",
            "context": "cluster-deprioritize",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate pod crash and network",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-deprioritize.json",
            "snapshot_path": "snapshots/cluster-deprioritize.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-deprioritize",
                    "context": "cluster-deprioritize",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-deprioritize.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_degraded_single_cluster() -> dict[str, object]:
    """Build a UI index for a degraded single-cluster run with missing evidence and worklist items.

    Expected outcomes:
    - status: degraded
    - title: "Degraded health detected in 1 cluster(s)"
    - facts: non-empty (health rating, trigger reasons, warning events, non-running pods)
    - inferences: non-empty (assessment hypotheses)
    - unknowns: non-empty (missing_evidence present)
    - staleEvidenceWarnings: empty (fresh freshness)
    - recommendedActions: non-empty
    - sourceArtifactRefs: real paths only, no "unknown"
    - worklist: non-empty with rank, title, reason, expectedEvidence, safetyNote, state

    Protects against:
    - missing evidence not surfaced
    - facts empty when they should be non-empty
    - recommended actions missing
    - fake "unknown" artifact paths
    """
    return {
        "run": {
            "run_id": "run-degraded",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 1,
            "external_analysis_count": 0,
            "notification_count": 1,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 0,
                "successfulCalls": 0,
                "failedCalls": 0,
                "lastCallTimestamp": None,
                "p50LatencyMs": None,
                "p95LatencyMs": None,
                "p99LatencyMs": None,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-degraded-next-check-plan.json",
                "summary": "1 next check candidate.",
                "candidateCount": 1,
                "candidates": [
                    {
                        "description": "Inspect pod logs for crashed container",
                        "targetCluster": "cluster-degraded",
                        "sourceReason": "CrashLoopBackOff investigation",
                        "expectedSignal": "Recent crash logs",
                        "suggestedCommandFamily": "kubectl-logs",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-logs",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "unexecuted",
                        "outcomeStatus": "unexecuted",
                        "latestArtifactPath": None,
                        "latestTimestamp": None,
                        "targetContext": "cluster-degraded · default",
                        "commandPreview": "kubectl logs pod/my-pod --context cluster-degraded",
                    }
                ],
                "outcomeCounts": [{"status": "unexecuted", "count": 1}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "1 next check candidate.",
                "artifactPath": "runs/health/external-analysis/run-degraded-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-logs",
                    "candidateIndex": 0,
                    "description": "Inspect pod logs for crashed container",
                    "targetCluster": "cluster-degraded",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "unexecuted",
                    "outcomeStatus": "unexecuted",
                    "latestArtifactPath": None,
                    "sourceReason": "CrashLoopBackOff investigation",
                    "expectedSignal": "Recent crash logs",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-degraded · default",
                    "commandPreview": "kubectl logs pod/my-pod --context cluster-degraded",
                    "planArtifactPath": "runs/health/external-analysis/run-degraded-next-check-plan.json",
                    "queueStatus": "pending",
                }
            ],
            "next_check_execution_history": [],
            "deterministic_next_checks": {
                "clusterCount": 1,
                "totalNextCheckCount": 1,
                "clusters": [
                    {
                        "label": "cluster-degraded",
                        "context": "cluster-degraded",
                        "topProblem": "crashloop",
                        "deterministicNextCheckCount": 1,
                        "deterministicNextCheckSummaries": [
                            {
                                "description": "Check pod events for CrashLoopBackOff",
                                "owner": "platform",
                                "method": "kubectl get events",
                                "evidenceNeeded": ["pod events", "restart count"],
                                "workstream": "incident",
                                "urgency": "high",
                                "isPrimaryTriage": True,
                                "whyNow": "CrashLoopBackOff detected on pod my-pod",
                            }
                        ],
                        "drilldownAvailable": True,
                        "assessmentArtifactPath": "assessments/cluster-degraded.json",
                        "drilldownArtifactPath": "drilldowns/cluster-degraded.json",
                    }
                ],
            },
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 2,
            "p50_run_duration_seconds": 40,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 60,
        },
        "clusters": [
            {
                "label": "cluster-degraded",
                "context": "cluster-degraded",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 5,
                "non_running_pods": 2,
                "baseline_policy_path": "policy.json",
                "missing_evidence": ["events"],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-degraded.json",
                    "assessment": "assessments/cluster-degraded.json",
                    "drilldown": "drilldowns/cluster-degraded.json",
                },
            }
        ],
        "proposals": [
            {
                "proposal_id": "p1",
                "target": "health.trigger_policy.warning_event_threshold",
                "status": "pending",
                "confidence": "medium",
                "rationale": "threshold too low",
                "expected_benefit": "less noise",
                "source_run_id": "run-degraded",
                "artifact_path": "proposals/p1.json",
                "review_artifact": "reviews/run-degraded-review.json",
                "lifecycle_history": [
                    {"status": "pending", "timestamp": "2026-01-01T00:00:00Z"}
                ],
            }
        ],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-degraded"],
        },
        "proposal_status_summary": {
            "status_counts": [{"status": "pending", "count": 1}]
        },
        "latest_drilldown": {
            "label": "cluster-degraded",
            "context": "cluster-degraded",
            "trigger_reasons": ["non_running_pods", "warning_event_threshold"],
            "warning_events": 5,
            "non_running_pods": 2,
            "summary": {"foo": "bar"},
            "rollout_status": ["stable"],
            "pattern_details": {"pattern": "crashloop"},
            "artifact_path": "drilldowns/cluster-degraded.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-degraded",
            "context": "cluster-degraded",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": ["events"],
            "findings": [
                {
                    "description": "crashloop detected",
                    "layer": "workload",
                    "supporting_signals": ["sig-1"],
                }
            ],
            "hypotheses": [
                {
                    "description": "Application misconfiguration causes repeated crashes",
                    "confidence": "medium",
                    "probable_layer": "workload",
                    "what_would_falsify": "Pod runs normally after config change",
                }
            ],
            "next_evidence_to_collect": [
                {
                    "description": "Check pod events for CrashLoopBackOff",
                    "owner": "platform",
                    "method": "kubectl get events",
                    "evidence_needed": ["pod events", "restart count"],
                }
            ],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate pod events and logs for my-pod",
                "references": ["assessments/cluster-degraded.json"],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-degraded.json",
            "snapshot_path": "snapshots/cluster-degraded.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-degraded",
                    "context": "cluster-degraded",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-degraded.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [
            {
                "kind": "degraded-health",
                "summary": "cluster degraded",
                "timestamp": "2026-01-01T00:00:00Z",
                "run_id": "run-degraded",
                "cluster_label": "cluster-degraded",
                "context": "cluster-degraded",
                "details": [{"label": "warnings", "value": "[1, 2, 3, 4, 5]"}],
                "artifact_path": "notifications/degraded-health.json",
            }
        ],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_stale_provider_enriched_degraded() -> dict[str, object]:
    """Build a UI index for a stale, degraded run with provider-assisted review enrichment.

    Expected outcomes:
    - status: degraded
    - title: "Degraded health detected in 1 cluster(s)"
    - facts: non-empty (deterministic assessment/drilldown facts)
    - inferences: non-empty (review enrichment summary must be here, not in facts)
    - unknowns: non-empty
    - staleEvidenceWarnings: non-empty ("Run freshness is stale" or "delayed")
    - recommendedActions: non-empty
    - sourceArtifactRefs: real paths only

    Critical invariant: provider-assisted review enrichment appears in inferences,
    NOT in facts.

    Protects against:
    - stale evidence silently hidden
    - provider-assisted content incorrectly classified as deterministic fact
    """
    index = _fixture_degraded_single_cluster()
    # Add provider-assisted review enrichment
    run_entry = cast(JsonObject, index["run"])
    run_entry["review_enrichment"] = {
        "status": "success",
        "provider": "llamacpp",
        "timestamp": "2026-01-01T00:05:00Z",
        "summary": "High ingress latency detected; consider scaling the gateway.",
        "triageOrder": ["cluster-degraded"],
        "topConcerns": ["ingress latency"],
        "evidenceGaps": ["CDN metrics"],
        "nextChecks": ["Collect ingress logs"],
        "focusNotes": ["Prioritize ingress investigation"],
        "artifactPath": "external-analysis/run-degraded-review-enrichment-llamacpp.json",
        "errorSummary": None,
        "skipReason": None,
    }
    run_entry["review_enrichment_config"] = {"enabled": True, "provider": "llamacpp"}
    # No need to update deterministic_next_checks; they already exist in degraded fixture
    return index


def _fixture_deterministic_only_no_command() -> dict[str, object]:
    """Build a UI index with deterministic next checks and no queue items.

    Expected outcomes:
    - worklist: non-empty items
    - each item: command is None (deterministic checks have method, not command)
    - each item: rank, title, workstream, reason, expectedEvidence, safetyNote present
    - counts: totalItems = len(items), completedItems = 0, pendingItems = count, blockedItems = 0

    Protects against: null command being converted to a fake runnable string.
    """
    return {
        "run": {
            "run_id": "run-deterministic-only",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 0,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 0,
                "successfulCalls": 0,
                "failedCalls": 0,
                "lastCallTimestamp": None,
                "p50LatencyMs": None,
                "p95LatencyMs": None,
                "p99LatencyMs": None,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": None,
            "planner_availability": None,
            "next_check_queue": [],
            "next_check_execution_history": [],
            "deterministic_next_checks": {
                "clusterCount": 1,
                "totalNextCheckCount": 2,
                "clusters": [
                    {
                        "label": "cluster-det",
                        "context": "cluster-det",
                        "topProblem": "unknown",
                        "deterministicNextCheckCount": 2,
                        "deterministicNextCheckSummaries": [
                            {
                                "description": "Collect node metrics for CPU pressure",
                                "owner": "platform",
                                "method": "kubectl top nodes",
                                "evidenceNeeded": ["cpu usage", "memory usage"],
                                "workstream": "incident",
                                "urgency": "medium",
                                "isPrimaryTriage": True,
                                "whyNow": "Unexplained latency spike",
                            },
                            {
                                "description": "Check for CNI errors",
                                "owner": "network",
                                "method": "kubectl logs -n kube-system -l k8s-app=kube-cni",
                                "evidenceNeeded": ["CNI logs", "error messages"],
                                "workstream": "network",
                                "urgency": "low",
                                "isPrimaryTriage": False,
                                "whyNow": "Potential network misconfiguration",
                            },
                        ],
                        "drilldownAvailable": True,
                        "assessmentArtifactPath": "assessments/cluster-det.json",
                        "drilldownArtifactPath": "drilldowns/cluster-det.json",
                    }
                ],
            },
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 30,
            "total_runs": 1,
            "p50_run_duration_seconds": 30,
            "p95_run_duration_seconds": 30,
            "p99_run_duration_seconds": 30,
        },
        "clusters": [
            {
                "label": "cluster-det",
                "context": "cluster-det",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 3,
                "non_running_pods": 0,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-det.json",
                    "assessment": "assessments/cluster-det.json",
                    "drilldown": "drilldowns/cluster-det.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-det"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-det",
            "context": "cluster-det",
            "trigger_reasons": ["warning_event_threshold"],
            "warning_events": 3,
            "non_running_pods": 0,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {},
            "artifact_path": "drilldowns/cluster-det.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-det",
            "context": "cluster-det",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Collect node and network diagnostics",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "infrastructure",
            "artifact_path": "assessments/cluster-det.json",
            "snapshot_path": "snapshots/cluster-det.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-det",
                    "context": "cluster-det",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-det.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_approval_needed_item() -> dict[str, object]:
    """Build a UI index with a queue item requiring operator approval.

    Expected outcomes:
    - worklist: non-empty with at least one approval-needed item
    - itemState: approval-needed
    - approvalState: approval-required
    - executionState: unexecuted
    - command is present (executable but blocked by approval)
    - sourceType: planner

    Protects against: approval gating not reflected in itemState.
    """
    return {
        "run": {
            "run_id": "run-approval-needed",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 0,
                "successfulCalls": 0,
                "failedCalls": 0,
                "lastCallTimestamp": None,
                "p50LatencyMs": None,
                "p95LatencyMs": None,
                "p99LatencyMs": None,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-approval-next-check-plan.json",
                "summary": "1 candidate requiring approval.",
                "candidateCount": 1,
                "candidates": [
                    {
                        "description": "Delete the failing pod to trigger restart",
                        "targetCluster": "cluster-approval",
                        "sourceReason": "Pod stuck in CrashLoopBackOff",
                        "expectedSignal": "Pod restarts successfully",
                        "suggestedCommandFamily": "kubectl-delete",
                        "safeToAutomate": False,
                        "requiresOperatorApproval": True,
                        "riskLevel": "medium",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": "mutation-detected",
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-delete",
                        "candidateIndex": 0,
                        "approvalStatus": "approval-required",
                        "approvalArtifactPath": None,
                        "approvalState": "approval-required",
                        "executionState": "unexecuted",
                        "outcomeStatus": "approval-required",
                        "latestArtifactPath": None,
                        "latestTimestamp": None,
                        "targetContext": "cluster-approval · default",
                        "commandPreview": "kubectl delete pod my-pod --context cluster-approval",
                    }
                ],
                "outcomeCounts": [{"status": "approval-required", "count": 1}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "1 candidate requiring approval.",
                "artifactPath": "runs/health/external-analysis/run-approval-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-delete",
                    "candidateIndex": 0,
                    "description": "Delete the failing pod to trigger restart",
                    "targetCluster": "cluster-approval",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-delete",
                    "safeToAutomate": False,
                    "requiresOperatorApproval": True,
                    "approvalState": "approval-required",
                    "executionState": "unexecuted",
                    "outcomeStatus": "approval-required",
                    "latestArtifactPath": None,
                    "sourceReason": "Pod stuck in CrashLoopBackOff",
                    "expectedSignal": "Pod restarts successfully",
                    "normalizationReason": "selection_label",
                    "safetyReason": "mutation-detected",
                    "approvalReason": "mutation-detected",
                    "duplicateReason": None,
                    "blockingReason": "awaiting-approval",
                    "targetContext": "cluster-approval · default",
                    "commandPreview": "kubectl delete pod my-pod --context cluster-approval",
                    "planArtifactPath": "runs/health/external-analysis/run-approval-next-check-plan.json",
                    "queueStatus": "approval-needed",
                }
            ],
            "next_check_execution_history": [],
            "deterministic_next_checks": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 1,
            "p50_run_duration_seconds": 45,
            "p95_run_duration_seconds": 45,
            "p99_run_duration_seconds": 45,
        },
        "clusters": [
            {
                "label": "cluster-approval",
                "context": "cluster-approval",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-approval.json",
                    "assessment": "assessments/cluster-approval.json",
                    "drilldown": "drilldowns/cluster-approval.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-approval"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-approval",
            "context": "cluster-approval",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 2,
            "non_running_pods": 1,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {},
            "artifact_path": "drilldowns/cluster-approval.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-approval",
            "context": "cluster-approval",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate failing pod",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-approval.json",
            "snapshot_path": "snapshots/cluster-approval.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-approval",
                    "context": "cluster-approval",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-approval.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_executed_with_usefulness() -> dict[str, object]:
    """Build a UI index with an executed item that has usefulness feedback.

    Expected outcomes:
    - worklist: non-empty with executed item
    - itemState: executed or reviewed
    - executionState: executed-success
    - usefulnessClass is present
    - sourceArtifactRefs includes execution artifact

    Protects against: usefulness feedback linkage not preserved.
    """
    return {
        "run": {
            "run_id": "run-executed-useful",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 0,
                "successfulCalls": 0,
                "failedCalls": 0,
                "lastCallTimestamp": None,
                "p50LatencyMs": None,
                "p95LatencyMs": None,
                "p99LatencyMs": None,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-exec-next-check-plan.json",
                "summary": "1 executed candidate.",
                "candidateCount": 1,
                "candidates": [
                    {
                        "description": "Check pod events for CrashLoopBackOff",
                        "targetCluster": "cluster-exec",
                        "sourceReason": "CrashLoopBackOff investigation",
                        "expectedSignal": "Recent crash events",
                        "suggestedCommandFamily": "kubectl-get",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-events",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "executed-success",
                        "outcomeStatus": "executed-success",
                        "latestArtifactPath": "runs/health/external-analysis/run-exec-next-check-execution-0.json",
                        "latestTimestamp": "2026-01-01T00:10:00Z",
                        "targetContext": "cluster-exec · default",
                        "commandPreview": "kubectl get events --context cluster-exec",
                    }
                ],
                "outcomeCounts": [{"status": "executed-success", "count": 1}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "1 executed candidate.",
                "artifactPath": "runs/health/external-analysis/run-exec-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-events",
                    "candidateIndex": 0,
                    "description": "Check pod events for CrashLoopBackOff",
                    "targetCluster": "cluster-exec",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-get",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "executed-success",
                    "outcomeStatus": "executed-success",
                    "latestArtifactPath": "runs/health/external-analysis/run-exec-next-check-execution-0.json",
                    "sourceReason": "CrashLoopBackOff investigation",
                    "expectedSignal": "Recent crash events",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-exec · default",
                    "commandPreview": "kubectl get events --context cluster-exec",
                    "planArtifactPath": "runs/health/external-analysis/run-exec-next-check-plan.json",
                    "queueStatus": "completed",
                }
            ],
            "next_check_execution_history": [
                {
                    "timestamp": "2026-01-01T00:10:00Z",
                    "clusterLabel": "cluster-exec",
                    "candidateDescription": "Check pod events for CrashLoopBackOff",
                    "commandFamily": "kubectl-get",
                    "status": "success",
                    "durationMs": 840,
                    "artifactPath": "runs/health/external-analysis/run-exec-next-check-execution-0.json",
                    "timedOut": False,
                    "stdoutTruncated": False,
                    "stderrTruncated": False,
                    "outputBytesCaptured": 2048,
                    "resultClass": "useful-signal",
                    "resultSummary": "Captured pod events showing repeated crash restarts.",
                    "usefulnessClass": "useful",
                    "usefulnessSummary": "Found key crash events",
                    "suggestedNextOperatorMove": "Correlate with pod logs to identify root cause.",
                }
            ],
            "deterministic_next_checks": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 1,
            "p50_run_duration_seconds": 45,
            "p95_run_duration_seconds": 45,
            "p99_run_duration_seconds": 45,
        },
        "clusters": [
            {
                "label": "cluster-exec",
                "context": "cluster-exec",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-exec.json",
                    "assessment": "assessments/cluster-exec.json",
                    "drilldown": "drilldowns/cluster-exec.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-exec"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-exec",
            "context": "cluster-exec",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 2,
            "non_running_pods": 1,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {},
            "artifact_path": "drilldowns/cluster-exec.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-exec",
            "context": "cluster-exec",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate failing pod",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-exec.json",
            "snapshot_path": "snapshots/cluster-exec.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-exec",
                    "context": "cluster-exec",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-exec.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_duplicate_candidates() -> dict[str, object]:
    """Build a UI index with duplicate candidates from multiple sources.

    Expected outcomes:
    - worklist: items with mergedSources when duplicates detected
    - deterministic item enriched with planner provenance when IDs match
    - sourceType reflects merged provenance

    Protects against: duplicate handling losing provenance.
    """
    return {
        "run": {
            "run_id": "run-duplicate",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 0,
                "successfulCalls": 0,
                "failedCalls": 0,
                "lastCallTimestamp": None,
                "p50LatencyMs": None,
                "p95LatencyMs": None,
                "p99LatencyMs": None,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-dup-next-check-plan.json",
                "summary": "1 candidate.",
                "candidateCount": 1,
                "candidates": [
                    {
                        "description": "Check pod events for CrashLoopBackOff",
                        "targetCluster": "cluster-dup",
                        "sourceReason": "CrashLoopBackOff investigation",
                        "expectedSignal": "Recent crash events",
                        "suggestedCommandFamily": "kubectl-get",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        # Use candidate ID that matches deterministic ID pattern
                        "candidateId": "candidate-logs",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "unexecuted",
                        "outcomeStatus": "unexecuted",
                        "latestArtifactPath": None,
                        "latestTimestamp": None,
                        "targetContext": "cluster-dup · default",
                        "commandPreview": "kubectl get events --context cluster-dup",
                    }
                ],
                "outcomeCounts": [{"status": "unexecuted", "count": 1}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "1 candidate.",
                "artifactPath": "runs/health/external-analysis/run-dup-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-logs",
                    "candidateIndex": 0,
                    "description": "Check pod events for CrashLoopBackOff",
                    "targetCluster": "cluster-dup",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-get",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "unexecuted",
                    "outcomeStatus": "unexecuted",
                    "latestArtifactPath": None,
                    "sourceReason": "CrashLoopBackOff investigation",
                    "expectedSignal": "Recent crash events",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-dup · default",
                    "commandPreview": "kubectl get events --context cluster-dup",
                    "planArtifactPath": "runs/health/external-analysis/run-dup-next-check-plan.json",
                    "queueStatus": "pending",
                }
            ],
            "next_check_execution_history": [],
            # Deterministic next checks with same description (duplicate candidate)
            "deterministic_next_checks": {
                "clusterCount": 1,
                "totalNextCheckCount": 1,
                "clusters": [
                    {
                        "label": "cluster-dup",
                        "context": "cluster-dup",
                        "topProblem": "crashloop",
                        "deterministicNextCheckCount": 1,
                        "deterministicNextCheckSummaries": [
                            {
                                "description": "Check pod events for CrashLoopBackOff",
                                "owner": "platform",
                                "method": "kubectl get events",
                                "evidenceNeeded": ["pod events", "restart count"],
                                "workstream": "incident",
                                "urgency": "high",
                                "isPrimaryTriage": True,
                                "whyNow": "CrashLoopBackOff detected on pod my-pod",
                            }
                        ],
                        "drilldownAvailable": True,
                        "assessmentArtifactPath": "assessments/cluster-dup.json",
                        "drilldownArtifactPath": "drilldowns/cluster-dup.json",
                    }
                ],
            },
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 1,
            "p50_run_duration_seconds": 45,
            "p95_run_duration_seconds": 45,
            "p99_run_duration_seconds": 45,
        },
        "clusters": [
            {
                "label": "cluster-dup",
                "context": "cluster-dup",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-dup.json",
                    "assessment": "assessments/cluster-dup.json",
                    "drilldown": "drilldowns/cluster-dup.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-dup"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-dup",
            "context": "cluster-dup",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 2,
            "non_running_pods": 1,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {},
            "artifact_path": "drilldowns/cluster-dup.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-dup",
            "context": "cluster-dup",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate failing pod",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-dup.json",
            "snapshot_path": "snapshots/cluster-dup.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-dup",
                    "context": "cluster-dup",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-dup.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_queue_with_command() -> dict[str, object]:
    """Build a UI index with a queue item that has an executable command.

    Expected outcomes:
    - worklist: non-empty with at least one queue item
    - queue item: command is populated (not None)
    - queue item: targetCluster, targetContext, reason, expectedEvidence,
      safetyNote, approvalState, executionState, feedbackState all present
    - queue item: sourceArtifactRefs non-empty
    - queue item: itemState is queued, sourceType is planner

    Protects against: queue items missing required metadata fields.
    """
    return {
        "run": {
            "run_id": "run-queue-cmd",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 1,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 0,
                "successfulCalls": 0,
                "failedCalls": 0,
                "lastCallTimestamp": None,
                "p50LatencyMs": None,
                "p95LatencyMs": None,
                "p99LatencyMs": None,
                "providerBreakdown": [],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-queue-cmd-next-check-plan.json",
                "summary": "1 next check candidate.",
                "candidateCount": 1,
                "candidates": [
                    {
                        "description": "Collect kubelet logs for control-plane pods",
                        "targetCluster": "cluster-cmd",
                        "sourceReason": "CrashLoopBackOff investigation",
                        "expectedSignal": "Recent kubelet errors around control-plane pod restarts",
                        "suggestedCommandFamily": "kubectl-logs",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "medium",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-logs",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "executed-success",
                        "outcomeStatus": "executed-success",
                        "latestArtifactPath": "runs/health/external-analysis/run-queue-cmd-next-check-execution-0.json",
                        "latestTimestamp": "2026-01-01T00:10:00Z",
                        "targetContext": "cluster-cmd · control-plane pods",
                        "commandPreview": "kubectl logs deployment/control-plane --context cluster-cmd",
                    }
                ],
                "outcomeCounts": [{"status": "executed-success", "count": 1}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "1 next check candidate.",
                "artifactPath": "runs/health/external-analysis/run-queue-cmd-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-logs",
                    "candidateIndex": 0,
                    "description": "Collect kubelet logs for control-plane pods",
                    "targetCluster": "cluster-cmd",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "executed-success",
                    "outcomeStatus": "executed-success",
                    "latestArtifactPath": "runs/health/external-analysis/run-queue-cmd-next-check-execution-0.json",
                    "sourceReason": "CrashLoopBackOff investigation",
                    "expectedSignal": "Recent kubelet errors around control-plane pod restarts",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-cmd · control-plane pods",
                    "commandPreview": "kubectl logs deployment/control-plane --context cluster-cmd",
                    "planArtifactPath": "runs/health/external-analysis/run-queue-cmd-next-check-plan.json",
                    "queueStatus": "completed",
                    "failureClass": None,
                    "failureSummary": None,
                    "suggestedNextOperatorMove": None,
                }
            ],
            "next_check_execution_history": [
                {
                    "timestamp": "2026-01-01T00:10:00Z",
                    "clusterLabel": "cluster-cmd",
                    "candidateDescription": "Collect kubelet logs for control-plane pods",
                    "commandFamily": "kubectl-logs",
                    "status": "success",
                    "durationMs": 1840,
                    "artifactPath": "runs/health/external-analysis/run-queue-cmd-next-check-execution-0.json",
                    "timedOut": False,
                    "stdoutTruncated": False,
                    "stderrTruncated": False,
                    "outputBytesCaptured": 1240,
                    "resultClass": "useful-signal",
                    "resultSummary": "Captured control-plane logs that highlight recent kubelet errors.",
                    "suggestedNextOperatorMove": "Correlate this output with the target incident.",
                }
            ],
            "deterministic_next_checks": None,
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 1,
            "p50_run_duration_seconds": 45,
            "p95_run_duration_seconds": 45,
            "p99_run_duration_seconds": 45,
        },
        "clusters": [
            {
                "label": "cluster-cmd",
                "context": "cluster-cmd",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-cmd.json",
                    "assessment": "assessments/cluster-cmd.json",
                    "drilldown": "drilldowns/cluster-cmd.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-cmd"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-cmd",
            "context": "cluster-cmd",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 2,
            "non_running_pods": 1,
            "summary": {},
            "rollout_status": [],
            "pattern_details": {},
            "artifact_path": "drilldowns/cluster-cmd.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-cmd",
            "context": "cluster-cmd",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Collect kubelet logs",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-cmd.json",
            "snapshot_path": "snapshots/cluster-cmd.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-cmd",
                    "context": "cluster-cmd",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-cmd.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {"count": 1, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


# =============================================================================
# MULTI-SIGNAL FIXTURES (BETA-G1)
# =============================================================================


def _fixture_multi_signal_warnings_pods_missing() -> dict[str, object]:
    """Build a UI index combining warning events + non-running pods + missing evidence.

    This fixture tests the incident report's ability to handle multiple simultaneous
    signals that would commonly occur in a real operational scenario.

    Expected outcomes:
    - status: degraded
    - facts: non-empty (trigger_reasons includes both warning_event_threshold AND non_running_pods)
    - facts: non-empty (warning_events count, non_running_pods count)
    - unknowns: non-empty (events missing)
    - derived: non-empty (health rating)
    - inferences: non-empty (hypothesis with basis)
    - recommendations: non-empty
    - worklist: non-empty (deterministic + queue items)
    - staleEvidenceWarnings: empty (fresh freshness)

    Protects against: multi-signal scenarios breaking claim separation or unknown surfacing.
    """
    return {
        "run": {
            "run_id": "run-multi-signal",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 1,
            "external_analysis_count": 1,
            "notification_count": 1,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 1,
                "successfulCalls": 1,
                "failedCalls": 0,
                "lastCallTimestamp": "2026-01-01T00:00:30Z",
                "p50LatencyMs": 450,
                "p95LatencyMs": 890,
                "p99LatencyMs": 1200,
                "providerBreakdown": [{"provider": "llamacpp", "calls": 1}],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-multi-next-check-plan.json",
                "summary": "2 next check candidates.",
                "candidateCount": 2,
                "candidates": [
                    {
                        "description": "Inspect pod logs for crashed container",
                        "targetCluster": "cluster-multi",
                        "sourceReason": "CrashLoopBackOff + OOMKilled detected",
                        "expectedSignal": "Recent crash logs with exit codes",
                        "suggestedCommandFamily": "kubectl-logs",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-logs",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "unexecuted",
                        "outcomeStatus": "unexecuted",
                        "latestArtifactPath": None,
                        "latestTimestamp": None,
                        "targetContext": "cluster-multi · default",
                        "commandPreview": "kubectl logs pod/my-pod --container main --context cluster-multi",
                    },
                    {
                        "description": "Check node resource pressure",
                        "targetCluster": "cluster-multi",
                        "sourceReason": "Multiple pods affected, possible node pressure",
                        "expectedSignal": "Node allocatable resources, current usage",
                        "suggestedCommandFamily": "kubectl-top",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "medium",
                        "priorityLabel": "secondary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-nodes",
                        "candidateIndex": 1,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "unexecuted",
                        "outcomeStatus": "unexecuted",
                        "latestArtifactPath": None,
                        "latestTimestamp": None,
                        "targetContext": "cluster-multi",
                        "commandPreview": "kubectl top nodes --context cluster-multi",
                    },
                ],
                "outcomeCounts": [{"status": "unexecuted", "count": 2}],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "2 next check candidates.",
                "artifactPath": "runs/health/external-analysis/run-multi-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-logs",
                    "candidateIndex": 0,
                    "description": "Inspect pod logs for crashed container",
                    "targetCluster": "cluster-multi",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "unexecuted",
                    "outcomeStatus": "unexecuted",
                    "latestArtifactPath": None,
                    "sourceReason": "CrashLoopBackOff + OOMKilled detected",
                    "expectedSignal": "Recent crash logs with exit codes",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-multi · default",
                    "commandPreview": "kubectl logs pod/my-pod --container main --context cluster-multi",
                    "planArtifactPath": "runs/health/external-analysis/run-multi-next-check-plan.json",
                    "queueStatus": "pending",
                },
                {
                    "candidateId": "candidate-nodes",
                    "candidateIndex": 1,
                    "description": "Check node resource pressure",
                    "targetCluster": "cluster-multi",
                    "priorityLabel": "secondary",
                    "suggestedCommandFamily": "kubectl-top",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "unexecuted",
                    "outcomeStatus": "unexecuted",
                    "latestArtifactPath": None,
                    "sourceReason": "Multiple pods affected, possible node pressure",
                    "expectedSignal": "Node allocatable resources, current usage",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-multi",
                    "commandPreview": "kubectl top nodes --context cluster-multi",
                    "planArtifactPath": "runs/health/external-analysis/run-multi-next-check-plan.json",
                    "queueStatus": "pending",
                },
            ],
            "next_check_execution_history": [],
            "deterministic_next_checks": {
                "clusterCount": 1,
                "totalNextCheckCount": 2,
                "clusters": [
                    {
                        "label": "cluster-multi",
                        "context": "cluster-multi",
                        "topProblem": "crashloop",
                        "deterministicNextCheckCount": 2,
                        "deterministicNextCheckSummaries": [
                            {
                                "description": "Check pod events for CrashLoopBackOff",
                                "owner": "platform",
                                "method": "kubectl get events",
                                "evidenceNeeded": ["pod events", "restart count", "exit codes"],
                                "workstream": "incident",
                                "urgency": "high",
                                "isPrimaryTriage": True,
                                "whyNow": "CrashLoopBackOff detected on 2 pods, OOMKilled on 1",
                            },
                            {
                                "description": "Check node resource availability",
                                "owner": "platform",
                                "method": "kubectl describe nodes",
                                "evidenceNeeded": ["allocatable resources", "memory pressure", "disk pressure"],
                                "workstream": "incident",
                                "urgency": "medium",
                                "isPrimaryTriage": False,
                                "whyNow": "Multiple pods affected simultaneously",
                            },
                        ],
                        "drilldownAvailable": True,
                        "assessmentArtifactPath": "assessments/cluster-multi.json",
                        "drilldownArtifactPath": "drilldowns/cluster-multi.json",
                    }
                ],
            },
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 60,
            "total_runs": 5,
            "p50_run_duration_seconds": 55,
            "p95_run_duration_seconds": 70,
            "p99_run_duration_seconds": 85,
        },
        "clusters": [
            {
                "label": "cluster-multi",
                "context": "cluster-multi",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 5,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 8,
                "non_running_pods": 3,
                "baseline_policy_path": "policy.json",
                "missing_evidence": ["events", "pod_logs"],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-multi.json",
                    "assessment": "assessments/cluster-multi.json",
                    "drilldown": "drilldowns/cluster-multi.json",
                },
            }
        ],
        "proposals": [
            {
                "proposal_id": "p-multi-1",
                "target": "health.trigger_policy.warning_event_threshold",
                "status": "pending",
                "confidence": "medium",
                "rationale": "threshold may be too sensitive for baseline warnings",
                "expected_benefit": "reduce noise from non-critical warnings",
                "source_run_id": "run-multi-signal",
                "artifact_path": "proposals/p-multi-1.json",
                "review_artifact": "reviews/run-multi-review.json",
                "lifecycle_history": [
                    {"status": "pending", "timestamp": "2026-01-01T00:00:00Z"}
                ],
            },
            {
                "proposal_id": "p-multi-2",
                "target": "health.trigger_policy.non_running_pod_threshold",
                "status": "pending",
                "confidence": "medium",
                "rationale": "threshold too low for production workload",
                "expected_benefit": "focus on actionable pod failures",
                "source_run_id": "run-multi-signal",
                "artifact_path": "proposals/p-multi-2.json",
                "review_artifact": "reviews/run-multi-review.json",
                "lifecycle_history": [
                    {"status": "pending", "timestamp": "2026-01-01T00:00:00Z"}
                ],
            },
        ],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-multi"],
        },
        "proposal_status_summary": {
            "status_counts": [{"status": "pending", "count": 2}]
        },
        "latest_drilldown": {
            "label": "cluster-multi",
            "context": "cluster-multi",
            "trigger_reasons": ["non_running_pods", "warning_event_threshold"],
            "warning_events": 8,
            "non_running_pods": 3,
            "summary": {"pods_affected": ["pod-a", "pod-b", "pod-c"], "patterns": ["crashloop", "oomkilled"]},
            "rollout_status": ["stable"],
            "pattern_details": {"pattern": "crashloop", "confidence": "high"},
            "artifact_path": "drilldowns/cluster-multi.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-multi",
            "context": "cluster-multi",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": ["events", "pod_logs"],
            "findings": [
                {
                    "description": "Multiple pods in CrashLoopBackOff or terminated state",
                    "layer": "workload",
                    "supporting_signals": ["sig-1", "sig-2"],
                },
                {
                    "description": "Elevated warning event rate indicates systemic issue",
                    "layer": "control-plane",
                    "supporting_signals": ["sig-3"],
                },
            ],
            "hypotheses": [
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
            ],
            "next_evidence_to_collect": [
                {
                    "description": "Check pod events for CrashLoopBackOff details",
                    "owner": "platform",
                    "method": "kubectl get events",
                    "evidence_needed": ["pod events", "restart count", "exit codes"],
                },
                {
                    "description": "Describe nodes to check allocatable resources",
                    "owner": "platform",
                    "method": "kubectl describe nodes",
                    "evidence_needed": ["allocatable", "memory", "conditions"],
                },
            ],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate pod events and node resources; check for memory pressure",
                "references": ["assessments/cluster-multi.json", "drilldowns/cluster-multi.json"],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-multi.json",
            "snapshot_path": "snapshots/cluster-multi.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-multi",
                    "context": "cluster-multi",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-multi.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [
            {
                "kind": "degraded-health",
                "summary": "cluster multi-signal degraded",
                "timestamp": "2026-01-01T00:00:00Z",
                "run_id": "run-multi-signal",
                "cluster_label": "cluster-multi",
                "context": "cluster-multi",
                "details": [
                    {"label": "warnings", "value": 8},
                    {"label": "non_running_pods", "value": 3},
                ],
                "artifact_path": "notifications/multi-signal.json",
            }
        ],
        "external_analysis": {
            "count": 1,
            "status_counts": [{"status": "success", "count": 1}],
            "artifacts": ["runs/health/external-analysis/run-multi-llamacpp.json"],
        },
        "auto_drilldown_interpretations": {},
    }


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


def _fixture_multi_signal_executed_with_pending() -> dict[str, object]:
    """Build a UI index with executed/reviewed items coexisting with pending items.

    This fixture tests the worklist's ability to handle mixed execution states:
    - Some items executed and reviewed
    - Some items pending execution
    - Deterministic items present alongside queue items

    Expected outcomes:
    - worklist: non-empty with mixed itemStates
    - at least one item with itemState=executed or reviewed
    - at least one item with itemState=queued or advisory
    - executed items have usefulness feedback preserved
    - pending items have appropriate state tracking

    Protects against: execution state not being preserved or mixed states confusing ranking.
    """
    return {
        "run": {
            "run_id": "run-mixed-exec",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 0,
            "external_analysis_count": 2,
            "notification_count": 0,
            "scheduler_interval_seconds": 300,
            "llm_stats": {
                "totalCalls": 1,
                "successfulCalls": 1,
                "failedCalls": 0,
                "lastCallTimestamp": "2026-01-01T00:00:30Z",
                "p50LatencyMs": 450,
                "p95LatencyMs": 890,
                "p99LatencyMs": 1200,
                "providerBreakdown": [{"provider": "llamacpp", "calls": 1}],
                "scope": "current_run",
            },
            "llm_activity": {"entries": [], "summary": {"retained_entries": 0}},
            "llm_policy": None,
            "review_enrichment": None,
            "review_enrichment_status": None,
            "provider_execution": None,
            "auto_drilldown_config": None,
            "review_enrichment_config": None,
            "next_check_plan": {
                "artifactPath": "runs/health/external-analysis/run-mixed-next-check-plan.json",
                "summary": "3 next check candidates (1 executed, 2 pending).",
                "candidateCount": 3,
                "candidates": [
                    {
                        "description": "Check pod events for CrashLoopBackOff",
                        "targetCluster": "cluster-mixed",
                        "sourceReason": "CrashLoopBackOff detected on primary pod",
                        "expectedSignal": "Recent crash events with exit codes",
                        "suggestedCommandFamily": "kubectl-get",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-events",
                        "candidateIndex": 0,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "executed-success",
                        "outcomeStatus": "executed-success",
                        "latestArtifactPath": "runs/health/external-analysis/run-mixed-exec-0.json",
                        "latestTimestamp": "2026-01-01T00:05:00Z",
                        "targetContext": "cluster-mixed · default",
                        "commandPreview": "kubectl get events --context cluster-mixed",
                    },
                    {
                        "description": "Inspect pod logs for detailed crash information",
                        "targetCluster": "cluster-mixed",
                        "sourceReason": "Events show crash, need logs for exit code",
                        "expectedSignal": "Crash logs with OOM or signal exit codes",
                        "suggestedCommandFamily": "kubectl-logs",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "high",
                        "priorityLabel": "primary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-logs",
                        "candidateIndex": 1,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "unexecuted",
                        "outcomeStatus": "unexecuted",
                        "latestArtifactPath": None,
                        "latestTimestamp": None,
                        "targetContext": "cluster-mixed · default",
                        "commandPreview": "kubectl logs pod/my-pod --context cluster-mixed",
                    },
                    {
                        "description": "Check node resource pressure",
                        "targetCluster": "cluster-mixed",
                        "sourceReason": "Multiple pods affected, possible node pressure",
                        "expectedSignal": "Node allocatable and current usage",
                        "suggestedCommandFamily": "kubectl-top",
                        "safeToAutomate": True,
                        "requiresOperatorApproval": False,
                        "riskLevel": "low",
                        "estimatedCost": "low",
                        "confidence": "medium",
                        "priorityLabel": "secondary",
                        "gatingReason": None,
                        "duplicateOfExistingEvidence": False,
                        "candidateId": "candidate-nodes",
                        "candidateIndex": 2,
                        "approvalStatus": "not-required",
                        "approvalArtifactPath": None,
                        "approvalState": "not-required",
                        "executionState": "unexecuted",
                        "outcomeStatus": "unexecuted",
                        "latestArtifactPath": None,
                        "latestTimestamp": None,
                        "targetContext": "cluster-mixed",
                        "commandPreview": "kubectl top nodes --context cluster-mixed",
                    },
                ],
                "outcomeCounts": [
                    {"status": "executed-success", "count": 1},
                    {"status": "unexecuted", "count": 2},
                ],
                "orphanedApprovalCount": 0,
                "orphanedApprovals": [],
            },
            "planner_availability": {
                "status": "planner-present",
                "reason": "3 candidates (1 executed, 2 pending).",
                "artifactPath": "runs/health/external-analysis/run-mixed-next-check-plan.json",
            },
            "next_check_queue": [
                {
                    "candidateId": "candidate-events",
                    "candidateIndex": 0,
                    "description": "Check pod events for CrashLoopBackOff",
                    "targetCluster": "cluster-mixed",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-get",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "executed-success",
                    "outcomeStatus": "executed-success",
                    "latestArtifactPath": "runs/health/external-analysis/run-mixed-exec-0.json",
                    "sourceReason": "CrashLoopBackOff detected on primary pod",
                    "expectedSignal": "Recent crash events with exit codes",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-mixed · default",
                    "commandPreview": "kubectl get events --context cluster-mixed",
                    "planArtifactPath": "runs/health/external-analysis/run-mixed-next-check-plan.json",
                    "queueStatus": "completed",
                    "usefulnessClass": "useful",
                    "usefulnessSummary": "Found crash events showing OOMKilled",
                    "suggestedNextOperatorMove": "Check pod logs for detailed exit information",
                },
                {
                    "candidateId": "candidate-logs",
                    "candidateIndex": 1,
                    "description": "Inspect pod logs for detailed crash information",
                    "targetCluster": "cluster-mixed",
                    "priorityLabel": "primary",
                    "suggestedCommandFamily": "kubectl-logs",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "unexecuted",
                    "outcomeStatus": "unexecuted",
                    "latestArtifactPath": None,
                    "sourceReason": "Events show crash, need logs for exit code",
                    "expectedSignal": "Crash logs with OOM or signal exit codes",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-mixed · default",
                    "commandPreview": "kubectl logs pod/my-pod --context cluster-mixed",
                    "planArtifactPath": "runs/health/external-analysis/run-mixed-next-check-plan.json",
                    "queueStatus": "pending",
                },
                {
                    "candidateId": "candidate-nodes",
                    "candidateIndex": 2,
                    "description": "Check node resource pressure",
                    "targetCluster": "cluster-mixed",
                    "priorityLabel": "secondary",
                    "suggestedCommandFamily": "kubectl-top",
                    "safeToAutomate": True,
                    "requiresOperatorApproval": False,
                    "approvalState": "not-required",
                    "executionState": "unexecuted",
                    "outcomeStatus": "unexecuted",
                    "latestArtifactPath": None,
                    "sourceReason": "Multiple pods affected, possible node pressure",
                    "expectedSignal": "Node allocatable and current usage",
                    "normalizationReason": "selection_label",
                    "safetyReason": "known_command",
                    "approvalReason": None,
                    "duplicateReason": None,
                    "blockingReason": None,
                    "targetContext": "cluster-mixed",
                    "commandPreview": "kubectl top nodes --context cluster-mixed",
                    "planArtifactPath": "runs/health/external-analysis/run-mixed-next-check-plan.json",
                    "queueStatus": "pending",
                },
            ],
            "next_check_execution_history": [
                {
                    "timestamp": "2026-01-01T00:05:00Z",
                    "clusterLabel": "cluster-mixed",
                    "candidateDescription": "Check pod events for CrashLoopBackOff",
                    "commandFamily": "kubectl-get",
                    "status": "success",
                    "durationMs": 620,
                    "artifactPath": "runs/health/external-analysis/run-mixed-exec-0.json",
                    "timedOut": False,
                    "stdoutTruncated": False,
                    "stderrTruncated": False,
                    "outputBytesCaptured": 1840,
                    "resultClass": "useful-signal",
                    "resultSummary": "Captured pod events showing OOMKilled exit codes.",
                    "usefulnessClass": "useful",
                    "usefulnessSummary": "Found crash events showing OOMKilled",
                    "suggestedNextOperatorMove": "Check pod logs for detailed exit information",
                }
            ],
            "deterministic_next_checks": {
                "clusterCount": 1,
                "totalNextCheckCount": 2,
                "clusters": [
                    {
                        "label": "cluster-mixed",
                        "context": "cluster-mixed",
                        "topProblem": "crashloop",
                        "deterministicNextCheckCount": 2,
                        "deterministicNextCheckSummaries": [
                            {
                                "description": "Check pod events for CrashLoopBackOff",
                                "owner": "platform",
                                "method": "kubectl get events",
                                "evidenceNeeded": ["pod events", "restart count", "exit codes"],
                                "workstream": "incident",
                                "urgency": "high",
                                "isPrimaryTriage": True,
                                "whyNow": "CrashLoopBackOff detected on primary pod",
                            },
                            {
                                "description": "Check node resource availability",
                                "owner": "platform",
                                "method": "kubectl describe nodes",
                                "evidenceNeeded": ["allocatable resources", "memory pressure"],
                                "workstream": "incident",
                                "urgency": "medium",
                                "isPrimaryTriage": False,
                                "whyNow": "Multiple pods affected, potential node pressure",
                            },
                        ],
                        "drilldownAvailable": True,
                        "assessmentArtifactPath": "assessments/cluster-mixed.json",
                        "drilldownArtifactPath": "drilldowns/cluster-mixed.json",
                    }
                ],
            },
            "diagnostic_pack_review": None,
            "diagnostic_pack": None,
        },
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 5,
            "p50_run_duration_seconds": 40,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": [
            {
                "label": "cluster-mixed",
                "context": "cluster-mixed",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 3,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-mixed.json",
                    "assessment": "assessments/cluster-mixed.json",
                    "drilldown": "drilldowns/cluster-mixed.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-mixed"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-mixed",
            "context": "cluster-mixed",
            "trigger_reasons": ["non_running_pods"],
            "warning_events": 3,
            "non_running_pods": 1,
            "summary": {"pods_affected": ["pod-a"], "patterns": ["crashloop"]},
            "rollout_status": [],
            "pattern_details": {"pattern": "crashloop"},
            "artifact_path": "drilldowns/cluster-mixed.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-mixed",
            "context": "cluster-mixed",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate pod crash logs and node resources",
                "references": [],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/cluster-mixed.json",
            "snapshot_path": "snapshots/cluster-mixed.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-mixed",
                    "context": "cluster-mixed",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-mixed.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [],
        "external_analysis": {
            "count": 2,
            "status_counts": [{"status": "success", "count": 2}],
            "artifacts": [],
        },
        "auto_drilldown_interpretations": {},
    }
