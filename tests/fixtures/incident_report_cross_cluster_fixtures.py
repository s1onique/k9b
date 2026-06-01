"""Cross-cluster drift fixture helpers for BETA-G2 epic regression tests.

This module provides deterministic fixture builders that construct synthetic UI index
structures for testing cross-cluster findings in the incident report projection.

Purpose
-------
- Provide replayable, deterministic fixtures for cross-cluster drift scenarios
- Protect against cross-cluster findings appearing as per-cluster observations
- Protect against unsupported causal language in cross-cluster findings
- Protect against cross-cluster drift masquerading as single-cluster facts
- Verify fleet-aware recommendations surface correctly

Scenario coverage
----------------
1. _fixture_helm_release_drift: Same-role clusters with Helm release drift
2. _fixture_control_plane_drift: Same-role clusters with control plane version drift
3. _fixture_crd_family_drift: Same-role clusters with CRD family drift
4. _fixture_healthy_but_suspicious_cross_cluster: Healthy assessments but suspicious comparison
5. _fixture_cross_cluster_drift_with_degraded_workload: Cross-cluster drift plus degraded workload

Example usage
-------------
    from tests.fixtures.incident_report_cross_cluster_fixtures import (
        _fixture_helm_release_drift,
        _fixture_control_plane_drift,
        _fixture_healthy_but_suspicious_cross_cluster,
    )
    from k8s_diag_agent.ui.model import build_ui_context
    from k8s_diag_agent.ui.api_incident_report import _build_incident_report_payload

    # Test helm release drift
    index = _fixture_helm_release_drift()
    context = build_ui_context(index)
    report = _build_incident_report_payload(context, _freshness("fresh"))
    assert report is not None
    assert report["crossClusterFindings"] is not None
    assert len(report["crossClusterFindings"]) > 0
    # Verify helm drift recommendation surfaces
    helm_recs = [r for r in report["crossClusterFindings"][0].get("recommendedNextChecks", [])
                 if "helm" in r.lower()]
    assert helm_recs
"""

from __future__ import annotations

from typing import Any, TypeAlias

JsonObject: TypeAlias = dict[str, Any]


def _freshness(status: str) -> dict[str, Any]:
    """Return a freshness payload with the given status."""
    return {
        "ageSeconds": 600,
        "expectedIntervalSeconds": 300,
        "status": status,
    }


def _base_run(run_id: str, cluster_count: int = 2) -> dict[str, object]:
    """Base run entry for a two-cluster comparison scenario."""
    return {
        "run_id": run_id,
        "run_label": "health-run",
        "timestamp": "2026-01-01T00:00:00Z",
        "collector_version": "1.0",
        "cluster_count": cluster_count,
        "drilldown_count": 2,
        "proposal_count": 0,
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
        "next_check_plan": None,
        "planner_availability": None,
        "next_check_queue": [],
        "next_check_execution_history": [],
        "deterministic_next_checks": None,
        "diagnostic_pack_review": None,
        "diagnostic_pack": None,
    }


def _base_clusters() -> list[dict[str, object]]:
    """Base cluster list for comparison scenarios."""
    return [
        {
            "label": "prod-cluster-a",
            "context": "prod-cluster-a",
            "cluster_class": "prod",
            "cluster_role": "primary",
            "baseline_cohort": "fleet",
            "node_count": 5,
            "control_plane_version": "v1.28.0",
            "health_rating": "healthy",
            "warnings": 0,
            "non_running_pods": 0,
            "baseline_policy_path": "policy.json",
            "missing_evidence": [],
            "artifact_paths": {
                "snapshot": "snapshots/prod-cluster-a.json",
                "assessment": "assessments/prod-cluster-a.json",
                "drilldown": "drilldowns/prod-cluster-a.json",
            },
        },
        {
            "label": "prod-cluster-b",
            "context": "prod-cluster-b",
            "cluster_class": "prod",
            "cluster_role": "primary",
            "baseline_cohort": "fleet",
            "node_count": 5,
            "control_plane_version": "v1.28.0",
            "health_rating": "healthy",
            "warnings": 0,
            "non_running_pods": 0,
            "baseline_policy_path": "policy.json",
            "missing_evidence": [],
            "artifact_paths": {
                "snapshot": "snapshots/prod-cluster-b.json",
                "assessment": "assessments/prod-cluster-b.json",
                "drilldown": "drilldowns/prod-cluster-b.json",
            },
        },
    ]


