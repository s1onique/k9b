"""Tests for load_next_check_plan_payload and load_next_check_plan_payloads_for_incident functions.

These tests verify:
1. Missing artifact returns None without error
2. Malformed JSON returns None without error
3. Non-object JSON returns None
4. Valid plan payload loads successfully
5. Multiple run_ids load multiple payloads in deterministic order
6. Helper does not mutate incident
7. Max artifacts bound is respected
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from k8s_diag_agent.collect.incident_next_check_artifacts import (
    load_next_check_plan_payload,
    load_next_check_plan_payloads_for_incident,
)

from .incident_next_check_artifact_fixtures import (
    make_basic_plan_payload,
    make_incident_with_run_ids,
    write_plan_artifact,
)


class TestLoadNextCheckPlanPayload(unittest.TestCase):
    """Tests for load_next_check_plan_payload function."""

    def test_missing_file_returns_none(self) -> None:
        """load_next_check_plan_payload must return None for missing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            result = load_next_check_plan_payload(path)
            self.assertIsNone(result)

    def test_malformed_json_returns_none(self) -> None:
        """load_next_check_plan_payload must return None for malformed JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "malformed.json"
            path.write_text("{ invalid json }", encoding="utf-8")
            result = load_next_check_plan_payload(path)
            self.assertIsNone(result)

    def test_non_object_json_returns_none(self) -> None:
        """load_next_check_plan_payload must return None for non-object JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "array.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")
            result = load_next_check_plan_payload(path)
            self.assertIsNone(result)

    def test_valid_plan_payload_loads(self) -> None:
        """load_next_check_plan_payload must load valid plan payload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "run-123-next-check-plan.json"
            payload = make_basic_plan_payload("run-123")
            path.write_text(json.dumps(payload), encoding="utf-8")

            result = load_next_check_plan_payload(path)
            self.assertIsNotNone(result)
            self.assertEqual(result["run_id"], "run-123")
            self.assertEqual(len(result["candidates"]), 1)


class TestLoadNextCheckPlanPayloadsForIncident(unittest.TestCase):
    """Tests for load_next_check_plan_payloads_for_incident function."""

    def test_loads_multiple_payloads_in_deterministic_order(self) -> None:
        """Must load multiple payloads in run_id order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "external-analysis"

            # Create incident with signals for run-1 and run-2
            incident = make_incident_with_run_ids(["run-1", "run-2"])

            # Write plan artifacts
            write_plan_artifact(external_dir, "run-1", make_basic_plan_payload("run-1"))
            write_plan_artifact(external_dir, "run-2", make_basic_plan_payload("run-2"))

            result = load_next_check_plan_payloads_for_incident(incident, external_dir)

            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["run_id"], "run-1")
            self.assertEqual(result[1]["run_id"], "run-2")

    def test_skips_missing_artifact(self) -> None:
        """Must skip missing artifacts without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "external-analysis"
            external_dir.mkdir(parents=True, exist_ok=True)

            # Create incident with signal for non-existent run
            incident = make_incident_with_run_ids(["nonexistent-run"])

            result = load_next_check_plan_payloads_for_incident(incident, external_dir)

            self.assertEqual(len(result), 0)

    def test_skips_malformed_artifact(self) -> None:
        """Must skip malformed artifacts without error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "external-analysis"
            external_dir.mkdir(parents=True, exist_ok=True)

            # Create incident with signal for run-1
            incident = make_incident_with_run_ids(["run-1"])

            # Write malformed artifact
            malformed_path = external_dir / "run-1-next-check-plan.json"
            malformed_path.write_text("{ invalid }", encoding="utf-8")

            result = load_next_check_plan_payloads_for_incident(incident, external_dir)

            self.assertEqual(len(result), 0)

    def test_returns_empty_for_nonexistent_directory(self) -> None:
        """Must return empty when directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "nonexistent"
            incident = make_incident_with_run_ids(["run-1"])

            result = load_next_check_plan_payloads_for_incident(incident, external_dir)

            self.assertEqual(len(result), 0)

    def test_returns_empty_for_no_run_ids(self) -> None:
        """Must return empty when incident has no run_ids."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "external-analysis"
            external_dir.mkdir(parents=True, exist_ok=True)

            # Create incident with no run_ids
            incident = make_incident_with_run_ids([None])

            result = load_next_check_plan_payloads_for_incident(incident, external_dir)

            self.assertEqual(len(result), 0)

    def test_bounded_by_max_artifacts(self) -> None:
        """Must bound the number of artifacts loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "external-analysis"

            # Create incident with many run_ids
            run_ids = [f"run-{i}" for i in range(20)]
            incident = make_incident_with_run_ids(run_ids)

            # Write artifacts for each run
            for run_id in run_ids:
                write_plan_artifact(external_dir, run_id, make_basic_plan_payload(run_id))

            # Load with max_artifacts=5
            result = load_next_check_plan_payloads_for_incident(
                incident, external_dir, max_artifacts=5
            )

            self.assertEqual(len(result), 5)

    def test_does_not_mutate_incident(self) -> None:
        """Must not mutate the incident."""
        with tempfile.TemporaryDirectory() as tmpdir:
            external_dir = Path(tmpdir) / "external-analysis"
            incident = make_incident_with_run_ids(["run-1"])

            # Capture original state
            original_signals = list(incident.signals)

            # Call function
            load_next_check_plan_payloads_for_incident(incident, external_dir)

            # Verify signals unchanged
            self.assertEqual(len(incident.signals), len(original_signals))


if __name__ == "__main__":
    unittest.main()
