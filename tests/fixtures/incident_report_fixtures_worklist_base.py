"""Deterministic fixture helpers for operator worklist quality tests.

Fixtures:
- _fixture_deterministic_only_no_command: deterministic next checks, no queue items
"""

from __future__ import annotations


def _fixture_deterministic_only_no_command() -> dict[str, object]:
    """Build a UI index with deterministic next checks and no queue items."""
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
