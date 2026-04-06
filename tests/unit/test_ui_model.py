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
                    "lifecycle_history": [
                        {"status": "pending", "timestamp": "2026-01-01T00:00:00Z"}
                    ],
                }
            ],
            "latest_drilldown": {
                "label": "cluster-a",
                "context": "cluster-a",
                "trigger_reasons": ["warning_event_threshold"],
                "warning_events": 3,
                "non_running_pods": 1,
                "summary": {"foo": "bar"},
                "rollout_status": ["stable"],
                "pattern_details": {"pattern": "noise"},
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
