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
        self.assertEqual(context.external_analysis.count, 3)
        self.assertEqual(context.run.external_analysis_count, 3)
        self.assertEqual(context.run.notification_count, 1)
        self.assertEqual(context.run.scheduler_interval_seconds, 300)
        self.assertIsNotNone(context.latest_assessment)
        assessment = cast(AssessmentView, context.latest_assessment)
        self.assertEqual(assessment.cluster_label, "cluster-a")
        self.assertIsNotNone(assessment.recommended_action)
        recommended_action = cast(RecommendedActionView, assessment.recommended_action)
        self.assertEqual(recommended_action.action_type, "observation")
        self.assertEqual(assessment.next_checks[0].owner, "platform")
        self.assertEqual(context.run.run_stats.total_runs, 3)
        self.assertEqual(context.run.run_stats.last_run_duration_seconds, 42)
        self.assertEqual(context.run.llm_stats.total_calls, 3)
        provider_names = {entry.provider for entry in context.run.llm_stats.provider_breakdown}
        self.assertIn("k8sgpt", provider_names)
        self.assertIn("llm-autodrilldown", provider_names)
        self.assertIn("cluster-a", context.auto_drilldown_interpretations)
        interpretation = context.auto_drilldown_interpretations["cluster-a"]
        self.assertEqual(interpretation.status, "success")
        self.assertIsNotNone(context.run.historical_llm_stats)
        historical = context.run.historical_llm_stats
        assert historical is not None
        self.assertEqual(historical.total_calls, 5)
        self.assertEqual(historical.successful_calls, 4)
        self.assertEqual(historical.failed_calls, 1)
        self.assertEqual(historical.scope, "retained_history")
        activity = context.llm_activity
        self.assertEqual(activity.summary.retained_entries, 3)
        self.assertEqual(activity.entries[0].status, "success")
        llm_policy = context.run.llm_policy
        self.assertIsNotNone(llm_policy)
        assert llm_policy is not None
        auto_policy = llm_policy.auto_drilldown
        self.assertIsNotNone(auto_policy)
        assert auto_policy is not None
        self.assertEqual(auto_policy.provider, "default")
        self.assertEqual(auto_policy.max_per_run, 3)
        self.assertEqual(auto_policy.used_this_run, 1)
        self.assertEqual(auto_policy.successful_this_run, 0)
        self.assertEqual(auto_policy.failed_this_run, 1)
        self.assertEqual(auto_policy.skipped_this_run, 0)

        review_enrichment = context.run.review_enrichment
        self.assertIsNotNone(review_enrichment)
        assert review_enrichment is not None
        self.assertEqual(review_enrichment.status, "success")
        self.assertEqual(review_enrichment.triage_order, ("cluster-b", "cluster-a"))
        self.assertEqual(review_enrichment.top_concerns[0], "ingress latency")
        self.assertIsNone(context.run.review_enrichment_status)

        plan = context.run.next_check_plan
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.candidate_count, 3)
        self.assertEqual(
            plan.candidates[0].description,
            "Collect kubelet logs for control-plane pods",
        )
        self.assertEqual(plan.candidates[0].candidate_id, "candidate-control-plane-logs")
        self.assertEqual(plan.candidates[0].priority_label, "primary")
        self.assertEqual(plan.candidates[1].gating_reason, "Command not recognized or too vague")
        self.assertEqual(plan.candidates[1].priority_label, "fallback")
        self.assertTrue(plan.candidates[2].duplicate_of_existing_evidence)
        self.assertEqual(
            plan.candidates[2].duplicate_evidence_description,
            "Collect kubelet metrics",
        )
        self.assertEqual(plan.candidates[0].normalization_reason, "selection_label")
        self.assertEqual(plan.candidates[0].safety_reason, "known_command")
        self.assertEqual(plan.candidates[2].duplicate_reason, "exact_match")
        self.assertEqual(plan.orphaned_approvals, ())
        history_entries = context.run.next_check_execution_history
        self.assertTrue(history_entries)
        self.assertEqual(history_entries[0].status, "success")
        self.assertFalse(history_entries[0].timed_out)

        planner_availability = context.run.planner_availability
        self.assertIsNotNone(planner_availability)
        assert planner_availability is not None
        self.assertEqual(planner_availability.status, "planner-present")
        self.assertIsNotNone(planner_availability.reason)
        assert planner_availability.reason is not None
        self.assertTrue(planner_availability.reason.startswith("3 provider-suggested"))

        provider_execution = context.run.provider_execution
        self.assertIsNotNone(provider_execution)
        assert provider_execution is not None
        auto_branch = provider_execution.auto_drilldown
        self.assertIsNotNone(auto_branch)
        assert auto_branch is not None
        self.assertEqual(auto_branch.provider, "default")
        self.assertEqual(auto_branch.eligible, 2)
        self.assertEqual(auto_branch.attempted, 1)
        self.assertEqual(auto_branch.failed, 1)
        self.assertEqual(auto_branch.unattempted, 1)
        self.assertEqual(auto_branch.budget_limited, 1)
        review_branch = provider_execution.review_enrichment
        self.assertIsNotNone(review_branch)
        assert review_branch is not None
        self.assertEqual(review_branch.eligible, 1)
        self.assertEqual(review_branch.attempted, 1)
        self.assertEqual(review_branch.succeeded, 1)
