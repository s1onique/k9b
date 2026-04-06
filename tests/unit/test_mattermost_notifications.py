import unittest

from k8s_diag_agent.health.notifications import NotificationArtifact
from k8s_diag_agent.notifications.mattermost import render_mattermost_payload


class MattermostNotificationTests(unittest.TestCase):
    def _artifact(self, kind: str, details: dict[str, object]) -> NotificationArtifact:
        return NotificationArtifact(
            kind=kind,
            summary=f"Summary for {kind}",
            details=details,
            run_id="run-1",
            cluster_label="cluster-a",
            context="context-a",
        )

    def test_degraded_health_payload_includes_missing_evidence(self) -> None:
        artifact = self._artifact("degraded-health", {"warnings": ["foo"], "cluster": "cluster-a"})
        payload = render_mattermost_payload(artifact)
        text = str(payload.get("text", ""))
        self.assertIn("Missing evidence", text)
        self.assertIn("Cluster: cluster-a", text)

    def test_suspicious_comparison_payload_mentions_differences(self) -> None:
        artifact = self._artifact(
            "suspicious-comparison",
            {"reasons": ["drift"], "differences": {"foo": "bar"}, "intent": "replication"},
        )
        payload = render_mattermost_payload(artifact)
        text = str(payload.get("text", ""))
        self.assertIn("Intent: replication", text)
        self.assertIn("Differences", text)

    def test_proposal_created_payload_describes_target(self) -> None:
        artifact = self._artifact(
            "proposal-created",
            {"target": "health.trigger_policy.warning_event_threshold", "confidence": "medium", "rationale": "test"},
        )
        target_text = str(render_mattermost_payload(artifact).get("text", ""))
        self.assertIn("Target:", target_text)

    def test_proposal_checked_payload_includes_outcome(self) -> None:
        artifact = self._artifact(
            "proposal-checked",
            {"outcome": "pass", "noise_reduction": "10%", "signal_loss": "low"},
        )
        outcome_text = str(render_mattermost_payload(artifact).get("text", ""))
        self.assertIn("Outcome: pass", outcome_text)
