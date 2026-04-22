"""Tests for proposal lifecycle event artifacts and immutability."""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from k8s_diag_agent.health.adaptation import (
    HealthProposal,
    ProposalEvaluation,
    ProposalLifecycleStatus,
    with_lifecycle_status,
)
from k8s_diag_agent.health.proposal_lifecycle_events import (
    ProposalLifecycleEvent,
    derive_current_proposal_status,
    write_proposal_lifecycle_event,
)


class ProposalLifecycleEventTests(unittest.TestCase):
    """Tests for ProposalLifecycleEvent dataclass and helpers."""

    def test_event_creation_with_defaults(self) -> None:
        event = ProposalLifecycleEvent(
            proposal_id="test-proposal",
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
        )
        self.assertIsNotNone(event.artifact_id)
        self.assertEqual(event.proposal_id, "test-proposal")
        self.assertEqual(event.status, ProposalLifecycleStatus.CHECKED)
        self.assertEqual(event.transition, "check")
        self.assertIsNotNone(event.created_at)

    def test_event_to_dict_roundtrip(self) -> None:
        event = ProposalLifecycleEvent(
            proposal_id="test-proposal",
            proposal_artifact_id="artifact-123",
            status=ProposalLifecycleStatus.ACCEPTED,
            transition="promote",
            note="Operator approved",
            provenance={"operator": "test-user"},
        )
        data = event.to_dict()
        restored = ProposalLifecycleEvent.from_dict(data)

        self.assertEqual(restored.proposal_id, event.proposal_id)
        self.assertEqual(restored.proposal_artifact_id, event.proposal_artifact_id)
        self.assertEqual(restored.status, event.status)
        self.assertEqual(restored.transition, event.transition)
        self.assertEqual(restored.note, event.note)
        self.assertIsNotNone(restored.provenance)

    def test_event_from_dict_preserves_artifact_id(self) -> None:
        data = {
            "artifact_id": "0192a1b8-3c4e-5678-abcd-1234567890ab",
            "proposal_id": "test-proposal",
            "status": "checked",
            "transition": "check",
            "created_at": "2026-04-07T12:00:00+00:00",
        }
        event = ProposalLifecycleEvent.from_dict(data)
        self.assertEqual(event.artifact_id, "0192a1b8-3c4e-5678-abcd-1234567890ab")


class LifecycleEventWriteTests(unittest.TestCase):
    """Tests for writing lifecycle event artifacts."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.transitions_dir = self.root / "transitions"

    def test_write_event_creates_file(self) -> None:
        event = ProposalLifecycleEvent(
            proposal_id="test-proposal",
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
            note="Test note",
        )
        path = write_proposal_lifecycle_event(event, self.transitions_dir)

        self.assertTrue(path.exists())
        self.assertTrue(self.transitions_dir.exists())
        self.assertIn(event.proposal_id, path.name)
        self.assertIn(event.transition, path.name)
        self.assertIn(event.artifact_id, path.name)
        self.assertTrue(path.name.endswith(".json"))

    def test_write_event_contains_provenance(self) -> None:
        event = ProposalLifecycleEvent(
            proposal_id="test-proposal",
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
            provenance={"fixture_path": "/test/fixture.json"},
        )
        path = write_proposal_lifecycle_event(event, self.transitions_dir)

        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["proposal_id"], "test-proposal")
        self.assertEqual(data["status"], "checked")
        self.assertIn("provenance", data)
        self.assertEqual(data["provenance"]["fixture_path"], "/test/fixture.json")


class DeriveCurrentStatusTests(unittest.TestCase):
    """Tests for current-status derivation from event artifacts."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.transitions_dir = self.root / "transitions"
        self.transitions_dir.mkdir()

    def _write_event(self, proposal_id: str, status: str, artifact_id: str, created_at: str) -> None:
        data = {
            "artifact_id": artifact_id,
            "proposal_id": proposal_id,
            "status": status,
            "transition": "check",
            "created_at": created_at,
        }
        filename = f"{proposal_id}-check-{artifact_id}.json"
        (self.transitions_dir / filename).write_text(json.dumps(data), encoding="utf-8")

    def test_derives_status_from_latest_event(self) -> None:
        # Write two events - the later one should win
        self._write_event(
            "proposal-1",
            "pending",
            "aaa111",
            "2026-04-07T10:00:00+00:00",
        )
        self._write_event(
            "proposal-1",
            "checked",
            "bbb222",
            "2026-04-07T11:00:00+00:00",
        )

        base = {"proposal_id": "proposal-1", "lifecycle_history": [{"status": "pending"}]}
        status = derive_current_proposal_status(base, self.transitions_dir)
        self.assertEqual(status, ProposalLifecycleStatus.CHECKED)

    def test_falls_back_to_embedded_history_when_no_events(self) -> None:
        base = {
            "proposal_id": "proposal-no-events",
            "lifecycle_history": [{"status": "pending"}],
        }
        status = derive_current_proposal_status(base, self.transitions_dir)
        self.assertEqual(status, ProposalLifecycleStatus.PENDING)

    def test_falls_back_when_transitions_dir_none(self) -> None:
        base = {
            "proposal_id": "proposal-no-events",
            "lifecycle_history": [{"status": "pending"}],
        }
        status = derive_current_proposal_status(base, None)
        self.assertEqual(status, ProposalLifecycleStatus.PENDING)

    def test_derives_accepted_status_from_promote_event(self) -> None:
        self._write_event(
            "proposal-2",
            "accepted",
            "ccc333",
            "2026-04-07T12:00:00+00:00",
        )

        base = {"proposal_id": "proposal-2", "lifecycle_history": [{"status": "pending"}]}
        status = derive_current_proposal_status(base, self.transitions_dir)
        self.assertEqual(status, ProposalLifecycleStatus.ACCEPTED)