def _fixture_helm_release_drift() -> dict[str, object]:
    """Build a UI index for same-role clusters with Helm release drift.

    Expected outcomes:
    - status: healthy (per-cluster, but cross-cluster findings present)
    - crossClusterFindings: non-empty with helm_releases drift
    - recommendedNextChecks: includes "Compare Helm release versions across same-role clusters"
    - driftCounts: contains helm_releases count > 0

    Protects against:
    - helm release drift not surfaced in cross-cluster findings
    - fleet-aware recommendations missing for helm drift
    """
    run_entry = _base_run("run-helm-drift")
    # Add comparison triggers to run entry
    run_entry["comparison_triggers"] = [
        {
            "run_id": "run-helm-drift",
            "primary_label": "prod-cluster-a",
            "secondary_label": "prod-cluster-b",
            "trigger_reasons": ["helm_release_drift", "baseline_regression"],
            "comparison_summary": {"helm_releases": 3, "metadata": 0, "crds": 0, "metrics": 0},
            "comparison_intent": "drift_detection",
            "artifact_path": "triggers/comparison-prod-cluster-a-prod-cluster-b.json",
            "timestamp": "2026-01-01T00:01:00Z",
        }
    ]

    return {
        "run": run_entry,
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 3,
            "p50_run_duration_seconds": 42,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": _base_clusters(),
        "proposals": [],
        "fleet_status": {
            "rating_counts": [
                {"rating": "healthy", "count": 2},
            ],
            "degraded_clusters": [],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": None,
        "latest_assessment": {
            "cluster_label": "prod-cluster-a",
            "context": "prod-cluster-a",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "healthy",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": None,
            "overall_confidence": "high",
            "probable_layer_of_origin": None,
            "artifact_path": "assessments/prod-cluster-a.json",
            "snapshot_path": "snapshots/prod-cluster-a.json",
        },
        "drilldown_availability": {
            "total_clusters": 2,
            "available": 2,
            "missing": 0,
            "coverage": [
                {
                    "label": "prod-cluster-a",
                    "context": "prod-cluster-a",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-a.json",
                },
                {
                    "label": "prod-cluster-b",
                    "context": "prod-cluster-b",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-b.json",
                },
            ],
            "missing_clusters": [],
        },
        "notification_history": [
            {
                "kind": "suspicious-comparison",
                "summary": "Helm release drift detected between prod clusters",
                "timestamp": "2026-01-01T00:01:00Z",
                "run_id": "run-helm-drift",
                "cluster_label": "prod-cluster-a",
                "context": "prod-cluster-a",
                "details": [
                    {"label": "secondary_cluster", "value": "prod-cluster-b"},
                    {"label": "reasons", "value": "['helm_release_drift', 'baseline_regression']"},
                    {"label": "intent", "value": "drift_detection"},
                    {"label": "differences", "value": "{'helm_releases': 3, 'metadata': 0, 'crds': 0, 'metrics': 0}"},
                ],
                "artifact_path": "notifications/suspicious-comparison-helm-drift.json",
            }
        ],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_control_plane_drift() -> dict[str, object]:
    """Build a UI index for same-role clusters with control plane version drift.

    Expected outcomes:
    - status: healthy (per-cluster, but cross-cluster findings present)
    - crossClusterFindings: non-empty with metadata drift
    - recommendedNextChecks: includes "Check control plane version consistency across fleet"
    - driftCounts: contains metadata count > 0

    Protects against:
    - control plane version drift not surfaced
    - fleet-aware recommendations missing for metadata drift
    """
    run_entry = _base_run("run-cp-drift")
    run_entry["comparison_triggers"] = [
        {
            "run_id": "run-cp-drift",
            "primary_label": "prod-cluster-a",
            "secondary_label": "prod-cluster-b",
            "trigger_reasons": ["control_plane_version_mismatch"],
            "comparison_summary": {"helm_releases": 0, "metadata": 1, "crds": 0, "metrics": 0},
            "comparison_intent": "drift_detection",
            "artifact_path": "triggers/comparison-prod-cluster-a-prod-cluster-b.json",
            "timestamp": "2026-01-01T00:01:00Z",
        }
    ]

    # Override cluster B to have different control plane version
    clusters = _base_clusters()
    clusters[1]["control_plane_version"] = "v1.29.0"

    return {
        "run": run_entry,
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 3,
            "p50_run_duration_seconds": 42,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": clusters,
        "proposals": [],
        "fleet_status": {
            "rating_counts": [
                {"rating": "healthy", "count": 2},
            ],
            "degraded_clusters": [],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": None,
        "latest_assessment": {
            "cluster_label": "prod-cluster-a",
            "context": "prod-cluster-a",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "healthy",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": None,
            "overall_confidence": "high",
            "probable_layer_of_origin": None,
            "artifact_path": "assessments/prod-cluster-a.json",
            "snapshot_path": "snapshots/prod-cluster-a.json",
        },
        "drilldown_availability": {
            "total_clusters": 2,
            "available": 2,
            "missing": 0,
            "coverage": [
                {
                    "label": "prod-cluster-a",
                    "context": "prod-cluster-a",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-a.json",
                },
                {
                    "label": "prod-cluster-b",
                    "context": "prod-cluster-b",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-b.json",
                },
            ],
            "missing_clusters": [],
        },
        "notification_history": [
            {
                "kind": "suspicious-comparison",
                "summary": "Control plane version drift detected between prod clusters",
                "timestamp": "2026-01-01T00:01:00Z",
                "run_id": "run-cp-drift",
                "cluster_label": "prod-cluster-a",
                "context": "prod-cluster-a",
                "details": [
                    {"label": "secondary_cluster", "value": "prod-cluster-b"},
                    {"label": "reasons", "value": "['control_plane_version_mismatch']"},
                    {"label": "intent", "value": "drift_detection"},
                    {"label": "differences", "value": "{'helm_releases': 0, 'metadata': 1, 'crds': 0, 'metrics': 0}"},
                ],
                "artifact_path": "notifications/suspicious-comparison-cp-drift.json",
            }
        ],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_crd_family_drift() -> dict[str, object]:
    """Build a UI index for same-role clusters with CRD family drift.

    Expected outcomes:
    - status: healthy (per-cluster, but cross-cluster findings present)
    - crossClusterFindings: non-empty with crds drift
    - recommendedNextChecks: includes "Inspect CRD storage versions and served APIs across clusters"
    - driftCounts: contains crds count > 0

    Protects against:
    - CRD family drift not surfaced
    - fleet-aware recommendations missing for CRD drift
    """
    run_entry = _base_run("run-crd-drift")
    run_entry["comparison_triggers"] = [
        {
            "run_id": "run-crd-drift",
            "primary_label": "prod-cluster-a",
            "secondary_label": "prod-cluster-b",
            "trigger_reasons": ["crd_family_drift"],
            "comparison_summary": {"helm_releases": 0, "metadata": 0, "crds": 5, "metrics": 0},
            "comparison_intent": "drift_detection",
            "artifact_path": "triggers/comparison-prod-cluster-a-prod-cluster-b.json",
            "timestamp": "2026-01-01T00:01:00Z",
        }
    ]

    return {
        "run": run_entry,
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 3,
            "p50_run_duration_seconds": 42,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": _base_clusters(),
        "proposals": [],
        "fleet_status": {
            "rating_counts": [
                {"rating": "healthy", "count": 2},
            ],
            "degraded_clusters": [],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": None,
        "latest_assessment": {
            "cluster_label": "prod-cluster-a",
            "context": "prod-cluster-a",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "healthy",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": None,
            "overall_confidence": "high",
            "probable_layer_of_origin": None,
            "artifact_path": "assessments/prod-cluster-a.json",
            "snapshot_path": "snapshots/prod-cluster-a.json",
        },
        "drilldown_availability": {
            "total_clusters": 2,
            "available": 2,
            "missing": 0,
            "coverage": [
                {
                    "label": "prod-cluster-a",
                    "context": "prod-cluster-a",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-a.json",
                },
                {
                    "label": "prod-cluster-b",
                    "context": "prod-cluster-b",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-b.json",
                },
            ],
            "missing_clusters": [],
        },
        "notification_history": [
            {
                "kind": "suspicious-comparison",
                "summary": "CRD family drift detected between prod clusters",
                "timestamp": "2026-01-01T00:01:00Z",
                "run_id": "run-crd-drift",
                "cluster_label": "prod-cluster-a",
                "context": "prod-cluster-a",
                "details": [
                    {"label": "secondary_cluster", "value": "prod-cluster-b"},
                    {"label": "reasons", "value": "['crd_family_drift']"},
                    {"label": "intent", "value": "drift_detection"},
                    {"label": "differences", "value": "{'helm_releases': 0, 'metadata': 0, 'crds': 5, 'metrics': 0}"},
                ],
                "artifact_path": "notifications/suspicious-comparison-crd-drift.json",
            }
        ],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_healthy_but_suspicious_cross_cluster() -> dict[str, object]:
    """Build a UI index with healthy per-cluster assessments but suspicious cross-cluster comparison.

    This is the most subtle scenario: each cluster is individually healthy, but a comparison
    reveals suspicious patterns that warrant fleet-level investigation.

    Expected outcomes:
    - status: healthy (per-cluster perspective)
    - crossClusterFindings: non-empty with suspicious-comparison intent
    - findings surface without overstating causality

    Protects against:
    - suspicious comparisons being hidden when per-cluster health is good
    - cross-cluster findings claiming causation when only correlation is known
    """
    run_entry = _base_run("run-suspicious")
    run_entry["comparison_triggers"] = [
        {
            "run_id": "run-suspicious",
            "primary_label": "prod-cluster-a",
            "secondary_label": "prod-cluster-b",
            "trigger_reasons": ["baseline_regression", "health_regression"],
            "comparison_summary": {"helm_releases": 2, "metadata": 1, "crds": 0, "metrics": 3},
            "comparison_intent": "suspicious-comparison",
            "artifact_path": "triggers/comparison-prod-cluster-a-prod-cluster-b.json",
            "timestamp": "2026-01-01T00:01:00Z",
        }
    ]

    return {
        "run": run_entry,
        "run_stats": {
            "last_run_duration_seconds": 45,
            "total_runs": 3,
            "p50_run_duration_seconds": 42,
            "p95_run_duration_seconds": 50,
            "p99_run_duration_seconds": 55,
        },
        "clusters": _base_clusters(),
        "proposals": [],
        "fleet_status": {
            "rating_counts": [
                {"rating": "healthy", "count": 2},
            ],
            "degraded_clusters": [],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": None,
        "latest_assessment": {
            "cluster_label": "prod-cluster-a",
            "context": "prod-cluster-a",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "healthy",
            "missing_evidence": [],
            "findings": [],
            "hypotheses": [],
            "next_evidence_to_collect": [],
            "recommended_action": None,
            "overall_confidence": "high",
            "probable_layer_of_origin": None,
            "artifact_path": "assessments/prod-cluster-a.json",
            "snapshot_path": "snapshots/prod-cluster-a.json",
        },
        "drilldown_availability": {
            "total_clusters": 2,
            "available": 2,
            "missing": 0,
            "coverage": [
                {
                    "label": "prod-cluster-a",
                    "context": "prod-cluster-a",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-a.json",
                },
                {
                    "label": "prod-cluster-b",
                    "context": "prod-cluster-b",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-b.json",
                },
            ],
            "missing_clusters": [],
        },
        "notification_history": [
            {
                "kind": "suspicious-comparison",
                "summary": "Suspicious comparison detected between prod clusters - baseline regression and health regression patterns",
                "timestamp": "2026-01-01T00:01:00Z",
                "run_id": "run-suspicious",
                "cluster_label": "prod-cluster-a",
                "context": "prod-cluster-a",
                "details": [
                    {"label": "secondary_cluster", "value": "prod-cluster-b"},
                    {"label": "reasons", "value": "['baseline_regression', 'health_regression']"},
                    {"label": "intent", "value": "suspicious-comparison"},
                    {"label": "differences", "value": "{'helm_releases': 2, 'metadata': 1, 'crds': 0, 'metrics': 3}"},
                ],
                "artifact_path": "notifications/suspicious-comparison-suspicious.json",
            }
        ],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }


def _fixture_cross_cluster_drift_with_degraded_workload() -> dict[str, object]:
    """Build a UI index with cross-cluster drift plus degraded workload on one cluster.

    This combines per-cluster degradation with cross-cluster drift findings,
    testing that both are surfaced without interference.

    Expected outcomes:
    - status: degraded (from per-cluster perspective)
    - facts: non-empty (per-cluster drilldown findings)
    - crossClusterFindings: non-empty (fleet-level drift)
    - findings are clearly separated from per-cluster observations

    Protects against:
    - cross-cluster findings being overshadowed by per-cluster degradation
    - cross-cluster drift masquerading as single-cluster root cause
    """
    run_entry = _base_run("run-mixed-degraded", cluster_count=2)
    run_entry["drilldown_count"] = 2
    run_entry["comparison_triggers"] = [
        {
            "run_id": "run-mixed-degraded",
            "primary_label": "prod-cluster-a",
            "secondary_label": "prod-cluster-b",
            "trigger_reasons": ["helm_release_drift"],
            "comparison_summary": {"helm_releases": 4, "metadata": 0, "crds": 0, "metrics": 1},
            "comparison_intent": "drift_detection",
            "artifact_path": "triggers/comparison-prod-cluster-a-prod-cluster-b.json",
            "timestamp": "2026-01-01T00:01:00Z",
        }
    ]
    run_entry["deterministic_next_checks"] = {
        "clusterCount": 1,
        "totalNextCheckCount": 1,
        "clusters": [
            {
                "label": "prod-cluster-a",
                "context": "prod-cluster-a",
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
                "assessmentArtifactPath": "assessments/prod-cluster-a.json",
                "drilldownArtifactPath": "drilldowns/prod-cluster-a.json",
            }
        ],
    }

    return {
        "run": run_entry,
        "run_stats": {
            "last_run_duration_seconds": 60,
            "total_runs": 5,
            "p50_run_duration_seconds": 50,
            "p95_run_duration_seconds": 70,
            "p99_run_duration_seconds": 80,
        },
        "clusters": [
            {
                "label": "prod-cluster-a",
                "context": "prod-cluster-a",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 5,
                "control_plane_version": "v1.28.0",
                "health_rating": "degraded",
                "warnings": 5,
                "non_running_pods": 2,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/prod-cluster-a.json",
                    "assessment": "assessments/prod-cluster-a.json",
                    "drilldown": "drilldowns/prod-cluster-a.json",
                },
            },
            {
                "label": "prod-cluster-b",
                "context": "prod-cluster-b",
                "cluster_class": "prod",
                "cluster_role": "primary",
                "baseline_cohort": "fleet",
                "node_count": 5,
                "control_plane_version": "v1.28.0",
                "health_rating": "healthy",
                "warnings": 0,
                "non_running_pods": 0,
                "baseline_policy_path": "policy.json",
                "missing_evidence": [],
                "artifact_paths": {
                    "snapshot": "snapshots/prod-cluster-b.json",
                    "assessment": "assessments/prod-cluster-b.json",
                    "drilldown": "drilldowns/prod-cluster-b.json",
                },
            },
        ],
        "proposals": [],
        "fleet_status": {
            "rating_counts": [
                {"rating": "healthy", "count": 1},
                {"rating": "degraded", "count": 1},
            ],
            "degraded_clusters": ["prod-cluster-a"],
        },
        "proposal_status_summary": {"status_counts": []},
        "latest_drilldown": {
            "label": "prod-cluster-a",
            "context": "prod-cluster-a",
            "trigger_reasons": ["non_running_pods", "warning_event_threshold"],
            "warning_events": 5,
            "non_running_pods": 2,
            "summary": {"pods_affected": ["pod-a", "pod-b"], "patterns": ["crashloop"]},
            "rollout_status": ["stable"],
            "pattern_details": {"pattern": "crashloop"},
            "artifact_path": "drilldowns/prod-cluster-a.json",
        },
        "latest_assessment": {
            "cluster_label": "prod-cluster-a",
            "context": "prod-cluster-a",
            "timestamp": "2026-01-01T00:00:00Z",
            "health_rating": "degraded",
            "missing_evidence": [],
            "findings": [
                {
                    "description": "CrashLoopBackOff detected on 2 pods",
                    "layer": "workload",
                    "supporting_signals": ["sig-1"],
                }
            ],
            "hypotheses": [
                {
                    "description": "Application misconfiguration may cause repeated crashes",
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
                "description": "Investigate pod events and logs for crashed pods",
                "references": ["assessments/prod-cluster-a.json"],
                "safety_level": "low-risk",
            },
            "overall_confidence": "high",
            "probable_layer_of_origin": "workload",
            "artifact_path": "assessments/prod-cluster-a.json",
            "snapshot_path": "snapshots/prod-cluster-a.json",
        },
        "drilldown_availability": {
            "total_clusters": 2,
            "available": 2,
            "missing": 0,
            "coverage": [
                {
                    "label": "prod-cluster-a",
                    "context": "prod-cluster-a",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-a.json",
                },
                {
                    "label": "prod-cluster-b",
                    "context": "prod-cluster-b",
                    "available": True,
                    "timestamp": "2026-01-01T00:00:00Z",
                    "artifact_path": "drilldowns/prod-cluster-b.json",
                },
            ],
            "missing_clusters": [],
        },
        "notification_history": [
            {
                "kind": "degraded-health",
                "summary": "prod-cluster-a degraded",
                "timestamp": "2026-01-01T00:00:00Z",
                "run_id": "run-mixed-degraded",
                "cluster_label": "prod-cluster-a",
                "context": "prod-cluster-a",
                "details": [{"label": "warnings", "value": "[1, 2, 3, 4, 5]"}],
                "artifact_path": "notifications/degraded-health-prod-cluster-a.json",
            },
            {
                "kind": "suspicious-comparison",
                "summary": "Helm release drift detected between prod clusters",
                "timestamp": "2026-01-01T00:01:00Z",
                "run_id": "run-mixed-degraded",
                "cluster_label": "prod-cluster-a",
                "context": "prod-cluster-a",
                "details": [
                    {"label": "secondary_cluster", "value": "prod-cluster-b"},
                    {"label": "reasons", "value": "['helm_release_drift']"},
                    {"label": "intent", "value": "drift_detection"},
                    {"label": "differences", "value": "{'helm_releases': 4, 'metadata': 0, 'crds': 0, 'metrics': 1}"},
                ],
                "artifact_path": "notifications/suspicious-comparison-helm.json",
            },
        ],
        "external_analysis": {"count": 0, "status_counts": [], "artifacts": []},
        "auto_drilldown_interpretations": {},
    }
