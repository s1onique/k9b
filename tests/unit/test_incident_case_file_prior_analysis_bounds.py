"""Bounds tests for incident case-file prior analysis integration.

Tests:
1. max_prior_analysis is enforced
2. Long summaries are truncated
3. Long raw outputs are truncated
4. Ordering is deterministic
5. Full packet remains JSON-serializable
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


class TestIncidentCaseFilePriorAnalysisBounds(unittest.TestCase):
    """Bounds tests for prior analysis integration."""

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

    def test_max_prior_analysis_enforced(self) -> None:
        """max_prior_analysis is enforced."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        max_prior = 2

        # Create incident with multiple run_ids
        run_ids = ["run-a", "run-b", "run-c"]
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        for run_id in run_ids:
            stored_incident.signals.append(
                IncidentSignal(
                    source="pod",
                    reason="Test",
                    message="test",
                    captured_at=TEST_TIME_2,
                    run_id=run_id,
                )
            )
            artifact = {
                "run_id": run_id,
                "linkage_schema_version": 1,
                "incident_id": incident_id,
                "summary": f"Analysis for {run_id}",
            }
            self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
            max_prior_analysis=max_prior,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(len(packet["prior_analysis"]), max_prior)

    def test_long_summary_truncated(self) -> None:
        """Long summaries are truncated."""
        run_id = "run-truncate"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        long_summary = "A" * 2000  # Very long summary
        artifact = {
            "run_id": run_id,
            "linkage_schema_version": 1,
            "incident_id": incident_id,
            "summary": long_summary,
        }
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

        # Summary should be truncated
        summary = prior[0]["summary"]
        self.assertLess(len(summary), len(long_summary))
        # Allow for truncation marker " [...]" (6 chars) added by _truncate_string
        self.assertLessEqual(len(summary), 1000 + 6)

    def test_long_raw_output_truncated(self) -> None:
        """Long raw outputs are truncated."""
        run_id = "run-raw"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        long_raw = "B" * 5000  # Very long raw output
        artifact = {
            "run_id": run_id,
            "linkage_schema_version": 1,
            "incident_id": incident_id,
            "summary": "Test summary",
            "raw_output": long_raw,
        }
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

        # Raw output should be truncated if present
        raw_output = prior[0].get("raw_output", "")
        if raw_output:
            self.assertLess(len(raw_output), len(long_raw))
            # Allow for truncation marker " [...]" (6 chars) added by _truncate_string
            self.assertLessEqual(len(raw_output), 2000 + 6)

    def test_ordering_deterministic(self) -> None:
        """Ordering is deterministic by run_id."""
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        # Create incident with multiple run_ids in non-alphabetical order
        run_ids = ["run-z", "run-a", "run-m"]
        candidate = make_candidate(name="test-pod")
        self._test_store.promote_candidates([candidate], TEST_TIME_1)
        incidents = self._test_store.list_incidents()
        incident = incidents[0]
        incident_id = incident.incident_id

        stored_incident = self._test_store._incidents[incident_id]
        for run_id in run_ids:
            stored_incident.signals.append(
                IncidentSignal(
                    source="pod",
                    reason="Test",
                    message="test",
                    captured_at=TEST_TIME_2,
                    run_id=run_id,
                )
            )
            artifact = {
                "run_id": run_id,
                "linkage_schema_version": 1,
                "incident_id": incident_id,
                "summary": f"Analysis for {run_id}",
            }
            self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        # Build multiple times
        packets = []
        for _ in range(3):
            packet = build_incident_case_file(
                incident_id,
                external_analysis_dir=self._external_dir,
                now=now,
            )
            packets.append(packet)

        # All packets should have same order
        for packet in packets:
            self.assertIsNotNone(packet)
            prior = packet["prior_analysis"]
            run_ids_ordered = [p["run_id"] for p in prior]
            self.assertEqual(run_ids_ordered, ["run-a", "run-m", "run-z"])

    def test_full_packet_json_serializable(self) -> None:
        """Full packet remains JSON-serializable."""
        run_id = "run-json"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        artifact = {
            "run_id": run_id,
            "linkage_schema_version": 1,
            "incident_id": incident_id,
            "summary": "Test analysis",
            "supporting_evidence": ["Evidence 1", "Evidence 2"],
        }
        self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None

        # Should be JSON serializable
        json_str = json.dumps(packet)
        self.assertIsInstance(json_str, str)

        # Should be deserializable
        parsed = json.loads(json_str)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed["incident"]["incident_id"], incident_id)
        self.assertIn("prior_analysis", parsed)

    def test_malformed_artifact_skipped(self) -> None:
        """Malformed prior-analysis artifact is skipped gracefully."""
        run_id = "run-malformed"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        # Write malformed artifact
        path = self._external_dir / f"{run_id}-next-check-review.json"
        path.write_text("{ invalid json }", encoding="utf-8")

        # Should not raise, should return empty prior_analysis
        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        self.assertEqual(packet["prior_analysis"], [])

    def test_legacy_artifact_without_linkage_excluded(self) -> None:
        """Legacy artifact without linkage_schema_version is excluded."""
        run_id = "run-legacy"
        incident_id = self._create_incident_with_signal(run_id)
        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        # Legacy artifact without linkage_schema_version
        artifact = {
            "run_id": run_id,
            "incident_id": incident_id,
            "summary": "Legacy analysis without linkage",
        }
        self.write_prior_analysis_artifact(run_id, incident_id, artifact)

        packet = build_incident_case_file(
            incident_id,
            external_analysis_dir=self._external_dir,
            now=now,
        )

        self.assertIsNotNone(packet)
        assert packet is not None
        # Legacy artifact should not be included
        self.assertEqual(packet["prior_analysis"], [])


if __name__ == "__main__":
    unittest.main()
