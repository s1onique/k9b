import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from k8s_diag_agent.health.adaptation import (
    HealthProposal,
    evaluate_proposal,
    generate_proposals_from_review,
)
from k8s_diag_agent.health.baseline import BaselinePolicy
from k8s_diag_agent.health.review_feedback import DrilldownSelection, HealthReviewArtifact, QualityMetric
from k8s_diag_agent.models import ConfidenceLevel


class HealthAdaptationTest(unittest.TestCase):
    def test_generates_warning_and_baseline_proposals(self) -> None:
        selection = DrilldownSelection(
            context="cluster-a",
            label="cluster-a",
            severity=1,
            reasons=("warning_event_threshold", "NoisyWarning"),
            missing_evidence=(),
            warning_event_count=5,
            non_running_pod_count=0,
        )
        review = HealthReviewArtifact(
            run_id="run-123",
            timestamp=datetime.now(timezone.utc),
            selected_drilldowns=(selection,),
            quality_summary=(
                QualityMetric(
                    dimension="drilldown_prioritization",
                    level="low",
                    score=10,
                    detail="Weak prioritization",
                ),
            ),
            failure_modes=(),
            proposed_improvements=(),
        )
        triggers = [
            {
                "type": "watched_helm_release",
                "reason": "watched Helm release kube-system/observability drift (1.1.0 vs 1.1.1)",
                "actual_value": "1.1.0 vs 1.1.1",
            },
            {
                "type": "watched_crd",
                "reason": "watched CRD monitoring.example.com storage drift (v1 vs v1beta1)",
                "actual_value": "v1 vs v1beta1",
            },
        ]
        baseline = BaselinePolicy.empty()
        before = dict(baseline.release_policies)
        proposals = generate_proposals_from_review(
            review=review,
            review_path=Path("runs/health/reviews/run-123-review.json"),
            run_id="run-123",
            warning_threshold=1,
            baseline_policy=baseline,
            trigger_details=triggers,
        )
        self.assertTrue(any(p.target == "health.trigger_policy.warning_event_threshold" for p in proposals))
        self.assertTrue(any(p.target == "health.baseline_policy.watched_releases" for p in proposals))
        self.assertTrue(any(p.target == "health.baseline_policy.required_crd_families" for p in proposals))
        repo = proposals[0]
        serialized = repo.to_dict()
        restored = HealthProposal.from_dict(serialized)
        self.assertEqual(repo, restored)
        self.assertEqual(before, baseline.release_policies)

    def test_evaluate_proposal_uses_fixture(self) -> None:
        proposal = HealthProposal(
            proposal_id="run-123-warning",
            source_run_id="run-123",
            source_artifact_path="runs/health/reviews/run-123-review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold.",
            rationale="Noise.",
            confidence=ConfidenceLevel.MEDIUM,
            expected_benefit="Less noise.",
            rollback_note="Revert if needed.",
        )
        evaluation = evaluate_proposal(proposal, Path("tests/fixtures/snapshots/sanitized-alpha.json"))
        self.assertIn("noise", evaluation.noise_reduction.lower())
        self.assertIn("non-running", evaluation.signal_loss.lower())
        self.assertIn("sanitized-alpha", evaluation.test_outcome)
