import unittest

from k8s_diag_agent.health.adaptation import _baseline_release_proposals
from k8s_diag_agent.health.baseline import BaselinePolicy


class HealthAdaptationTests(unittest.TestCase):
    def test_release_proposals_skipped_when_baseline_mismatch(self) -> None:
        details = [
            {
                "type": "baseline_mismatch",
                "reason": "baseline mismatch (a vs b)",
                "actual_value": "a vs b",
            },
            {
                "type": "watched Helm release platform drift",
                "reason": "watched Helm release platform drift (v1 vs v2)",
                "actual_value": "v1 vs v2",
            },
        ]
        proposals = _baseline_release_proposals(
            run_id="run",
            review_path="review",
            source_run_id="run",
            baseline_policy=BaselinePolicy.empty(),
            details=details,
        )
        self.assertEqual(len(proposals), 0)
