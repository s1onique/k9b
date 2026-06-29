"""Golden fixture helpers for incident report quality tests.

This module provides core report fixtures for testing the incidentReport payload builder.

Fixtures:
- _fixture_healthy_no_incident: healthy run with no degraded clusters
- _fixture_degraded_single_cluster: degraded single-cluster run with missing evidence and worklist items
- _fixture_stale_provider_enriched_degraded: stale, degraded run with provider-assisted review enrichment
"""

from __future__ import annotations

from typing import TypeAlias, cast

from tests.fixtures.incident_report_fixtures_base import JsonObject

JsonDict: TypeAlias = dict[str, object]


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
    return index
