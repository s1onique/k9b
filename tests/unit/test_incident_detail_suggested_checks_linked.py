"""Positive/read-only tests for incident detail suggested_checks.

Tests:
- Valid linked artifact produces suggested check
- Multiple linked candidates from same artifact
- Multiple runs produce multiple suggested checks
- No execution controls in suggested checks
- Incident detail does not mutate store
- External analysis dir not required

These tests validate the happy path for the suggested_checks feature
while ensuring read-only behavior is preserved.
"""

from __future__ import annotations

import unittest

from k8s_diag_agent.collect.api_incident_reads import handle_get_incident
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal

from .incident_detail_suggested_checks_fixtures import (
    IncidentSuggestedChecksHarness,
    make_valid_next_check_plan_artifact,
)
from .incident_lifecycle_fixtures import TEST_TIME_1, TEST_TIME_2, make_candidate


class TestIncidentDetailSuggestedChecksLinked(
    IncidentSuggestedChecksHarness,
    unittest.TestCase,
):
    """Positive case tests for incident detail suggested_checks.

    Tests the full production path from incident creation through
    artifact loading to API response.
    """

    def test_valid_linked_artifact_produces_suggested_check(self) -> None:
        """Valid linked next-check-plan artifact produces suggested_checks in incident detail."""
        # Create incident with signal
        incident_id = self.create_incident_with_signal("run-valid-001")
        run_id = "run-valid-001"

        # Write valid artifact with linked candidate for this incident
        artifact = make_valid_next_check_plan_artifact(
            run_id=run_id,
            incident_id=incident_id,
            candidate_id="check-pod-logs",
            title="Inspect pod logs for test-pod",
            rationale="CrashLoopBackOff typically leaves informative logs",
            risk_level="LOW",
        )
        self.write_plan_artifact(run_id, artifact)

        # Fetch incident detail through production API path
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Assert suggested_checks is populated
        self.assertIsNotNone(result)
        assert result is not None  # for mypy
        self.assertIn("suggested_checks", result)
        self.assertEqual(len(result["suggested_checks"]), 1)

        # Assert check content
        check = result["suggested_checks"][0]
        self.assertEqual(check["check_id"], "check-pod-logs")
        self.assertEqual(check["title"], "Inspect pod logs for test-pod")
        self.assertEqual(check["rationale"], "CrashLoopBackOff typically leaves informative logs")
        self.assertEqual(check["source"], "next-check-plan")
        self.assertEqual(check["risk_level"], "LOW")
        self.assertEqual(check["status"], "suggested")

    def test_multiple_linked_candidates_from_same_artifact(self) -> None:
        """Artifact with multiple linked candidates produces multiple suggested_checks."""
        incident_id = self.create_incident_with_signal("run-multi-001")

        # Write artifact with multiple linked candidates
        artifact = {
            "run_id": "run-multi-001",
            "linkage_schema_version": 1,
            "candidates": [
                {
                    "linkage_status": "linked",
                    "incident_id": incident_id,
                    "candidateId": "check-001",
                    "title": "Check pod logs",
                    "rationale": "First diagnostic step",
                    "riskLevel": "LOW",
                },
                {
                    "linkage_status": "linked",
                    "incident_id": incident_id,
                    "candidateId": "check-002",
                    "title": "Describe deployment",
                    "rationale": "Check replica status",
                    "riskLevel": "MEDIUM",
                },
            ],
        }
        self.write_plan_artifact("run-multi-001", artifact)

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)
        assert result is not None
        self.assertEqual(len(result["suggested_checks"]), 2)
        check_ids = [c["check_id"] for c in result["suggested_checks"]]
        self.assertIn("check-001", check_ids)
        self.assertIn("check-002", check_ids)

    def test_multiple_runs_produce_multiple_suggested_checks(self) -> None:
        """Incident with signals from multiple runs produces checks from all linked artifacts."""
        # Create incident with signals from two runs
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        stored_incident.signals.extend([
            IncidentSignal(
                source="pod", reason="CrashLoopBackOff", message="restarting",
                captured_at=TEST_TIME_1, run_id="run-1",
            ),
            IncidentSignal(
                source="pod", reason="CrashLoopBackOff", message="restarting again",
                captured_at=TEST_TIME_2, run_id="run-2",
            ),
        ])

        # Write artifacts for both runs
        self.write_plan_artifact("run-1", make_valid_next_check_plan_artifact(
            run_id="run-1", incident_id=incident_id, candidate_id="check-001",
        ))
        self.write_plan_artifact("run-2", make_valid_next_check_plan_artifact(
            run_id="run-2", incident_id=incident_id, candidate_id="check-002",
        ))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should have checks from both artifacts
        self.assertEqual(len(result["suggested_checks"]), 2)
        check_ids = [c["check_id"] for c in result["suggested_checks"]]
        self.assertIn("check-001", check_ids)
        self.assertIn("check-002", check_ids)

    def test_no_execution_controls_in_suggested_checks(self) -> None:
        """Suggested checks do not include execution controls (Run, Execute, Promote, etc.)."""
        incident_id = self.create_incident_with_signal("run-controls")
        self.write_plan_artifact("run-controls", make_valid_next_check_plan_artifact(
            run_id="run-controls",
            incident_id=incident_id,
        ))

        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Check that the payload structure doesn't include action fields
        check = result["suggested_checks"][0]

        # These fields should NOT exist in suggested_check payload
        self.assertNotIn("run", check)
        self.assertNotIn("execute", check)
        self.assertNotIn("promote", check)
        self.assertNotIn("apply", check)
        self.assertNotIn("remediate", check)
        self.assertNotIn("action", check)

        # Status should be "suggested" (read-only state)
        self.assertEqual(check["status"], "suggested")

    def test_incident_detail_does_not_mutate_store(self) -> None:
        """handle_get_incident does not mutate the incident store."""
        incident_id = self.create_incident_with_signal("run-mutation")

        # Get initial state
        initial_signal_count = len(self._test_store.get_incident(incident_id).signals)

        # Fetch incident detail
        self.write_plan_artifact("run-mutation", make_valid_next_check_plan_artifact(
            run_id="run-mutation",
            incident_id=incident_id,
        ))
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # State should be unchanged
        final_signal_count = len(self._test_store.get_incident(incident_id).signals)
        self.assertEqual(initial_signal_count, final_signal_count)

        # Result should still have suggested_checks from artifact
        self.assertEqual(len(result["suggested_checks"]), 1)

    def test_external_analysis_dir_not_required(self) -> None:
        """handle_get_incident works without external_analysis_dir (returns empty suggested_checks)."""
        incident_id = self.create_incident_with_signal("run-no-dir")

        # No external_analysis_dir provided
        result = handle_get_incident(incident_id, external_analysis_dir=None)

        self.assertEqual(result["suggested_checks"], [])


if __name__ == "__main__":
    unittest.main()
