"""Tests for artifact_id field in HealthProposal.

Design:
- artifact_id is None for legacy artifacts (deserialized from files without it)
- artifact_id is auto-generated for NEW proposals created via generate_proposals_from_review()
- artifact_id is preserved when deserializing artifacts that already have it
- Direct HealthProposal() construction does NOT auto-generate artifact_id
  (use generate_proposals_from_review() for new proposals)
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.health.adaptation import HealthProposal, generate_proposals_from_review
from k8s_diag_agent.health.review_feedback import DrilldownSelection, HealthReviewArtifact
from k8s_diag_agent.models import ConfidenceLevel


def _make_review() -> HealthReviewArtifact:
    """Create a minimal HealthReviewArtifact for testing."""
    selection = DrilldownSelection(
        label="cluster-a",
        context="cluster-a",
        reasons=("warning_event_threshold",),
        warning_event_count=10,
        non_running_pod_count=2,
        severity=4,
        missing_evidence=(),
    )
    return HealthReviewArtifact(
        run_id="run-1",
        timestamp=datetime.now(UTC),
        selected_drilldowns=(selection,),
        quality_summary=(),
        failure_modes=(),
        proposed_improvements=(),
    )


class TestProposalArtifactIdFactoryFunction(unittest.TestCase):
    """Tests for artifact_id in proposals generated via factory function."""

    def test_generate_proposals_includes_artifact_id(self) -> None:
        """generate_proposals_from_review should create proposals with artifact_id."""
        review = _make_review()
        proposals = generate_proposals_from_review(
            review=review,
            review_path=Path("/path/to/review.json"),
            run_id="run-1",
            warning_threshold=5,
            baseline_policy=None,
        )
        self.assertTrue(len(proposals) > 0, "Should generate at least one proposal")
        for proposal in proposals:
            self.assertIsNotNone(proposal.artifact_id, f"Proposal {proposal.proposal_id} should have artifact_id")
            assert proposal.artifact_id is not None
            self.assertIsInstance(proposal.artifact_id, str)
            self.assertGreater(len(proposal.artifact_id), 0)

    def test_generate_proposals_artifact_ids_unique(self) -> None:
        """Each generated proposal should have a unique artifact_id."""
        review = _make_review()
        proposals = generate_proposals_from_review(
            review=review,
            review_path=Path("/path/to/review.json"),
            run_id="run-1",
            warning_threshold=5,
            baseline_policy=None,
        )
        ids = {p.artifact_id for p in proposals}
        self.assertEqual(len(ids), len(proposals), "All artifact_ids should be unique")

    def test_generate_proposals_artifact_id_uuid_format(self) -> None:
        """Generated artifact_id should be UUID-like format."""
        review = _make_review()
        proposals = generate_proposals_from_review(
            review=review,
            review_path=Path("/path/to/review.json"),
            run_id="run-1",
            warning_threshold=5,
            baseline_policy=None,
        )
        for proposal in proposals:
            aid = proposal.artifact_id
            assert aid is not None
            parts = aid.split("-")
            self.assertEqual(len(parts), 5)
            self.assertEqual(len(parts[0]), 8)
            self.assertEqual(len(parts[1]), 4)
            self.assertEqual(len(parts[2]), 4)
            self.assertEqual(len(parts[3]), 4)
            self.assertEqual(len(parts[4]), 12)


class TestProposalArtifactIdSerialization(unittest.TestCase):
    """Tests for artifact_id serialization/deserialization."""

    def test_to_dict_includes_artifact_id_when_present(self) -> None:
        """to_dict should serialize artifact_id when present."""
        proposal = HealthProposal(
            proposal_id="p1",
            source_run_id="run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="reduce noise",
            rollback_note="restore default",
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        result = proposal.to_dict()
        self.assertIn("artifact_id", result)
        self.assertEqual(result["artifact_id"], "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_from_dict_preserves_artifact_id(self) -> None:
        """from_dict should parse and preserve artifact_id."""
        raw = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "source_artifact_path": "runs/health/review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Raise threshold",
            "rationale": "test",
            "confidence": "low",
            "expected_benefit": "reduce noise",
            "rollback_note": "restore default",
            "artifact_id": "0192a1b8-3c4e-5678-abcd-1234567890ab",
        }
        proposal = HealthProposal.from_dict(raw)
        self.assertEqual(proposal.artifact_id, "0192a1b8-3c4e-5678-abcd-1234567890ab")

    def test_from_dict_missing_artifact_id_returns_none(self) -> None:
        """Legacy artifacts without artifact_id should deserialize with None."""
        raw = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "source_artifact_path": "runs/health/review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Raise threshold",
            "rationale": "test",
            "confidence": "low",
            "expected_benefit": "reduce noise",
            "rollback_note": "restore default",
            # No artifact_id field
        }
        proposal = HealthProposal.from_dict(raw)
        self.assertIsNone(proposal.artifact_id)

    def test_roundtrip_preserves_artifact_id(self) -> None:
        """Roundtrip serialization should preserve artifact_id."""
        original = HealthProposal(
            proposal_id="p1",
            source_run_id="run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="reduce noise",
            rollback_note="restore default",
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        serialized = original.to_dict()
        restored = HealthProposal.from_dict(serialized)
        self.assertEqual(restored.artifact_id, original.artifact_id)

    def test_legacy_proposal_to_dict_excludes_artifact_id(self) -> None:
        """Legacy proposals (without artifact_id) should not include it in to_dict."""
        raw = {
            "proposal_id": "p1",
            "source_run_id": "run-1",
            "source_artifact_path": "runs/health/review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Raise threshold",
            "rationale": "test",
            "confidence": "low",
            "expected_benefit": "reduce noise",
            "rollback_note": "restore default",
            # No artifact_id field
        }
        proposal = HealthProposal.from_dict(raw)
        # artifact_id should be None for legacy proposals
        self.assertIsNone(proposal.artifact_id)
        # to_dict should NOT include artifact_id when it's None
        result = proposal.to_dict()
        self.assertNotIn("artifact_id", result)


class TestProposalArtifactIdSeparation(unittest.TestCase):
    """Tests ensuring artifact_id stays distinct from other identifiers."""

    def test_artifact_id_distinct_from_proposal_id(self) -> None:
        """artifact_id must remain distinct from proposal_id."""
        proposal = HealthProposal(
            proposal_id="p1",
            source_run_id="run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="reduce noise",
            rollback_note="restore default",
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        self.assertNotEqual(proposal.artifact_id, proposal.proposal_id)

    def test_artifact_id_distinct_from_source_run_id(self) -> None:
        """artifact_id must remain distinct from source_run_id."""
        proposal = HealthProposal(
            proposal_id="p1",
            source_run_id="run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="reduce noise",
            rollback_note="restore default",
            artifact_id="0192a1b8-3c4e-5678-abcd-1234567890ab",
        )
        self.assertNotEqual(proposal.artifact_id, proposal.source_run_id)

    def test_explicit_artifact_id_preserved(self) -> None:
        """Explicit artifact_id should be preserved (not overwritten)."""
        explicit_id = "0192a1b8-3c4e-5678-abcd-1234567890ab"
        proposal = HealthProposal(
            proposal_id="p1",
            source_run_id="run-1",
            source_artifact_path="runs/health/review.json",
            target="health.trigger_policy.warning_event_threshold",
            proposed_change="Raise threshold",
            rationale="test",
            confidence=ConfidenceLevel.LOW,
            expected_benefit="reduce noise",
            rollback_note="restore default",
            artifact_id=explicit_id,
        )
        self.assertEqual(proposal.artifact_id, explicit_id)
        result = proposal.to_dict()
        self.assertEqual(result["artifact_id"], explicit_id)


if __name__ == "__main__":
    unittest.main()
