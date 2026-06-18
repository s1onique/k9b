"""Tests for signal serialization in incident detail payloads."""

from __future__ import annotations

import unittest

from k8s_diag_agent.ui.api_incident_reads import build_incident_signal_payload

from .incident_lifecycle_fixtures import TEST_TIME_1


class TestBuildIncidentSignalPayload(unittest.TestCase):
    """Test signal serialization."""

    def test_signal_serialization(self) -> None:
        """Signal must be serialized correctly."""
        from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal

        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="back-off restarting",
            captured_at=TEST_TIME_1,
            run_id="run-123",
        )
        result = build_incident_signal_payload(signal)

        self.assertEqual(result["source"], "pod")
        self.assertEqual(result["reason"], "CrashLoopBackOff")
        self.assertEqual(result["message"], "back-off restarting")
        self.assertIn("captured_at", result)
        self.assertEqual(result["run_id"], "run-123")


if __name__ == "__main__":
    unittest.main()
