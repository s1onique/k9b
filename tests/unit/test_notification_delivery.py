import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from k8s_diag_agent.health.notifications import NotificationArtifact
from k8s_diag_agent.notifications.delivery import DeliveryJournal, artifact_digest


class NotificationDeliveryTests(unittest.TestCase):
    def test_journal_records_and_detects_delivery(self) -> None:
        artifact = NotificationArtifact(
            kind="degraded-health",
            summary="test",
            details={"warnings": ["foo"]},
            run_id="run-1",
            cluster_label="cluster-a",
            context="context-a",
        )
        digest = artifact_digest(artifact)
        with TemporaryDirectory() as tempdir:
            journal_dir = Path(tempdir)
            journal = DeliveryJournal.load(journal_dir)
            self.assertFalse(journal.is_delivered("alert.json", digest))
            journal.record_result("alert.json", digest, "sent")
            self.assertTrue(journal.is_delivered("alert.json", digest))
            # Reload should retain history
            reloaded = DeliveryJournal.load(journal_dir)
            self.assertTrue(reloaded.is_delivered("alert.json", digest))
            # Different digest should not be treated as delivered
            self.assertFalse(reloaded.is_delivered("alert.json", "other"))

    def test_needs_delivery_tracks_status_and_hash(self) -> None:
        artifact = NotificationArtifact(
            kind="proposal-created",
            summary="proposal",
            details={},
            run_id="run-1",
        )
        digest = artifact_digest(artifact)
        with TemporaryDirectory() as tempdir:
            journal = DeliveryJournal.load(Path(tempdir))
            self.assertTrue(journal.needs_delivery("proposal.json", digest))
            journal.record_result("proposal.json", digest, "failed", "timeout")
            self.assertTrue(journal.needs_delivery("proposal.json", digest))
            journal.record_result("proposal.json", digest, "sent")
            self.assertFalse(journal.needs_delivery("proposal.json", digest))
            self.assertTrue(journal.needs_delivery("proposal.json", "newhash"))