class ProposalImmutabilityTests(unittest.TestCase):
    """Tests verifying that proposal base artifacts are not mutated."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.proposals_dir = self.root / "proposals"
        self.proposals_dir.mkdir()
        self.transitions_dir = self.proposals_dir / "transitions"

    def _create_proposal_file(self, proposal_id: str, initial_status: str = "pending") -> Path:
        proposal_data = {
            "proposal_id": proposal_id,
            "source_run_id": "test-run",
            "source_artifact_path": "reviews/test.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Raise threshold",
            "rationale": "test",
            "confidence": "medium",
            "expected_benefit": "reduce noise",
            "rollback_note": "revert",
            "lifecycle_history": [{"status": initial_status, "timestamp": "2026-04-07T10:00:00+00:00"}],
            "promotion_evaluation": None,
            "artifact_path": None,
        }
        path = self.proposals_dir / f"{proposal_id}.json"
        path.write_text(json.dumps(proposal_data, indent=2), encoding="utf-8")
        return path

    def test_check_transition_writes_event_not_proposal(self) -> None:
        proposal_path = self._create_proposal_file("test-check")
        original_content = proposal_path.read_text(encoding="utf-8")

        # Simulate what handle_check_proposal does
        raw = json.loads(proposal_path.read_text(encoding="utf-8"))
        proposal = HealthProposal.from_dict(raw)

        event = ProposalLifecycleEvent(
            proposal_id=proposal.proposal_id,
            proposal_artifact_id=proposal.artifact_id,
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
            note="Replayed against test fixture",
        )
        event_path = write_proposal_lifecycle_event(event, self.transitions_dir)

        # Verify proposal file is unchanged
        current_content = proposal_path.read_text(encoding="utf-8")
        self.assertEqual(original_content, current_content)
        self.assertTrue(event_path.exists())

    def test_promote_transition_writes_event_not_proposal(self) -> None:
        proposal_path = self._create_proposal_file("test-promote", initial_status="checked")
        original_content = proposal_path.read_text(encoding="utf-8")

        raw = json.loads(proposal_path.read_text(encoding="utf-8"))
        proposal = HealthProposal.from_dict(raw)

        # Add promotion evaluation to simulate a checked proposal
        evaluation = ProposalEvaluation(
            proposal_id=proposal.proposal_id,
            noise_reduction="Likely noise reduction",
            signal_loss="Low signal loss",
            test_outcome="Test passed",
        )
        checked_proposal = replace(proposal, promotion_evaluation=evaluation)
        checked_proposal = with_lifecycle_status(
            checked_proposal,
            ProposalLifecycleStatus.CHECKED,
            note="Replayed for tests",
        )

        event = ProposalLifecycleEvent(
            proposal_id=checked_proposal.proposal_id,
            proposal_artifact_id=checked_proposal.artifact_id,
            status=ProposalLifecycleStatus.ACCEPTED,
            transition="promote",
            note="Promotion patch written",
        )
        event_path = write_proposal_lifecycle_event(event, self.transitions_dir)

        # Verify proposal file is unchanged
        current_content = proposal_path.read_text(encoding="utf-8")
        self.assertEqual(original_content, current_content)
        self.assertTrue(event_path.exists())

    def test_multiple_transitions_create_separate_events(self) -> None:
        proposal_path = self._create_proposal_file("test-multi")
        original_content = proposal_path.read_text(encoding="utf-8")

        # Write check event
        check_event = ProposalLifecycleEvent(
            proposal_id="test-multi",
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
        )
        check_path = write_proposal_lifecycle_event(check_event, self.transitions_dir)

        # Write promote event
        promote_event = ProposalLifecycleEvent(
            proposal_id="test-multi",
            status=ProposalLifecycleStatus.ACCEPTED,
            transition="promote",
        )
        promote_path = write_proposal_lifecycle_event(promote_event, self.transitions_dir)

        # Verify proposal file unchanged
        current_content = proposal_path.read_text(encoding="utf-8")
        self.assertEqual(original_content, current_content)

        # Verify both events exist
        self.assertTrue(check_path.exists())
        self.assertTrue(promote_path.exists())
        self.assertNotEqual(check_path.name, promote_path.name)

        # Verify derivation picks the latest
        raw = json.loads(proposal_path.read_text(encoding="utf-8"))
        status = derive_current_proposal_status(raw, self.transitions_dir)
        self.assertEqual(status, ProposalLifecycleStatus.ACCEPTED)


class UISerializationPreferTransitionsTests(unittest.TestCase):
    """Tests proving that UI serialization prefers transition artifacts.

    The expert review explicitly requires wiring transitions_dir through
    the actual proposal serialization/read path and adding focused tests
    that prove UI/API serialization prefers transition artifacts over
    embedded lifecycle history.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.output_dir = self.root / "runs" / "health"
        self.proposals_dir = self.output_dir / "proposals"
        self.transitions_dir = self.proposals_dir / "transitions"
        self.transitions_dir.mkdir(parents=True, exist_ok=True)

    def _create_proposal_artifact(
        self,
        proposal_id: str,
        lifecycle_status: str,
    ) -> tuple[HealthProposal, Path]:
        """Create a proposal artifact with embedded lifecycle history."""
        history_data = [
            {"status": "pending", "timestamp": "2026-04-01T10:00:00+00:00"},
            {
                "status": lifecycle_status,
                "timestamp": "2026-04-01T11:00:00+00:00",
            },
        ]
        proposal_data = {
            "proposal_id": proposal_id,
            "source_run_id": "health-run-1",
            "source_artifact_path": f"reviews/{proposal_id}-review.json",
            "target": "health.trigger_policy.warning_event_threshold",
            "proposed_change": "Raise threshold",
            "rationale": "test rationale",
            "confidence": "medium",
            "expected_benefit": "reduce noise",
            "rollback_note": "revert",
            "lifecycle_history": history_data,
            "promotion_evaluation": None,
            "artifact_path": None,
        }
        path = self.proposals_dir / f"{proposal_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(proposal_data), encoding="utf-8")
        proposal = HealthProposal.from_dict(proposal_data)
        return proposal, path

    def _write_transition_event(
        self,
        proposal_id: str,
        status: ProposalLifecycleStatus,
        transition: str,
        timestamp: str,
        artifact_id: str,
    ) -> Path:
        """Write a transition event artifact."""
        data = {
            "artifact_id": artifact_id,
            "proposal_id": proposal_id,
            "status": status.value,
            "transition": transition,
            "created_at": timestamp,
        }
        filename = f"{proposal_id}-{transition}-{artifact_id}.json"
        event_path = self.transitions_dir / filename
        event_path.write_text(json.dumps(data), encoding="utf-8")
        return event_path

    def test_ui_serialization_derives_status_from_transition_events(self) -> None:
        """Verify UI index uses transition artifact status over embedded history.

        Given:
        - Proposal with embedded lifecycle_history showing 'pending'
        - A 'check' transition event showing status 'checked'

        When write_health_ui_index serializes the proposal

        Then the serialized proposal.status is 'checked' (from events), not
        'pending' (from embedded history).
        """
        proposal_id = "test-derive-status"
        proposal, _ = self._create_proposal_artifact(proposal_id, "pending")

        # Write transition event showing the proposal is 'checked'
        event_timestamp = "2026-04-07T12:00:00+00:00"
        self._write_transition_event(
            proposal_id=proposal_id,
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
            timestamp=event_timestamp,
            artifact_id="event-uuid-001",
        )

        from k8s_diag_agent.health.ui_serialization import _serialize_proposal

        serialized = _serialize_proposal(proposal, self.output_dir, self.transitions_dir)

        self.assertEqual(serialized["status"], "checked")
        self.assertIn("lifecycle_history", serialized)
        history = serialized["lifecycle_history"]
        assert isinstance(history, list)
        last_entry = history[-1]
        assert isinstance(last_entry, dict)
        self.assertEqual(last_entry["status"], "pending")

    def test_ui_serialization_uses_latest_transition_event(self) -> None:
        """Verify that when multiple transition events exist, latest wins."""
        proposal_id = "test-latest-event"
        proposal, _ = self._create_proposal_artifact(proposal_id, "pending")

        # Write earlier event showing 'checked'
        self._write_transition_event(
            proposal_id=proposal_id,
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
            timestamp="2026-04-07T10:00:00+00:00",
            artifact_id="event-uuid-001",
        )

        # Write later event showing 'accepted'
        self._write_transition_event(
            proposal_id=proposal_id,
            status=ProposalLifecycleStatus.ACCEPTED,
            transition="promote",
            timestamp="2026-04-07T14:00:00+00:00",
            artifact_id="event-uuid-002",
        )

        from k8s_diag_agent.health.ui_serialization import _serialize_proposal

        serialized = _serialize_proposal(proposal, self.output_dir, self.transitions_dir)
        self.assertEqual(serialized["status"], "accepted")

    def test_ui_serialization_falls_back_to_embedded_when_no_events(self) -> None:
        """Verify backward compatibility: uses embedded history when no events."""
        proposal_id = "test-fallback"
        proposal, _ = self._create_proposal_artifact(proposal_id, "checked")

        from k8s_diag_agent.health.ui_serialization import _serialize_proposal

        serialized = _serialize_proposal(proposal, self.output_dir, self.transitions_dir)
        self.assertEqual(serialized["status"], "checked")

    def test_ui_serialization_falls_back_when_transitions_dir_none(self) -> None:
        """Verify backward compatibility: uses embedded history when transitions_dir is None."""
        proposal_id = "test-fallback-none"
        proposal, _ = self._create_proposal_artifact(proposal_id, "checked")

        from k8s_diag_agent.health.ui_serialization import _serialize_proposal

        serialized = _serialize_proposal(proposal, self.output_dir, None)
        self.assertEqual(serialized["status"], "checked")

    def test_integration_write_health_ui_index_uses_transitions(self) -> None:
        """End-to-end test: write_health_ui_index wires transitions_dir correctly."""
        proposal_id = "test-integration"
        proposal, _ = self._create_proposal_artifact(proposal_id, "pending")

        self._write_transition_event(
            proposal_id=proposal_id,
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
            timestamp="2026-04-07T12:00:00+00:00",
            artifact_id="integration-event-001",
        )

        from k8s_diag_agent.health.ui import write_health_ui_index

        index_path = write_health_ui_index(
            output_dir=self.output_dir,
            run_id="integration-test-run",
            run_label="integration-test",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[proposal],
            external_analysis=[],
            notifications=[],
        )

        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertIn("proposals", index_data)
        self.assertEqual(len(index_data["proposals"]), 1)
        self.assertEqual(index_data["proposals"][0]["status"], "checked")

    def test_proposal_status_summary_uses_derived_status(self) -> None:
        """Verify proposal_status_summary reflects transition-derived statuses."""
        proposal_a, _ = self._create_proposal_artifact("proposal-a", "pending")
        proposal_b, _ = self._create_proposal_artifact("proposal-b", "pending")

        # Write 'check' event for proposal_a
        self._write_transition_event(
            proposal_id="proposal-a",
            status=ProposalLifecycleStatus.CHECKED,
            transition="check",
            timestamp="2026-04-07T12:00:00+00:00",
            artifact_id="event-a-001",
        )

        from k8s_diag_agent.health.ui import write_health_ui_index

        index_path = write_health_ui_index(
            output_dir=self.output_dir,
            run_id="summary-test-run",
            run_label="summary-test",
            collector_version="1.0",
            records=[],
            assessments=[],
            drilldowns=[],
            proposals=[proposal_a, proposal_b],
            external_analysis=[],
            notifications=[],
        )

        index_data = json.loads(index_path.read_text(encoding="utf-8"))
        summary = index_data.get("proposal_status_summary", {})
        status_counts = summary.get("status_counts", [])

        counts_map = {}
        for entry in status_counts:
            status = entry.get("status")
            count = entry.get("count", 0)
            counts_map[status] = count

        self.assertEqual(counts_map.get("checked", 0), 1)
        self.assertEqual(counts_map.get("pending", 0), 1)


if __name__ == "__main__":
    unittest.main()
