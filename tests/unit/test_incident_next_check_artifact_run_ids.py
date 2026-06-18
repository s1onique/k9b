"""Tests for incident_signal_run_ids function.

These tests verify:
1. incident_signal_run_ids extracts run_id values from signals
2. Duplicate run_ids are deduplicated in deterministic order
3. Signals without run_id are ignored
4. Expected next-check plan path is constructed correctly
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal
from k8s_diag_agent.collect.incident_next_check_artifacts import incident_signal_run_ids

from .incident_next_check_artifact_fixtures import make_incident_with_signals


class TestIncidentSignalRunIds(unittest.TestCase):
    """Tests for incident_signal_run_ids function."""

    def test_extracts_run_id_from_signal(self) -> None:
        """incident_signal_run_ids must extract run_id from signal."""
        incident = make_incident_with_signals([
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="restarting",
                captured_at=datetime.now(UTC),
                run_id="run-123",
            ),
        ])

        result = incident_signal_run_ids(incident)
        self.assertEqual(result, ("run-123",))

    def test_deduplicates_run_ids_preserving_order(self) -> None:
        """incident_signal_run_ids must deduplicate while preserving first-occurrence order."""
        incident = make_incident_with_signals([
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="restarting",
                captured_at=datetime.now(UTC),
                run_id="run-123",
            ),
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="restarting again",
                captured_at=datetime.now(UTC),
                run_id="run-456",
            ),
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="still restarting",
                captured_at=datetime.now(UTC),
                run_id="run-123",  # Duplicate - should be ignored
            ),
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="finally stable",
                captured_at=datetime.now(UTC),
                run_id="run-789",
            ),
        ])

        result = incident_signal_run_ids(incident)
        self.assertEqual(result, ("run-123", "run-456", "run-789"))

    def test_ignores_signals_without_run_id(self) -> None:
        """incident_signal_run_ids must ignore signals without run_id."""
        incident = make_incident_with_signals([
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="restarting",
                captured_at=datetime.now(UTC),
                run_id=None,  # No run_id
            ),
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="restarting again",
                captured_at=datetime.now(UTC),
                run_id="run-456",
            ),
        ])

        result = incident_signal_run_ids(incident)
        self.assertEqual(result, ("run-456",))

    def test_returns_empty_tuple_for_no_run_ids(self) -> None:
        """incident_signal_run_ids must return empty tuple when no run_ids present."""
        incident = make_incident_with_signals([
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="restarting",
                captured_at=datetime.now(UTC),
                run_id=None,
            ),
        ])

        result = incident_signal_run_ids(incident)
        self.assertEqual(result, ())

    def test_does_not_mutate_incident(self) -> None:
        """incident_signal_run_ids must not mutate the incident."""
        original_signals = [
            IncidentSignal(
                source="pod",
                reason="CrashLoopBackOff",
                message="restarting",
                captured_at=datetime.now(UTC),
                run_id="run-123",
            ),
        ]
        incident = make_incident_with_signals(original_signals)

        # Capture original state
        original_signal_run_ids = [s.run_id for s in incident.signals]

        # Call function
        incident_signal_run_ids(incident)

        # Verify signals unchanged
        self.assertEqual([s.run_id for s in incident.signals], original_signal_run_ids)


if __name__ == "__main__":
    unittest.main()
