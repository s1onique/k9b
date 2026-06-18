"""Tests for suggested_checks in incident detail payloads.

These tests verify:
1. handle_get_incident with plan artifact loading
2. suggested_checks field population from linked candidates
3. Handling of partial/unlinked/legacy candidates
4. Graceful handling of missing or malformed artifacts
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.collect.api_incident_reads import handle_get_incident
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import reset_incident_store, set_incident_store

from .incident_lifecycle_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate


class TestHandleGetIncidentWithPlanArtifacts(unittest.TestCase):
    """Test handle_get_incident with plan artifact loading."""

    def setUp(self) -> None:
        """Reset incident store before each test."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)
        self._tmpdir = tempfile.mkdtemp()
        self._external_dir = Path(self._tmpdir) / "external-analysis"
        self._external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Reset incident store and cleanup after each test."""
        set_incident_store(None)
        reset_incident_store()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_plan_artifact(self, run_id: str, payload: dict) -> None:
        """Write a plan artifact to the external_analysis directory."""
        path = self._external_dir / f"{run_id}-next-check-plan.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_get_incident_with_one_linked_plan_artifact(self) -> None:
        """handle_get_incident with one linked plan artifact includes suggested_checks."""

        # Create incident with signal directly - signal must be in store
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signal to the stored incident (not just the snapshot)
        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_1,
            run_id="run-123",
        )
        stored_incident.signals.append(signal)

        # Write plan artifact with linked candidate for this incident
        self._write_plan_artifact("run-123", {
            "run_id": "run-123",
            "linkage_schema_version": 1,
            "candidates": [
                {
                    "linkage_status": "linked",
                    "incident_id": incident_id,
                    "candidateId": "check-001",
                    "title": "Pod Log Inspection",
                    "description": "Check pod logs for crash loop errors",
                    "riskLevel": "LOW",
                },
            ],
        })

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertIsNotNone(result)
        self.assertIn("suggested_checks", result)
        self.assertEqual(len(result["suggested_checks"]), 1)
        self.assertEqual(result["suggested_checks"][0]["check_id"], "check-001")
        self.assertEqual(result["suggested_checks"][0]["title"], "Pod Log Inspection")

    def test_get_incident_with_two_linked_plan_artifacts(self) -> None:
        """handle_get_incident with two linked plan artifacts includes both suggestions."""

        # Create incident with signals for two runs
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signals to the stored incident (not just the snapshot)
        stored_incident = self._test_store._incidents[incident_id]
        signal1 = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_1,
            run_id="run-1",
        )
        signal2 = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting again",
            captured_at=TEST_TIME_2,
            run_id="run-2",
        )
        stored_incident.signals.extend([signal1, signal2])

        # Write plan artifacts for both runs
        self._write_plan_artifact("run-1", {
            "run_id": "run-1",
            "linkage_schema_version": 1,
            "candidates": [
                {
                    "linkage_status": "linked",
                    "incident_id": incident_id,
                    "candidateId": "check-001",
                    "title": "Check 1",
                },
            ],
        })
        self._write_plan_artifact("run-2", {
            "run_id": "run-2",
            "linkage_schema_version": 1,
            "candidates": [
                {
                    "linkage_status": "linked",
                    "incident_id": incident_id,
                    "candidateId": "check-002",
                    "title": "Check 2",
                },
            ],
        })

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertIsNotNone(result)
        self.assertEqual(len(result["suggested_checks"]), 2)
        # Deterministic order: run-1 first, then run-2
        self.assertEqual(result["suggested_checks"][0]["check_id"], "check-001")
        self.assertEqual(result["suggested_checks"][1]["check_id"], "check-002")

    def test_get_incident_ignores_partial_unlinked_candidates(self) -> None:
        """handle_get_incident must ignore partial/unlinked/legacy candidates."""

        # Create incident
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signal
        incident.signals.append(IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_1,
            run_id="run-123",
        ))

        # Write plan with mixed candidates
        self._write_plan_artifact("run-123", {
            "run_id": "run-123",
            "linkage_schema_version": 1,
            "candidates": [
                {"linkage_status": "partial", "candidateId": "check-001"},  # Partial - ignored
                {"linkage_status": "unlinked", "candidateId": "check-002"},  # Unlinked - ignored
                {"candidateId": "check-003"},  # Legacy - ignored
                {"linkage_status": "linked", "incident_id": "different-incident", "candidateId": "check-004"},  # Different incident - ignored
            ],
        })

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertIsNotNone(result)
        self.assertEqual(len(result["suggested_checks"]), 0)

    def test_get_incident_suggested_checks_empty_when_artifact_missing(self) -> None:
        """handle_get_incident remains suggested_checks: [] when artifact is missing."""
        # Create incident with signal
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signal with run_id (but no artifact exists)
        incident.signals.append(IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_1,
            run_id="nonexistent-run",
        ))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertIsNotNone(result)
        self.assertEqual(result["suggested_checks"], [])

    def test_get_incident_malformed_plan_artifact_does_not_fail(self) -> None:
        """Malformed plan artifact must not fail incident detail response."""
        # Create incident with signal
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        # Add signal
        incident.signals.append(IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_1,
            run_id="run-123",
        ))

        # Write malformed artifact
        malformed_path = self._external_dir / "run-123-next-check-plan.json"
        malformed_path.write_text("{ invalid }", encoding="utf-8")

        # Should not raise
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertIsNotNone(result)
        self.assertEqual(result["suggested_checks"], [])

    def test_get_incident_without_external_analysis_dir(self) -> None:
        """handle_get_incident without external_analysis_dir returns empty suggested_checks."""
        # Create incident with signal
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident_id = incidents[0].incident_id

        # Don't provide external_analysis_dir
        result = handle_get_incident(incident_id, external_analysis_dir=None)

        self.assertIsNotNone(result)
        self.assertEqual(result["suggested_checks"], [])

    def test_get_incident_no_old_fields(self) -> None:
        """handle_get_incident must not reintroduce old incident fields."""
        # Create incident
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident_id = incidents[0].incident_id

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        self.assertIsNotNone(result)
        # Old fields must not be present
        self.assertNotIn("review_packet_available", result)
        self.assertNotIn("review_packet_id", result)
        self.assertNotIn("snapshot_bundle_id", result)


if __name__ == "__main__":
    unittest.main()
