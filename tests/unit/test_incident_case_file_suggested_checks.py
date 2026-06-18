"""Tests for incident case-file packet suggested checks linkage.

Tests:
1. Packet includes linked suggested checks from safe next-check artifacts
2. Packet excludes unsafe/unlinked/wrong-run suggested checks
3. Packet bounds suggested checks count
4. Multiple artifacts produce multiple suggested checks
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from k8s_diag_agent.collect.incident_case_file import build_incident_case_file
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal

from .incident_detail_suggested_checks_fixtures import (
    IncidentSuggestedChecksHarness,
    make_legacy_next_check_plan_artifact,
    make_partial_next_check_plan_artifact,
    make_valid_next_check_plan_artifact,
    make_wrong_incident_next_check_plan_artifact,
)
from .incident_lifecycle_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate


class TestIncidentCaseFileSuggestedChecks(
    IncidentSuggestedChecksHarness,
    unittest.TestCase,
):
    """Tests for case-file packet suggested checks linkage."""

    def test_packet_includes_linked_suggested_checks(self) -> None:
        """Packet includes linked suggested checks from safe next-check artifacts."""
        # Create incident with signal
        incident_id = self.create_incident_with_signal("run-linked-001")
        run_id = "run-linked-001"

        # Write valid artifact with linked candidate
        artifact = make_valid_next_check_plan_artifact(
            run_id=run_id,
            incident_id=incident_id,
            candidate_id="check-pod-logs",
            title="Inspect pod logs",
            rationale="CrashLoopBackOff logs are informative",
            risk_level="LOW",
        )
        self.write_plan_artifact(run_id, artifact)

        # Build case file
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, external_analysis_dir=self._external_dir, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check suggested_checks is populated
        self.assertIn("suggested_checks", packet)
        suggested = packet["suggested_checks"]
        self.assertIsInstance(suggested, list)
        self.assertEqual(len(suggested), 1)

        # Check check content
        check = suggested[0]
        self.assertEqual(check["check_id"], "check-pod-logs")
        self.assertEqual(check["title"], "Inspect pod logs")
        self.assertEqual(check["rationale"], "CrashLoopBackOff logs are informative")
        self.assertEqual(check["source"], "next-check-plan")
        self.assertEqual(check["risk_level"], "LOW")
        self.assertEqual(check["status"], "suggested")

    def test_packet_excludes_partial_unlinked_suggested_checks(self) -> None:
        """Packet excludes partial/unlinked suggested checks."""
        incident_id = self.create_incident_with_signal("run-partial-001")

        # Write artifact with partial candidates (no linked check)
        artifact = make_partial_next_check_plan_artifact("run-partial-001")
        self.write_plan_artifact("run-partial-001", artifact)

        # Build case file
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, external_analysis_dir=self._external_dir, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check suggested_checks is empty (partial/unlinked filtered out)
        self.assertEqual(len(packet["suggested_checks"]), 0)

    def test_packet_excludes_wrong_incident_suggested_checks(self) -> None:
        """Packet excludes suggested checks linked to wrong incident."""
        # Create incident
        incident_id = self.create_incident_with_signal("run-wrong-001")
        wrong_incident_id = "wrong-incident-xyz"

        # Write artifact with candidate linked to wrong incident
        artifact = make_wrong_incident_next_check_plan_artifact("run-wrong-001", wrong_incident_id)
        self.write_plan_artifact("run-wrong-001", artifact)

        # Build case file
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, external_analysis_dir=self._external_dir, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check suggested_checks is empty (wrong incident filtered out)
        self.assertEqual(len(packet["suggested_checks"]), 0)

    def test_packet_excludes_legacy_artifact_suggested_checks(self) -> None:
        """Packet excludes suggested checks from legacy artifacts without linkage fields."""
        incident_id = self.create_incident_with_signal("run-legacy-001")

        # Write legacy artifact (no linkage fields)
        artifact = make_legacy_next_check_plan_artifact("run-legacy-001")
        self.write_plan_artifact("run-legacy-001", artifact)

        # Build case file
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, external_analysis_dir=self._external_dir, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check suggested_checks is empty (legacy format has no linkage)
        self.assertEqual(len(packet["suggested_checks"]), 0)

    def test_packet_bounds_suggested_checks_count(self) -> None:
        """Packet bounds suggested checks count to max_suggested_checks."""
        # Create incident with signal
        candidate = make_candidate(name="bound-check-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        stored_incident.signals.extend([
            IncidentSignal(
                source="pod", reason="CrashLoopBackOff", message="restart",
                captured_at=TEST_TIME_1, run_id=f"run-bound-{i}",
            )
            for i in range(10)
        ])

        # Write artifacts for 10 runs
        for i in range(10):
            artifact = make_valid_next_check_plan_artifact(
                run_id=f"run-bound-{i}",
                incident_id=incident_id,
                candidate_id=f"check-{i}",
            )
            self.write_plan_artifact(f"run-bound-{i}", artifact)

        # Build with max_suggested_checks=3
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
            max_suggested_checks=3,
        )

        self.assertIsNotNone(packet)
        assert packet is not None

        # Check bounded to 3
        self.assertEqual(len(packet["suggested_checks"]), 3)

    def test_multiple_artifacts_produce_multiple_suggested_checks(self) -> None:
        """Incident with signals from multiple runs produces checks from all linked artifacts."""
        # Create incident with signals from two runs
        candidate = make_candidate(name="multi-artifact-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        stored_incident.signals.extend([
            IncidentSignal(
                source="pod", reason="CrashLoopBackOff", message="restart 1",
                captured_at=TEST_TIME_1, run_id="run-multi-1",
            ),
            IncidentSignal(
                source="pod", reason="CrashLoopBackOff", message="restart 2",
                captured_at=TEST_TIME_2, run_id="run-multi-2",
            ),
        ])

        # Write artifacts for both runs
        self.write_plan_artifact("run-multi-1", make_valid_next_check_plan_artifact(
            run_id="run-multi-1",
            incident_id=incident_id,
            candidate_id="check-multi-1",
            title="Check from run 1",
        ))
        self.write_plan_artifact("run-multi-2", make_valid_next_check_plan_artifact(
            run_id="run-multi-2",
            incident_id=incident_id,
            candidate_id="check-multi-2",
            title="Check from run 2",
        ))

        # Build case file
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, external_analysis_dir=self._external_dir, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # Should have checks from both artifacts
        self.assertEqual(len(packet["suggested_checks"]), 2)
        check_ids = [c["check_id"] for c in packet["suggested_checks"]]
        self.assertIn("check-multi-1", check_ids)
        self.assertIn("check-multi-2", check_ids)

    def test_packet_works_without_external_analysis_dir(self) -> None:
        """Packet works without external_analysis_dir (returns empty suggested_checks)."""
        incident_id = self.create_incident_with_signal("run-no-dir")

        # Build case file without external_analysis_dir
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        packet = build_incident_case_file(incident_id, now=now)

        self.assertIsNotNone(packet)
        assert packet is not None

        # suggested_checks should be empty
        self.assertEqual(packet["suggested_checks"], [])


if __name__ == "__main__":
    unittest.main()
