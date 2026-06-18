"""Safety tests for incident case-file packet.

Tests:
1. Packet does not contain action-control fields (run, execute, promote, apply, remediate)
2. Packet is read-only and does not mutate store
3. Suggested checks have no execution fields
4. Safety metadata is explicit
5. Bounded counts prevent resource exhaustion
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_case_file import (
    DISALLOWED_ACTIONS,
    build_incident_case_file,
)
from k8s_diag_agent.collect.incident_lifecycle import (
    IncidentEvent,
    IncidentEventActor,
    IncidentEventType,
    IncidentSignal,
    make_event_id,
)
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

from .incident_detail_suggested_checks_fixtures import (
    IncidentSuggestedChecksHarness,
    make_valid_next_check_plan_artifact,
)
from .incident_lifecycle_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate

# Fields that should NOT appear in suggested_check payload
FORBIDDEN_ACTION_FIELDS: list[str] = [
    "run",
    "execute",
    "promote",
    "apply",
    "remediate",
    "action",
    "run_command",
    "execute_command",
    "approve",
    "reject",
]


class TestIncidentCaseFileSafety(unittest.TestCase):
    """Safety tests for incident case-file packet."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Clean up after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_packet_does_not_contain_action_control_fields(self) -> None:
        """Packet does not contain action-control fields."""
        # Create incident
        candidate = make_candidate(name="action-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check top-level packet
        for field in FORBIDDEN_ACTION_FIELDS:
            self.assertNotIn(field, packet, f"Field '{field}' should not be in packet top-level")

        # Check incident section
        inc = packet["incident"]
        for field in FORBIDDEN_ACTION_FIELDS:
            self.assertNotIn(field, inc, f"Field '{field}' should not be in incident section")

    def test_suggested_checks_have_no_execution_fields(self) -> None:
        """Suggested checks have no execution fields."""
        # Create incident harness for artifact-based test
        harness = IncidentSuggestedChecksHarness()
        harness.setUp()

        try:
            incident_id = harness.create_incident_with_signal("run-safety-001")

            # Write valid artifact
            artifact = make_valid_next_check_plan_artifact(
                run_id="run-safety-001",
                incident_id=incident_id,
                candidate_id="check-safety",
            )
            harness.write_plan_artifact("run-safety-001", artifact)

            # Build case file
            now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
            packet = build_incident_case_file(
                incident_id,
                external_analysis_dir=harness._external_dir,
                now=now,
            )

            self.assertIsNotNone(packet)
            assert packet is not None

            # Check suggested checks
            self.assertEqual(len(packet["suggested_checks"]), 1)
            check = packet["suggested_checks"][0]

            # No execution fields allowed
            for field in FORBIDDEN_ACTION_FIELDS:
                self.assertNotIn(field, check, f"Field '{field}' should not be in suggested_check")

            # Status should be "suggested" (read-only state)
            self.assertEqual(check["status"], "suggested")
        finally:
            harness.tearDown()

    def test_packet_is_read_only(self) -> None:
        """Packet has explicit read_only: true."""
        candidate = make_candidate(name="readonly-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        self.assertEqual(packet["read_only"], True)
        self.assertEqual(packet["allowed_actions"], [])
        self.assertIn("disallowed_actions", packet)
        self.assertIsInstance(packet["disallowed_actions"], list)

    def test_disallowed_actions_contains_required_verbs(self) -> None:
        """disallowed_actions contains all required mutation/remediation verbs."""
        required = {"execute", "promote", "apply", "remediate", "delete", "mutate_cluster"}
        self.assertEqual(set(DISALLOWED_ACTIONS), required)

    def test_packet_does_not_mutate_incident_store(self) -> None:
        """Packet generation does not mutate the incident store."""
        candidate = make_candidate(name="mutation-test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add a signal
        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_2,
            run_id="run-mutation",
        )
        stored_incident.signals.append(signal)

        # Record initial state
        initial = self._test_store.get_incident(incident_id)
        assert initial is not None
        initial_signal_count = len(initial.signals)
        initial_events_count = len(initial.events)
        initial_status = initial.status

        # Build packet multiple times
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        for _ in range(5):
            packet = build_incident_case_file(incident_id, now=now)
            self.assertIsNotNone(packet)

        # Verify store state unchanged
        final = self._test_store.get_incident(incident_id)
        assert final is not None
        self.assertEqual(len(final.signals), initial_signal_count)
        self.assertEqual(len(final.events), initial_events_count)
        self.assertEqual(final.status, initial_status)

    def test_bounded_signals_count(self) -> None:
        """Signals are bounded to max_signals."""
        candidate = make_candidate(name="bound-signals-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        # Add many signals
        for i in range(30):
            stored_incident.signals.append(IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message=f"restart {i}",
                captured_at=TEST_TIME_1,
                run_id=f"run-{i}",
            ))

        # Build with max_signals=5
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now, max_signals=5)

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(len(packet["signals"]), 5)

    def test_bounded_events_count(self) -> None:
        """Timeline events are bounded to max_events."""
        candidate = make_candidate(name="bound-events-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        # Add many events (must be IncidentEvent, not IncidentSignal)
        for i in range(60):
            stored_incident.events.append(IncidentEvent(
                event_id=make_event_id(incident_id, f"test_event_{i}", TEST_TIME_1),
                incident_id=incident_id,
                event_type=IncidentEventType.STATUS_CHANGED,
                actor=IncidentEventActor.SYSTEM,
                occurred_at=TEST_TIME_1,
                message=f"event {i}",
            ))

        # Build with max_events=10
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now, max_events=10)

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(len(packet["events"]), 10)


class TestIncidentCaseFileSafetyWithArtifacts(
    IncidentSuggestedChecksHarness,
    unittest.TestCase,
):
    """Safety tests that require artifact loading."""

    def test_packet_with_artifact_has_no_unsafe_paths(self) -> None:
        """Packet with artifact does not expose unsafe paths."""
        incident_id = self.create_incident_with_signal("run-safe-path")

        # Write valid artifact
        artifact = make_valid_next_check_plan_artifact(
            run_id="run-safe-path",
            incident_id=incident_id,
            candidate_id="check-safe",
        )
        self.write_plan_artifact("run-safe-path", artifact)

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check suggested checks don't have unsafe fields
        for check in packet["suggested_checks"]:
            # No path fields that could expose filesystem
            self.assertNotIn("path", check)
            self.assertNotIn("file_path", check)
            self.assertNotIn("unsafe", check)

    def test_malformed_artifact_handled_gracefully(self) -> None:
        """Malformed artifact is handled gracefully (no crash)."""
        incident_id = self.create_incident_with_signal("run-malformed")

        # Write malformed artifact
        self.write_malformed_artifact("run-malformed", "{ invalid json }")

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        # Should not crash, returns packet with empty suggested_checks
        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(packet["suggested_checks"], [])


if __name__ == "__main__":
    unittest.main()
