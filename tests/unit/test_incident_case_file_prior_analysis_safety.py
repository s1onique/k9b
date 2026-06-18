"""Safety tests for incident case-file prior analysis integration.

Tests:
1. Prior analysis entries do not include action-control fields
2. Case-file top-level allowed_actions remains empty
3. Case-file read_only remains True
4. Case-file disallowed_actions remains complete
5. Packet generation does not mutate artifacts
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_case_file import (
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

# Action control fields that should NOT appear in prior_analysis entries
FORBIDDEN_ACTION_FIELDS = frozenset({
    "run",
    "execute",
    "promote",
    "apply",
    "remediate",
    "action",
    "approve",
    "reject",
    "run_command",
    "execute_command",
})


def make_prior_analysis_artifact_with_action_fields(
    run_id: str,
    incident_id: str,
) -> dict:
    """Create a prior analysis artifact with action-control fields (should be stripped)."""
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "incident_id": incident_id,
        "summary": "Analysis with action fields",
        "confidence": "medium",
        # These should be stripped
        "run": "kubectl describe pod",
        "execute": True,
        "action": "approve",
        "promote": False,
        "apply": True,
        "remediate": "restart",
    }


class TestIncidentCaseFilePriorAnalysisSafety(unittest.TestCase):
    """Safety tests for prior analysis integration."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self._test_store = IncidentStore()
        set_incident_store(self._test_store)
        self._tmpdir = tempfile.mkdtemp()
        self._external_dir = Path(self._tmpdir) / "external-analysis"
        self._external_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        """Clean up after each test."""
        set_incident_store(None)
        reset_incident_store()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _create_incident_with_signal(self, run_id: str) -> str:
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
            captured_at=TEST_TIME_2,
            run_id=run_id,
        )
        stored_incident.signals.append(signal)

        return incident_id

    def write_prior_analysis_artifact(
        self, run_id: str, incident_id: str, payload: dict
    ) -> None:
        """Write a prior analysis artifact to the external_analysis directory."""
        path = self._external_dir / f"{run_id}-next-check-review.json"
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_prior_analysis_no_action_control_fields(self) -> None:
        """Prior analysis entries do not include action-control fields."""
        run_id = "run-safety-001"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = make_prior_analysis_artifact_with_action_fields(run_id, incident_id)
        self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        prior = packet["prior_analysis"]
        self.assertEqual(len(prior), 1)
        entry = prior[0]

        # None of the forbidden action fields should be present
        for field in FORBIDDEN_ACTION_FIELDS:
            self.assertNotIn(field, entry, f"Field '{field}' should not be in prior_analysis entry")

    def test_case_file_allowed_actions_remains_empty(self) -> None:
        """Case-file top-level allowed_actions remains empty."""
        run_id = "run-safety-002"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = {
            "run_id": run_id,
            "linkage_schema_version": 1,
            "incident_id": incident_id,
            "summary": "Test analysis",
        }
        self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(packet["allowed_actions"], [])

    def test_case_file_read_only_remains_true(self) -> None:
        """Case-file read_only remains True."""
        run_id = "run-safety-003"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = {
            "run_id": run_id,
            "linkage_schema_version": 1,
            "incident_id": incident_id,
            "summary": "Test analysis",
        }
        self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(packet["read_only"], True)

    def test_case_file_disallowed_actions_remains_complete(self) -> None:
        """Case-file disallowed_actions remains complete."""
        run_id = "run-safety-004"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = {
            "run_id": run_id,
            "linkage_schema_version": 1,
            "incident_id": incident_id,
            "summary": "Test analysis",
        }
        self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        disallowed = packet["disallowed_actions"]
        self.assertIsInstance(disallowed, list)

        # All required action verbs should be present
        required_actions = {"execute", "promote", "apply", "remediate", "delete", "mutate_cluster"}
        self.assertEqual(set(disallowed), required_actions)

    def test_packet_generation_does_not_mutate_artifact(self) -> None:
        """Packet generation does not mutate the artifact file."""
        run_id = "run-safety-005"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = {
            "run_id": run_id,
            "linkage_schema_version": 1,
            "incident_id": incident_id,
            "summary": "Original summary",
        }
        self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        # Read original artifact
        path = self._external_dir / f"{run_id}-next-check-review.json"
        original_content = path.read_text()

        # Build packet multiple times
        for _ in range(3):
            packet = build_incident_case_file(
                incident_id,
                external_analysis_dir=self._external_dir,
                now=now,
            )
            self.assertIsNotNone(packet)

        # Artifact should be unchanged
        final_content = path.read_text()
        self.assertEqual(original_content, final_content)

    def test_wrong_incident_artifact_excluded(self) -> None:
        """Wrong incident prior-analysis artifact is excluded."""
        run_id = "run-safety-006"
        incident_id = self._create_incident_with_signal(run_id)
        wrong_incident_id = "incident-wrong-123"
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = {
            "run_id": run_id,
            "linkage_schema_version": 1,
            "incident_id": wrong_incident_id,  # Wrong incident!
            "summary": "Analysis for wrong incident",
        }
        self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        # Wrong incident artifact should not be included
        self.assertEqual(packet["prior_analysis"], [])

    def test_unsafe_run_id_rejected(self) -> None:
        """Unsafe run IDs are rejected by is_safe_run_id and not loaded."""
        from k8s_diag_agent.collect.incident_prior_analysis import is_safe_run_id

        unsafe_run_ids = [
            "../etc/passwd",
            "run/../../../etc/passwd",
            "run;rm -rf",
            "/absolute/path",
            "run|command",
            "run`command`",
            "..",
            "",
            None,  # type: ignore
        ]

        for unsafe_run_id in unsafe_run_ids:
            # is_safe_run_id should reject these
            self.assertFalse(
                is_safe_run_id(unsafe_run_id),
                f"is_safe_run_id({unsafe_run_id!r}) should return False",
            )

    def test_unsafe_run_id_in_signal_not_loaded(self) -> None:
        """Incidents with unsafe run_ids in signals do not crash and return empty prior_analysis."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident with a safe run_id that has a valid artifact
        safe_run_id = "run-safe-001"
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        signal = IncidentSignal(
            source="pod",
            reason="Test",
            message="test",
            captured_at=TEST_TIME_2,
            run_id=safe_run_id,
        )
        stored_incident.signals.append(signal)

        # Create valid artifact with safe run_id
        artifact = {
            "run_id": safe_run_id,
            "linkage_schema_version": 1,
            "incident_id": incident_id,
            "summary": "Analysis for safe run",
        }
        self.write_prior_analysis_artifact(safe_run_id, incident_id, artifact)

        # Verify it loads correctly with safe run_id
        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )
        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(len(packet["prior_analysis"]), 1)

        # Now add an unsafe run_id signal and verify it doesn't crash
        unsafe_signal = IncidentSignal(
            source="pod",
            reason="Test2",
            message="test2",
            captured_at=TEST_TIME_2,
            run_id="../etc/passwd",  # Unsafe!
        )
        stored_incident.signals.append(unsafe_signal)

        # Should not crash and should still return the safe artifact
        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )
        self.assertIsNotNone(packet)
        assert packet is not None
        # Safe artifact should still be included
        self.assertEqual(len(packet["prior_analysis"]), 1)
        self.assertEqual(packet["prior_analysis"][0]["run_id"], safe_run_id)


if __name__ == "__main__":
    unittest.main()
