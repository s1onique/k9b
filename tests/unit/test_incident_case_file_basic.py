"""Basic tests for incident case-file packet builder.

Tests:
1. Valid incident produces a case-file packet
2. Packet includes incident identity and lifecycle/status fields
3. Packet includes incident signals and run IDs
4. Packet includes explicit read-only safety metadata
5. Unknown incident returns None
6. Output is deterministic with injected now
7. Packet generation does not mutate the incident store
"""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_case_file import (
    DISALLOWED_ACTIONS,
    PACKET_SCHEMA_VERSION,
    build_incident_case_file,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

from .incident_lifecycle_fixtures import (
    TEST_TIME_1,
    TEST_TIME_2,
    make_candidate,
)


class TestIncidentCaseFileBasic(unittest.TestCase):
    """Basic case-file packet tests."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)

    def tearDown(self) -> None:
        """Clean up after each test."""
        set_incident_store(None)
        reset_incident_store()

    def test_valid_incident_produces_case_file_packet(self) -> None:
        """Valid incident produces a case-file packet."""
        # Create incident via candidate promotion
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Build case file
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None  # for mypy

        # Verify basic structure
        self.assertIn("schema_version", packet)
        self.assertIn("generated_at", packet)
        self.assertIn("read_only", packet)
        self.assertIn("allowed_actions", packet)
        self.assertIn("disallowed_actions", packet)
        self.assertIn("incident", packet)
        self.assertIn("signals", packet)
        self.assertIn("evidence_links", packet)
        self.assertIn("events", packet)
        self.assertIn("suggested_checks", packet)

    def test_packet_includes_incident_identity_fields(self) -> None:
        """Packet includes incident identity and lifecycle/status fields."""
        candidate = make_candidate(name="identity-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check incident identity section
        inc = packet["incident"]
        self.assertEqual(inc["incident_id"], incident_id)
        self.assertEqual(inc["namespace"], "default")
        self.assertEqual(inc["object_kind"], "Pod")
        self.assertEqual(inc["object_name"], "identity-pod")
        self.assertIn("severity", inc)
        self.assertIn("status", inc)
        self.assertIn("first_observed_at", inc)
        self.assertIn("last_observed_at", inc)

    def test_packet_includes_signals_with_run_ids(self) -> None:
        """Packet includes incident signals and run IDs."""
        candidate = make_candidate(name="signal-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signal with run_id to the stored incident
        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_2,
            run_id="run-signal-001",
        )
        stored_incident.signals.append(signal)

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check signals
        self.assertIsInstance(packet["signals"], list)
        self.assertGreater(len(packet["signals"]), 0)

        # Find the signal with run_id
        signal_with_run_id = None
        for sig in packet["signals"]:
            if sig.get("run_id") == "run-signal-001":
                signal_with_run_id = sig
                break

        self.assertIsNotNone(signal_with_run_id)
        assert signal_with_run_id is not None
        self.assertEqual(signal_with_run_id["source"], "pod")
        self.assertEqual(signal_with_run_id["reason"], "CrashLoopBackOff")
        self.assertEqual(signal_with_run_id["run_id"], "run-signal-001")

    def test_packet_includes_explicit_read_only_safety_metadata(self) -> None:
        """Packet includes explicit read-only safety metadata."""
        candidate = make_candidate(name="safety-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check explicit read-only flag
        self.assertEqual(packet["read_only"], True)

        # Check allowed_actions is empty
        self.assertEqual(packet["allowed_actions"], [])

        # Check disallowed_actions includes mutation/remediation verbs
        self.assertIn("disallowed_actions", packet)
        disallowed = packet["disallowed_actions"]
        self.assertIsInstance(disallowed, list)
        self.assertIn("execute", disallowed)
        self.assertIn("promote", disallowed)
        self.assertIn("apply", disallowed)
        self.assertIn("remediate", disallowed)
        self.assertIn("delete", disallowed)
        self.assertIn("mutate_cluster", disallowed)

    def test_unknown_incident_returns_none(self) -> None:
        """Unknown incident returns None."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file("non-existent-incident", now=now)

        self.assertIsNone(packet)

    def test_output_is_deterministic_with_injected_now(self) -> None:
        """Output is deterministic with injected now."""
        candidate = make_candidate(name="deterministic-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        # Build twice with same now
        packet1 = build_incident_case_file(incident_id, now=now)
        packet2 = build_incident_case_file(incident_id, now=now)

        self.assertIsNotNone(packet1)
        self.assertIsNotNone(packet2)
        assert packet1 is not None and packet2 is not None

        # generated_at should be deterministic
        self.assertEqual(packet1["generated_at"], packet2["generated_at"])
        self.assertEqual(packet1["generated_at"], "2024-06-01T12:00:00+00:00")

        # Full packet should be identical
        self.assertEqual(json.dumps(packet1, sort_keys=True), json.dumps(packet2, sort_keys=True))

    def test_packet_generation_does_not_mutate_store(self) -> None:
        """Packet generation does not mutate the incident store."""
        candidate = make_candidate(name="mutation-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Get initial state
        initial_incident = self._test_store.get_incident(incident_id)
        assert initial_incident is not None
        initial_signal_count = len(initial_incident.signals)
        initial_status = initial_incident.status

        # Build case file multiple times
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        for _ in range(3):
            packet = build_incident_case_file(incident_id, now=now)
            self.assertIsNotNone(packet)

        # State should be unchanged
        final_incident = self._test_store.get_incident(incident_id)
        assert final_incident is not None
        self.assertEqual(len(final_incident.signals), initial_signal_count)
        self.assertEqual(final_incident.status, initial_status)

    def test_schema_version_is_defined(self) -> None:
        """PACKET_SCHEMA_VERSION is defined."""
        self.assertEqual(PACKET_SCHEMA_VERSION, "1.0")
        self.assertIsInstance(PACKET_SCHEMA_VERSION, str)

    def test_disallowed_actions_are_defined(self) -> None:
        """DISALLOWED_ACTIONS list is defined with required verbs."""
        expected_actions = {"execute", "promote", "apply", "remediate", "delete", "mutate_cluster"}
        self.assertEqual(set(DISALLOWED_ACTIONS), expected_actions)


if __name__ == "__main__":
    unittest.main()
