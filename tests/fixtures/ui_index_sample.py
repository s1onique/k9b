from collections.abc import Mapping


def sample_ui_index() -> Mapping[str, object]:
    return {
        "run": {
            "run_id": "run-1",
            "run_label": "health-run",
            "timestamp": "2026-01-01T00:00:00Z",
            "collector_version": "1.0",
            "cluster_count": 1,
            "drilldown_count": 1,
            "proposal_count": 1,
            "external_analysis_count": 2,
            "notification_count": 1,
            "llm_stats": {
                "totalCalls": 2,
                "successfulCalls": 2,
                "failedCalls": 0,
                "lastCallTimestamp": "2026-01-01T00:00:00Z",
                "p50LatencyMs": 120,
                "p95LatencyMs": 120,
                "p99LatencyMs": 120,
                "providerBreakdown": [
                    {"provider": "k8sgpt", "calls": 1, "failedCalls": 0},
                    {"provider": "llm-autodrilldown", "calls": 1, "failedCalls": 0},
                ],
                "scope": "current_run",
            },
            "historical_llm_stats": {
                "totalCalls": 5,
                "successfulCalls": 4,
                "failedCalls": 1,
                "lastCallTimestamp": "2025-12-31T23:59:00Z",
                "p50LatencyMs": 130,
                "p95LatencyMs": 250,
                "p99LatencyMs": 260,
                "providerBreakdown": [
                    {"provider": "k8sgpt", "calls": 3, "failedCalls": 1},
                    {"provider": "llm-autodrilldown", "calls": 2, "failedCalls": 0},
                ],
                "scope": "retained_history",
            },
        },
        "run_stats": {
            "last_run_duration_seconds": 42,
            "total_runs": 3,
            "p50_run_duration_seconds": 30,
            "p95_run_duration_seconds": 40,
            "p99_run_duration_seconds": 50,
        },
        "clusters": [
            {
                "label": "cluster-a",
                "context": "cluster-a",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 3,
                "control_plane_version": "v1.26.0",
                "health_rating": "degraded",
                "warnings": 2,
                "non_running_pods": 1,
                "baseline_policy_path": "policy.json",
                "missing_evidence": ["foo"],
                "artifact_paths": {
                    "snapshot": "snapshots/cluster-a.json",
                    "assessment": "assessments/cluster-a.json",
                    "drilldown": "drilldowns/cluster-a.json",
                },
            }
        ],
        "proposals": [
            {
                "proposal_id": "p1",
                "target": "health.trigger_policy.warning_event_threshold",
                "status": "pending",
                "confidence": "low",
                "rationale": "test",
                "expected_benefit": "less noise",
                "source_run_id": "run-1",
                "artifact_path": "proposals/p1.json",
                "review_artifact": "reviews/run-1-review.json",
                "lifecycle_history": [
                    {"status": "pending", "timestamp": "2026-01-01T00:00:00Z"}
                ],
            }
        ],
        "fleet_status": {
            "rating_counts": [{"rating": "degraded", "count": 1}],
            "degraded_clusters": ["cluster-a"],
        },
        "proposal_status_summary": {
            "status_counts": [{"status": "pending", "count": 1}]
        },
        "latest_drilldown": {
            "label": "cluster-a",
            "context": "cluster-a",
            "trigger_reasons": ["warning_event_threshold"],
            "warning_events": 3,
            "non_running_pods": 1,
            "summary": {"foo": "bar"},
            "rollout_status": ["stable"],
            "pattern_details": {"pattern": "noise"},
            "artifact_path": "drilldowns/cluster-a.json",
        },
        "latest_assessment": {
            "cluster_label": "cluster-a",
            "context": "cluster-a",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": ["foo"],
            "findings": [
                {
                    "description": "metric spike",
                    "layer": "workload",
                    "supporting_signals": ["sig-1"],
                }
            ],
            "hypotheses": [
                {
                    "description": "routing issue",
                    "confidence": "medium",
                    "probable_layer": "network",
                    "what_would_falsify": "packets flow normally",
                }
            ],
            "next_evidence_to_collect": [
                {
                    "description": "capture tcpdump",
                    "owner": "platform",
                    "method": "kubectl",
                    "evidence_needed": ["tcpdump"],
                }
            ],
            "recommended_action": {
                "type": "observation",
                "description": "monitor ingress metrics",
                "references": ["sig-1"],
                "safety_level": "low-risk",
            },
            "overall_confidence": "medium",
            "probable_layer_of_origin": "network",
            "artifact_path": "assessments/cluster-a.json",
            "snapshot_path": "snapshots/cluster-a.json",
        },
        "drilldown_availability": {
            "total_clusters": 1,
            "available": 1,
            "missing": 0,
            "coverage": [
                {
                    "label": "cluster-a",
                    "context": "cluster-a",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/cluster-a.json",
                }
            ],
            "missing_clusters": [],
        },
        "notification_history": [
            {
                "kind": "degraded-health",
                "summary": "cluster degraded",
                "timestamp": "2026-01-01T00:00:00Z",
                "run_id": "run-1",
                "cluster_label": "cluster-a",
                "context": "cluster-a",
                "details": [{"label": "warnings", "value": "[1, 2]"}],
                "artifact_path": "notifications/degraded-health.json",
            }
        ],
        "external_analysis": {
            "count": 2,
            "status_counts": [{"status": "success", "count": 2}],
            "artifacts": [
                {
                    "tool_name": "k8sgpt",
                    "cluster_label": "cluster-a",
                    "status": "success",
                    "summary": "analysis",
                    "findings": ["f1"],
                    "suggested_next_checks": ["next"],
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "external-analysis/cluster-a.json",
                    "duration_ms": 120,
                    "provider": "k8sgpt",
                    "purpose": "manual",
                    "payload": None,
                    "error_summary": None,
                    "skip_reason": None,
                },
                {
                    "tool_name": "llm-autodrilldown",
                    "cluster_label": "cluster-a",
                    "status": "success",
                    "summary": "LLM drilldown insight",
                    "findings": ["auto-f1"],
                    "suggested_next_checks": ["auto-check"],
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "external-analysis/run-1-cluster-a-auto-default.json",
                    "duration_ms": 150,
                    "provider": "default",
                    "purpose": "auto-drilldown",
                    "payload": {"hypotheses": []},
                    "error_summary": None,
                    "skip_reason": None,
                },
            ],
        },
        "auto_drilldown_interpretations": {
            "cluster-a": {
                "adapter": "llm-autodrilldown",
                "status": "success",
                "summary": "LLM drilldown insight",
                "timestamp": "2026-01-01T00:00:00Z",
                "artifact_path": "external-analysis/run-1-cluster-a-auto-default.json",
                "provider": "default",
                "duration_ms": 150,
                "payload": {"hypotheses": []},
                "error_summary": None,
                "skip_reason": None,
            }
        },
    }
