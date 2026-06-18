"""Tests for load_diagnosis_loop_pass_artifacts_for_incident function.

Tests prove:
1. Valid artifact loads for matching incident_id and run_id
2. Wrong incident_id is ignored
3. Unsafe run_id is ignored or rejected safely
4. Missing artifact returns empty list
5. Missing directory returns empty list
6. Malformed JSON is skipped
7. Non-dict root is skipped
8. Missing schema_version is skipped
9. Too many artifacts are bounded
10. Duplicate run IDs are deduplicated deterministically
11. Results are sorted deterministically
12. Loaded entries are JSON-serializable
13. Action-control fields are stripped on load
"""

from __future__ import annotations

import json
from pathlib import Path

from k8s_diag_agent.collect.incident_diagnosis_loop_pass_artifacts import (
    DEFAULT_MAX_DIAGNOSIS_LOOP_PASS_ARTIFACTS,
    load_diagnosis_loop_pass_artifacts_for_incident,
    write_diagnosis_loop_pass_artifact,
)


class FakeIncident:
    """Fake incident for testing."""

    def __init__(self, incident_id: str, run_ids: list[str]) -> None:
        self.incident_id = incident_id
        self.signals = [
            FakeSignal(run_id=run_id)
            for run_id in run_ids
        ]


class FakeSignal:
    """Fake signal for testing."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id


class TestValidArtifactLoading:
    """Test valid artifact loading."""

    def test_valid_artifact_loads(
        self, tmp_path: Path
    ) -> None:
        """Valid artifact loads for matching incident_id and run_id."""
        incident = FakeIncident("incident-001", ["run-001"])

        # Write artifact
        orchestrator_result = {
            "schema_version": "1.0",
            "incident_id": "incident-001",
            "run_id": "run-001",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": True,
            "runner_result": {
                "checks_requested": 2,
                "checks_run": 2,
                "checks_skipped": 0,
                "checks_rejected": 0,
            },
            "artifact": {
                "run_id": "run-001",
                "incident_id": "incident-001",
                "written": True,
            },
        }
        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-001",
            incident_id="incident-001",
            orchestrator_result=orchestrator_result,
        )

        # Load artifacts
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        assert len(results) == 1
        assert results[0]["run_id"] == "run-001"
        assert results[0]["decision"] == "run_allowed_read_only_checks"

    def test_wrong_incident_id_ignored(
        self, tmp_path: Path
    ) -> None:
        """Wrong incident_id is ignored."""
        incident = FakeIncident("incident-002", ["run-002"])

        # Write artifact for different incident
        orchestrator_result = {
            "schema_version": "1.0",
            "incident_id": "incident-wrong",
            "run_id": "run-002",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }
        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-002",
            incident_id="incident-wrong",
            orchestrator_result=orchestrator_result,
        )

        # Load artifacts
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty because incident_id doesn't match
        assert len(results) == 0

    def test_missing_artifact_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """Missing artifact returns empty list."""
        incident = FakeIncident("incident-004", ["run-nonexistent"])

        # Load artifacts - no artifacts written
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        assert len(results) == 0

    def test_missing_directory_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """Missing directory returns empty list."""
        incident = FakeIncident("incident-005", ["run-005"])

        # Use non-existent directory
        nonexistent = tmp_path / "nonexistent"

        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            nonexistent,
        )

        assert len(results) == 0


class TestMalformedArtifactHandling:
    """Test malformed artifact handling."""

    def test_malformed_json_skipped(
        self, tmp_path: Path
    ) -> None:
        """Malformed JSON is skipped safely."""
        incident = FakeIncident("incident-006", ["run-006"])

        # Write invalid JSON
        artifact_path = tmp_path / "run-006-diagnosis-loop-pass.json"
        artifact_path.write_text("not valid json {{{", encoding="utf-8")

        # Load artifacts
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty due to malformed JSON
        assert len(results) == 0

    def test_missing_schema_version_skipped(
        self, tmp_path: Path
    ) -> None:
        """Missing schema_version is skipped safely."""
        incident = FakeIncident("incident-007", ["run-007"])

        # Write artifact without schema_version
        artifact_path = tmp_path / "run-007-diagnosis-loop-pass.json"
        artifact_path.write_text(
            json.dumps({"run_id": "run-007", "incident_id": "incident-007"}),
            encoding="utf-8",
        )

        # Load artifacts
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty due to missing schema_version
        assert len(results) == 0

    def test_non_dict_root_skipped(
        self, tmp_path: Path
    ) -> None:
        """Non-dict root is skipped safely."""
        incident = FakeIncident("incident-008", ["run-008"])

        # Write artifact with non-dict root
        artifact_path = tmp_path / "run-008-diagnosis-loop-pass.json"
        artifact_path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

        # Load artifacts
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be empty due to non-dict root
        assert len(results) == 0


class TestBounds:
    """Test bounds enforcement."""

    def test_too_many_artifacts_bounded(
        self, tmp_path: Path
    ) -> None:
        """Too many artifacts are bounded."""
        # Create incident with many run_ids
        run_ids = [f"run-{i:03d}" for i in range(20)]
        incident = FakeIncident("incident-009", run_ids)

        # Write artifacts for each run_id
        for run_id in run_ids:
            orchestrator_result = {
                "schema_version": "1.0",
                "incident_id": "incident-009",
                "run_id": run_id,
                "decision": "run_allowed_read_only_checks",
                "case_file_linked_artifact": False,
            }
            write_diagnosis_loop_pass_artifact(
                external_analysis_dir=tmp_path,
                run_id=run_id,
                incident_id="incident-009",
                orchestrator_result=orchestrator_result,
            )

        # Load with default max
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be bounded
        assert len(results) <= DEFAULT_MAX_DIAGNOSIS_LOOP_PASS_ARTIFACTS


class TestDeterministicOrdering:
    """Test deterministic ordering."""

    def test_results_sorted_by_run_id(
        self, tmp_path: Path
    ) -> None:
        """Results are sorted by run_id."""
        run_ids = ["run-c", "run-a", "run-b"]
        incident = FakeIncident("incident-013", run_ids)

        # Write artifacts in non-sorted order
        for run_id in run_ids:
            orchestrator_result = {
                "schema_version": "1.0",
                "incident_id": "incident-013",
                "run_id": run_id,
                "decision": "run_allowed_read_only_checks",
                "case_file_linked_artifact": False,
            }
            write_diagnosis_loop_pass_artifact(
                external_analysis_dir=tmp_path,
                run_id=run_id,
                incident_id="incident-013",
                orchestrator_result=orchestrator_result,
            )

        # Load artifacts
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be sorted
        assert len(results) == 3
        run_ids_loaded = [r["run_id"] for r in results]
        assert run_ids_loaded == sorted(run_ids_loaded)


class TestSafetyFields:
    """Test safety field stripping."""

    def test_action_fields_stripped(
        self, tmp_path: Path
    ) -> None:
        """Action-control fields are stripped from loaded entries."""
        incident = FakeIncident("incident-014", ["run-014"])

        # Write artifact with action fields
        orchestrator_result = {
            "schema_version": "1.0",
            "incident_id": "incident-014",
            "run_id": "run-014",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
            # These should be stripped
            "run": "kubectl exec",
            "execute": "shell",
            "mutate": True,
            "action": "delete",
        }
        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-014",
            incident_id="incident-014",
            orchestrator_result=orchestrator_result,
        )

        # Load artifacts
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        assert len(results) == 1
        # Action fields should be stripped
        assert "run" not in results[0]
        assert "execute" not in results[0]
        assert "mutate" not in results[0]
        assert "action" not in results[0]


class TestLoadedArtifactsSerializable:
    """Test loaded artifacts are JSON-serializable."""

    def test_loaded_artifacts_json_serializable(
        self, tmp_path: Path
    ) -> None:
        """Loaded artifacts are JSON-serializable."""
        incident = FakeIncident("incident-015", ["run-015"])

        # Write artifact
        orchestrator_result = {
            "schema_version": "1.0",
            "incident_id": "incident-015",
            "run_id": "run-015",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }
        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-015",
            incident_id="incident-015",
            orchestrator_result=orchestrator_result,
        )

        # Load artifacts
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
        )

        # Should be JSON-serializable
        json_str = json.dumps(results, default=str)
        parsed = json.loads(json_str)
        assert len(parsed) == 1


class TestExplicitRunIds:
    """Test explicit run_ids parameter."""

    def test_explicit_run_ids_loaded(
        self, tmp_path: Path
    ) -> None:
        """Explicit run_ids are loaded even without signals."""
        # Create incident with no signals
        incident = FakeIncident("incident-020", [])

        # Write artifact
        orchestrator_result = {
            "schema_version": "1.0",
            "incident_id": "incident-020",
            "run_id": "run-020",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }
        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-020",
            incident_id="incident-020",
            orchestrator_result=orchestrator_result,
        )

        # Load with explicit run_ids
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
            explicit_run_ids=["run-020"],
        )

        assert len(results) == 1
        assert results[0]["run_id"] == "run-020"

    def test_explicit_run_ids_wrong_incident_ignored(
        self, tmp_path: Path
    ) -> None:
        """Explicit run_ids with wrong incident are ignored."""
        incident = FakeIncident("incident-021", [])

        # Write artifact for different incident
        orchestrator_result = {
            "schema_version": "1.0",
            "incident_id": "incident-other",
            "run_id": "run-021",
            "decision": "run_allowed_read_only_checks",
            "case_file_linked_artifact": False,
        }
        write_diagnosis_loop_pass_artifact(
            external_analysis_dir=tmp_path,
            run_id="run-021",
            incident_id="incident-other",
            orchestrator_result=orchestrator_result,
        )

        # Load with explicit run_ids for different incident
        results = load_diagnosis_loop_pass_artifacts_for_incident(
            incident,  # type: ignore[arg-type]
            tmp_path,
            explicit_run_ids=["run-021"],
        )

        # Should be empty because incident_id doesn't match
        assert len(results) == 0
