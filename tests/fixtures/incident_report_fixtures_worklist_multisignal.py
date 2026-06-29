"""Worklist multi-signal fixture helpers for operator worklist quality tests.

Fixtures:
- _fixture_multi_signal_warnings_pods_missing: multi-signal with warnings + missing pods
"""

from __future__ import annotations


def _fixture_multi_signal_warnings_pods_missing() -> dict[str, object]:
    """Build a UI index with multiple signals: warnings and missing pods."""
    return {
        "run": {
            "run_id": "run-multi-signal",
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
                "label": "cluster-multi",
                "context": "cluster-multi",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 5,
                "non_running_pods": 3,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-multi.json",
                    "assessment": "assessments/cluster-multi.json",
                    "drilldown": "drilldowns/cluster-multi.json",
                },
            }
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-multi"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "cluster-multi",
            "context": "cluster-multi",
            "trigger_reasons": ["non_running_pods", "warning_event_threshold"],
            "warning_events": 5,
            "non_running_pods": 3,
            "summary": {"pods_affected": ["pod-a", "pod-b", "pod-c"]},
            "rollout_status": [],
            "pattern_details": {},
            "artifact_path": "drilldowns/cluster-multi.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-multi",
            "context": "cluster-multi",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": {
                "type": "observation",
                "description": "Investigate non-running pods",
                "references": [],
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
        "notification_history": [],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }
