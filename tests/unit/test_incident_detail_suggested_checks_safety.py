"""Safety tests for incident detail suggested_checks.

Tests:
- Unsafe run_id with path traversal is rejected
- Unsafe run_id with absolute path is rejected
- Unsafe run_id with glob metacharacter is rejected

These tests ensure that malicious or malformed run_ids cannot
leak artifacts from outside the external-analysis directory.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from k8s_diag_agent.collect.api_incident_reads import handle_get_incident
from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal

from .incident_detail_suggested_checks_fixtures import IncidentSuggestedChecksHarness
from .incident_lifecycle_fixtures import TEST_TIME_1, make_candidate


class TestIncidentDetailSuggestedChecksSafety(
    IncidentSuggestedChecksHarness,
    unittest.TestCase,
):
    """Safety-specific tests for suggested_checks extraction.

    Ensures that unsafe run_ids and malicious paths cannot leak into
    incident detail suggested_checks.
    """

    def create_incident_with_signal(self, run_id: str) -> str:
        """Create an incident with a signal in the store."""
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="CrashLoopBackOff",
            message="restarting",
            captured_at=TEST_TIME_1,
            run_id=run_id,
        )
        stored_incident.signals.append(signal)

        return incident_id

    def test_unsafe_run_id_with_path_traversal_is_rejected(self) -> None:
        """run_id with path traversal (../) is rejected and doesn't leak artifacts."""
        incident_id = self.create_incident_with_signal("../etc/passwd")

        # Create a file that should NOT be accessible
        etc_dir = Path(self._tmpdir).parent / "etc"
        etc_dir.mkdir(parents=True, exist_ok=True)
        (etc_dir / "passwd").write_text("malicious content", encoding="utf-8")

        # Try to access via path traversal run_id
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should be empty (unsafe run_id was rejected)
        self.assertEqual(result["suggested_checks"], [])

    def test_unsafe_run_id_with_absolute_path_is_rejected(self) -> None:
        """run_id that is an absolute path is rejected."""
        incident_id = self.create_incident_with_signal("/tmp/malicious")

        # Create artifact in /tmp
        malicious_dir = Path(self._tmpdir).parent / "tmp"
        malicious_dir.mkdir(parents=True, exist_ok=True)
        malicious_path = malicious_dir / "malicious-next-check-plan.json"
        malicious_path.write_text(json.dumps({
            "run_id": "/tmp/malicious",
            "linkage_schema_version": 1,
            "candidates": [{
                "linkage_status": "linked",
                "incident_id": incident_id,
                "candidateId": "malicious-check",
                "title": "Malicious check",
            }],
        }), encoding="utf-8")

        try:
            # Try to access via absolute path run_id
            result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

            # Should be empty (unsafe run_id was rejected)
            self.assertEqual(result["suggested_checks"], [])
        finally:
            # Cleanup
            malicious_path.unlink(missing_ok=True)

    def test_unsafe_run_id_with_glob_metacharacter_is_rejected(self) -> None:
        """run_id with glob metacharacters is rejected."""
        incident_id = self.create_incident_with_signal("run-*")

        # Create artifact in external-analysis (should NOT be accessed)
        self._external_dir.mkdir(parents=True, exist_ok=True)
        (self._external_dir / "run-run-*-next-check-plan.json").write_text(json.dumps({
            "run_id": "run-*",
            "linkage_schema_version": 1,
            "candidates": [{
                "linkage_status": "linked",
                "incident_id": incident_id,
                "candidateId": "glob-check",
                "title": "Glob check",
            }],
        }), encoding="utf-8")

        # Try to access via glob run_id
        result = handle_get_incident(incident_id, external_analysis_dir=self._external_dir)

        # Should be empty (unsafe run_id was rejected)
        self.assertEqual(result["suggested_checks"], [])


if __name__ == "__main__":
    unittest.main()
