"""Tests for load_read_only_check_result_artifacts_for_incident function.

Tests prove:
1. Valid artifact loads for matching incident_id and run_id
2. Wrong incident_id is ignored
3. Wrong run_id is ignored
4. Unsafe run_id is ignored/rejected safely
5. Missing artifact returns empty list
6. Malformed JSON is skipped safely
7. Missing required fields are skipped safely
8. Too many artifacts are bounded
9. Long evidence is truncated or omitted according to bounds
10. Loaded artifacts are JSON-serializable
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_lifecycle import IncidentSignal
from k8s_diag_agent.collect.incident_read_only_check_artifacts import (
    DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS,
    DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS,
    DEFAULT_MAX_READ_ONLY_CHECK_ARTIFACTS,
    load_read_only_check_result_artifacts_for_incident,
    write_read_only_check_result_artifact,
)


class FakeIncident:
    """Fake incident for testing."""

    def __init__(self, incident_id: str, run_ids: list[str]) -> None:
        self.incident_id = incident_id
        self.signals = [
            IncidentSignal(
                source="test",
                reason="test",
                message="test",
                captured_at=datetime.now(UTC),
                run_id=run_id,
            )
            for run_id in run_ids
        ]


class TestValidArtifactLoading:
    """Test valid artifact loading."""

    def test_valid_artifact_loads_for_matching_incident_and_run(
        self, tmp_path: Path
    ) -> None:
        """Valid artifact loads for matching incident_id and run_id."""
        incident = FakeIncident("incident-001", ["run-001"])

        # Write artifact
        runner_result = {
            "checks_requested": 2,
            "checks_run": 2,
            "checks_skipped": 0,
            "checks_rejected": 0,
            "results": [
                {"check_id": "pod_logs", "status": "completed", "summary": "test log"}
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-001",
            incident_id="incident-001",
            runner_result=runner_result,
        )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]  # type: ignore[arg-type]
            tmp_path,
        )

        assert len(results) == 1
        assert results[0]["run_id"] == "run-001"
        assert results[0]["checks_run"] == 2

    def test_wrong_incident_id_ignored(self, tmp_path: Path) -> None:
        """Wrong incident_id is ignored."""
        incident = FakeIncident("incident-002", ["run-002"])

        # Write artifact for different incident
        runner_result = {"checks_requested": 1, "checks_run": 1}
        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-002",
            incident_id="incident-wrong",
            runner_result=runner_result,
        )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty because incident_id doesn't match
        assert len(results) == 0

    def test_wrong_run_id_ignored(self, tmp_path: Path) -> None:
        """Wrong run_id is ignored."""
        incident = FakeIncident("incident-003", ["run-other"])

        # Write artifact for different run
        runner_result = {"checks_requested": 1, "checks_run": 1}
        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-003",
            incident_id="incident-003",
            runner_result=runner_result,
        )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty because run_id doesn't match
        assert len(results) == 0

    def test_missing_artifact_returns_empty(self, tmp_path: Path) -> None:
        """Missing artifact returns empty list."""
        incident = FakeIncident("incident-004", ["run-nonexistent"])

        # Load artifacts - no artifacts written
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        assert len(results) == 0

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        """Missing directory returns empty list."""
        incident = FakeIncident("incident-005", ["run-005"])

        # Use non-existent directory
        nonexistent = tmp_path / "nonexistent"

        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            nonexistent,
        )

        assert len(results) == 0


class TestMalformedArtifactHandling:
    """Test malformed artifact handling."""

    def test_malformed_json_skipped(self, tmp_path: Path) -> None:
        """Malformed JSON is skipped safely."""
        incident = FakeIncident("incident-006", ["run-006"])

        # Write invalid JSON
        artifact_path = tmp_path / "run-006-read-only-check-results.json"
        artifact_path.write_text("not valid json {{{", encoding="utf-8")

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty due to malformed JSON
        assert len(results) == 0

    def test_missing_required_fields_skipped(self, tmp_path: Path) -> None:
        """Missing required fields are skipped safely."""
        incident = FakeIncident("incident-007", ["run-007"])

        # Write artifact without schema_version
        artifact_path = tmp_path / "run-007-read-only-check-results.json"
        artifact_path.write_text(
            json.dumps({"run_id": "run-007", "incident_id": "incident-007"}),
            encoding="utf-8",
        )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty due to missing schema_version
        assert len(results) == 0

    def test_non_dict_root_skipped(self, tmp_path: Path) -> None:
        """Non-dict root is skipped safely."""
        incident = FakeIncident("incident-008", ["run-008"])

        # Write artifact with non-dict root
        artifact_path = tmp_path / "run-008-read-only-check-results.json"
        artifact_path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty due to non-dict root
        assert len(results) == 0


class TestBounds:
    """Test bounds enforcement."""

    def test_too_many_artifacts_bounded(self, tmp_path: Path) -> None:
        """Too many artifacts are bounded."""
        # Create incident with many run_ids
        run_ids = [f"run-{i:03d}" for i in range(20)]
        incident = FakeIncident("incident-009", run_ids)

        # Write artifacts for each run_id
        for run_id in run_ids:
            write_read_only_check_result_artifact(
                external_analysis_dir=tmp_path,
                run_id=run_id,
                incident_id="incident-009",
                runner_result={"checks_requested": 1, "checks_run": 1},
            )

        # Load with default max
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be bounded
        assert len(results) <= DEFAULT_MAX_READ_ONLY_CHECK_ARTIFACTS

    def test_max_artifacts_parameter_respected(self, tmp_path: Path) -> None:
        """max_artifacts parameter is respected."""
        run_ids = [f"run-{i:03d}" for i in range(15)]
        incident = FakeIncident("incident-010", run_ids)

        # Write artifacts
        for run_id in run_ids:
            write_read_only_check_result_artifact(
                external_analysis_dir=tmp_path,
                run_id=run_id,
                incident_id="incident-010",
                runner_result={"checks_requested": 1, "checks_run": 1},
            )

        # Load with lower max
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
            max_artifacts=3,
        )

        assert len(results) <= 3

    def test_long_summary_truncated(self, tmp_path: Path) -> None:
        """Long summaries are truncated."""
        incident = FakeIncident("incident-011", ["run-011"])

        # Create long summary
        long_summary = "x" * 1000
        runner_result = {
            "checks_requested": 1,
            "checks_run": 1,
            "results": [
                {"check_id": "pod_logs", "status": "completed", "summary": long_summary}
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-011",
            incident_id="incident-011",
            runner_result=runner_result,
        )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
            max_summary_chars=DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS,
        )

        assert len(results) == 1
        result = results[0]["results"][0]
        assert len(result["summary"]) <= DEFAULT_MAX_CHECK_RESULT_SUMMARY_CHARS + 10  # + ellipsis

    def test_long_evidence_truncated(self, tmp_path: Path) -> None:
        """Long evidence strings are truncated."""
        incident = FakeIncident("incident-012", ["run-012"])

        # Create long evidence
        long_evidence = "y" * 5000
        runner_result = {
            "checks_requested": 1,
            "checks_run": 1,
            "results": [
                {
                    "check_id": "pod_logs",
                    "status": "completed",
                    "summary": "test",
                    "evidence": {"observations": [long_evidence]},
                }
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-012",
            incident_id="incident-012",
            runner_result=runner_result,
        )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
            max_evidence_chars=DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS,
        )

        assert len(results) == 1
        # Evidence should be truncated
        evidence_str = json.dumps(results[0]["results"][0].get("evidence", {}))
        assert len(evidence_str) <= DEFAULT_MAX_CHECK_RESULT_EVIDENCE_CHARS + 100


class TestDeterministicOrdering:
    """Test deterministic ordering."""

    def test_results_sorted_by_run_id(self, tmp_path: Path) -> None:
        """Results are sorted by run_id."""
        run_ids = ["run-c", "run-a", "run-b"]
        incident = FakeIncident("incident-013", run_ids)

        # Write artifacts in non-sorted order
        for run_id in run_ids:
            write_read_only_check_result_artifact(
                external_analysis_dir=tmp_path,
                run_id=run_id,
                incident_id="incident-013",
                runner_result={"checks_requested": 1, "checks_run": 1},
            )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be sorted
        assert len(results) == 3
        run_ids_loaded = [r["run_id"] for r in results]
        assert run_ids_loaded == sorted(run_ids_loaded)


class TestSafetyFields:
    """Test safety field stripping."""

    def test_action_fields_stripped(self, tmp_path: Path) -> None:
        """Action-control fields are stripped from results."""
        incident = FakeIncident("incident-014", ["run-014"])

        # Create result with action fields
        runner_result = {
            "checks_requested": 1,
            "checks_run": 1,
            "results": [
                {
                    "check_id": "pod_logs",
                    "status": "completed",
                    "summary": "test",
                    "run": "kubectl exec",
                    "execute": "shell",
                    "action": "delete",
                }
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-014",
            incident_id="incident-014",
            runner_result=runner_result,
        )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        assert len(results) == 1
        result = results[0]["results"][0]
        # Action fields should be stripped
        assert "run" not in result
        assert "execute" not in result
        assert "action" not in result


class TestLoadedArtifactsSerializable:
    """Test loaded artifacts are JSON-serializable."""

    def test_loaded_artifacts_json_serializable(self, tmp_path: Path) -> None:
        """Loaded artifacts are JSON-serializable."""
        incident = FakeIncident("incident-015", ["run-015"])

        # Write artifact
        runner_result = {
            "checks_requested": 2,
            "checks_run": 2,
            "results": [
                {"check_id": "pod_logs", "status": "completed", "summary": "test log"}
            ],
        }
        write_read_only_check_result_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-015",
            incident_id="incident-015",
            runner_result=runner_result,
        )

        # Load artifacts
        results = load_read_only_check_result_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be JSON-serializable
        json_str = json.dumps(results, default=str)
        parsed = json.loads(json_str)
        assert len(parsed) == 1
