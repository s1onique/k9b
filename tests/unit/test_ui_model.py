import unittest
from typing import cast

from k8s_diag_agent.ui.model import AssessmentView, FindingsView, RecommendedActionView, build_ui_context


class UIViewModelTests(unittest.TestCase):
    def test_build_ui_context_from_index(self) -> None:
        index = {
            "run": {
                "run_id": "run-1",
                "run_label": "health-run",
                "timestamp": "2026-01-01T00:00:00Z",
                "collector_version": "1.0",
                "cluster_count": 1,
                "drilldown_count": 1,
                "proposal_count": 1,
                "external_analysis_count": 1,
                "notification_count": 1,
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
                "rating_counts": [
                    {"rating": "degraded", "count": 1}
                ],
                "degraded_clusters": ["cluster-a"],
            },
            "proposal_status_summary": {
                "status_counts": [
                    {"status": "pending", "count": 1}
                ]
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
                    {"description": "metric spike", "layer": "workload", "supporting_signals": ["sig-1"]}
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
                "count": 1,
                "status_counts": [{"status": "success", "count": 1}],
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
                    }
                ],
            },
        }
        context = build_ui_context(index)
        self.assertEqual(context.run.run_id, "run-1")
        self.assertEqual(context.clusters[0].cluster_class, "prod")
        self.assertEqual(context.clusters[0].cluster_role, "primary")
        self.assertEqual(context.proposals[0].status, "pending")
        self.assertIsNotNone(context.latest_findings)
        findings = cast(FindingsView, context.latest_findings)
        self.assertEqual(findings.trigger_reasons, ("warning_event_threshold",))
        self.assertEqual(findings.rollout_status, ("stable",))
        self.assertEqual(findings.pattern_details[0][0], "pattern")
        self.assertIn("bar", findings.summary[0][1])
        self.assertEqual(context.clusters[0].snapshot_path, "snapshots/cluster-a.json")
        self.assertEqual(context.clusters[0].assessment_path, "assessments/cluster-a.json")
        self.assertEqual(context.clusters[0].drilldown_path, "drilldowns/cluster-a.json")
        self.assertEqual(context.proposals[0].artifact_path, "proposals/p1.json")
        self.assertEqual(context.proposals[0].review_path, "reviews/run-1-review.json")
        self.assertEqual(context.proposals[0].lifecycle_history[0][0], "pending")
        self.assertEqual(context.fleet_status.degraded_clusters, ("cluster-a",))
        self.assertEqual(context.proposal_status_summary.status_counts[0][0], "pending")
        self.assertEqual(findings.artifact_path, "drilldowns/cluster-a.json")
        self.assertEqual(context.drilldown_availability.available, 1)
        self.assertEqual(context.notification_history[0].kind, "degraded-health")
        self.assertEqual(context.external_analysis.count, 1)
        self.assertEqual(context.run.external_analysis_count, 1)
        self.assertEqual(context.run.notification_count, 1)
        self.assertIsNotNone(context.latest_assessment)
        assessment = cast(AssessmentView, context.latest_assessment)
        self.assertEqual(assessment.cluster_label, "cluster-a")
        self.assertIsNotNone(assessment.recommended_action)
        recommended_action = cast(RecommendedActionView, assessment.recommended_action)
        self.assertEqual(recommended_action.action_type, "observation")
        self.assertEqual(assessment.next_checks[0].owner, "platform")
