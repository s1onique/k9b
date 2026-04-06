import unittest
from typing import cast

from k8s_diag_agent.ui.model import FindingsView, build_ui_context


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
