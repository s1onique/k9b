import unittest
from typing import cast

from k8s_diag_agent.ui.model import AssessmentView, FindingsView, RecommendedActionView, build_ui_context
from tests.fixtures.ui_index_sample import sample_ui_index


class UIViewModelTests(unittest.TestCase):
    def test_build_ui_context_from_index(self) -> None:
        index = sample_ui_index()
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
        self.assertEqual(context.run.run_stats.total_runs, 3)
        self.assertEqual(context.run.run_stats.last_run_duration_seconds, 42)
