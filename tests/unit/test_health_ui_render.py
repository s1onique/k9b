import html
import unittest

from k8s_diag_agent.ui.model import (
    AssessmentFindingView,
    AssessmentHypothesisView,
    AssessmentNextCheckView,
    AssessmentView,
    ClusterView,
    ProposalView,
    RecommendedActionView,
)
from k8s_diag_agent.ui.server import (
    _render_assessment_panel,
    _render_cluster_row,
    _render_proposal_row,
)


class HealthUIRenderTests(unittest.TestCase):
    def test_proposal_row_shows_lifecycle_and_artifacts(self) -> None:
        proposal = ProposalView(
            proposal_id="p1",
            target="health.trigger_policy.warning_event_threshold",
            status="pending",
            confidence="low",
            rationale="test",
            expected_benefit="less noise",
            source_run_id="run-1",
            latest_note="note",
            artifact_path="proposals/p1.json",
            review_path="reviews/run-1-review.json",
            lifecycle_history=(
                ("pending", "2026-01-01T00:00:00Z", "checked"),
            ),
        )
        row = _render_proposal_row(proposal)
        self.assertIn("lifecycle-history", row)
        self.assertIn(html.escape("pending"), row)
        self.assertIn(html.escape("Proposal JSON"), row)
        self.assertIn(html.escape("Review JSON"), row)

    def test_cluster_row_shows_trigger_and_drilldown_status(self) -> None:
        cluster = ClusterView(
            label="cluster-a",
            context="cluster-a",
            cluster_class="prod",
            cluster_role="primary",
            baseline_cohort="fleet",
            node_count=3,
            control_plane_version="v1.26.0",
            health_rating="degraded",
            warnings=2,
            non_running_pods=1,
            baseline_policy_path="policy.json",
            missing_evidence=("foo",),
            latest_run_timestamp="2026-01-01T00:00:00Z",
            top_trigger_reason="warning_event_threshold",
            drilldown_available=True,
            drilldown_timestamp="2026-01-01T01:00:00Z",
            snapshot_path="snapshots/cluster-a.json",
            assessment_path="assessments/cluster-a.json",
            drilldown_path="drilldowns/cluster-a.json",
        )
        row = _render_cluster_row(cluster)
        self.assertIn("warning_event_threshold", row)
        self.assertIn("Ready", row)
        self.assertIn("2026-01-01T00:00:00Z", row)

    def test_assessment_panel_renders_hypotheses_and_checks(self) -> None:
        assessment = AssessmentView(
            cluster_label="cluster-a",
            context="cluster-a",
            timestamp="2026-01-01T00:00:00Z",
            health_rating="degraded",
            missing_evidence=("foo",),
            findings=(
                AssessmentFindingView(
                    description="Restart storms",
                    layer="workload",
                    supporting_signals=("sig-1",),
                ),
            ),
            hypotheses=(
                AssessmentHypothesisView(
                    description="CPU limit too low",
                    confidence="medium",
                    probable_layer="workload",
                    what_would_falsify="CPU well below limit",
                ),
            ),
            next_checks=(
                AssessmentNextCheckView(
                    description="Check pod stats",
                    owner="ops",
                    method="kubectl",
                    evidence_needed=("kubectl top",),
                ),
            ),
            recommended_action=RecommendedActionView(
                action_type="observation",
                description="Monitor pods",
                references=("sig-1",),
                safety_level="low-risk",
            ),
            probable_layer="workload",
            overall_confidence="medium",
            artifact_path="assessments/cluster-a.json",
            snapshot_path="snapshots/cluster-a.json",
        )
        panel = _render_assessment_panel(assessment)
        self.assertIn("Confidence: medium", panel)
        self.assertIn("Falsifier", panel)
        self.assertIn("Evidence needed", panel)
        self.assertIn("Safety: low-risk", panel)
