"""Basic tests for incident case-file prior analysis integration.

Tests:
1. Case file includes prior_analysis key
2. No prior analysis produces empty list
3. Valid linked prior analysis artifact is included
4. Prior analysis entry includes required fields
5. Prior analysis is clearly labeled as model context
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


def make_valid_prior_analysis_artifact(
    run_id: str,
    incident_id: str,
    *,
    summary: str = "Cluster shows degraded health with warning events",
    confidence: str = "medium",
) -> dict:
    """Create a valid prior analysis artifact with proper linkage."""
    return {
        "run_id": run_id,
        "linkage_schema_version": 1,
        "incident_id": incident_id,
        "summary": summary,
        "confidence": confidence,
        "supporting_evidence": ["Evidence item 1", "Evidence item 2"],
        "uncertainties": ["Missing logs"],
        "generated_at": "2024-06-01T12:00:00+00:00",
        "source": "next-check-review",
    }


class TestIncidentCaseFilePriorAnalysisBasic(unittest.TestCase):
    """Basic prior analysis integration tests."""

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

    def test_case_file_includes_prior_analysis_key(self) -> None:
        """Case file includes prior_analysis key."""
        run_id = "run-001"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertIn("prior_analysis", packet)

    def test_no_prior_analysis_produces_empty_list(self) -> None:
        """No prior analysis produces empty list."""
        run_id = "run-002"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(packet["prior_analysis"], [])

    def test_valid_linked_prior_analysis_included(self) -> None:
        """Valid linked prior analysis artifact is included."""
        run_id = "run-003"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = make_valid_prior_analysis_artifact(run_id, incident_id)
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
        self.assertEqual(prior[0]["source"], "next-check-review")
        self.assertEqual(prior[0]["summary"], "Cluster shows degraded health with warning events")

    def test_prior_analysis_entry_includes_required_fields(self) -> None:
        """Prior analysis entry includes required fields."""
        run_id = "run-004"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = make_valid_prior_analysis_artifact(run_id, incident_id)
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

        # Required fields
        self.assertIn("source", entry)
        self.assertIn("run_id", entry)
        self.assertIn("summary", entry)
        self.assertIn("confidence", entry)
        self.assertIn("bounded", entry)
        self.assertIn("artifact_ref", entry)

        # Check artifact_ref structure
        artifact_ref = entry["artifact_ref"]
        self.assertEqual(artifact_ref["kind"], "external-analysis")
        self.assertEqual(artifact_ref["safe"], True)

    def test_prior_analysis_labeled_as_model_context(self) -> None:
        """Prior analysis is clearly labeled as model-generated context."""
        run_id = "run-005"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = make_valid_prior_analysis_artifact(run_id, incident_id)
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

        # Should be marked as model-generated
        self.assertTrue(entry.get("bounded"))
        self.assertTrue(entry.get("_model_generated"))

    def test_multiple_prior_analysis_artifacts_ordered(self) -> None:
        """Multiple prior analysis artifacts are included in deterministic order."""
        run_id_1 = "run-aaa"
        run_id_2 = "run-bbb"
        incident_id = self._create_incident_with_signal(run_id_1)
        self._test_store._incidents[incident_id].signals.append(
            IncidentSignal(
                source="pod",
                reason="Warning",
                message="warning",
                captured_at=TEST_TIME_2,
                run_id=run_id_2,
            )
        )
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact_1 = make_valid_prior_analysis_artifact(
            run_id_1, incident_id, summary="First analysis"
        )
        artifact_2 = make_valid_prior_analysis_artifact(
            run_id_2, incident_id, summary="Second analysis"
        )
        self.write_prior_analysis_artifact(run_id_1, incident_id, artifact_1)
        self.write_prior_analysis_artifact(run_id_2, incident_id, artifact_2)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        prior = packet["prior_analysis"]
        self.assertEqual(len(prior), 2)
        # Deterministic order by run_id
        self.assertEqual(prior[0]["run_id"], "run-aaa")
        self.assertEqual(prior[1]["run_id"], "run-bbb")


if __name__ == "__main__":
    unittest.main()
