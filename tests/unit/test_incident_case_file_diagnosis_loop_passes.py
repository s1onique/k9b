"""Tests for incident_case_file diagnosis_loop_passes integration.

Tests prove:
1. build_incident_case_file includes diagnosis_loop_passes when run_ids provided
2. Existing behavior unchanged when no loop-pass artifacts exist
3. Wrong incident_id loop-pass artifact is ignored
4. Unsafe explicit run IDs do not escape path construction
5. diagnosis_loop_passes is consistently present in output
6. Existing read_only_check_results, prior_analysis behavior remains intact
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from k8s_diag_agent.collect.incident_case_file import build_incident_case_file
from k8s_diag_agent.collect.incident_diagnosis_loop_pass_artifacts import (
    write_diagnosis_loop_pass_artifact,
)
from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.collect.incident_store_provider import (
    reset_incident_store,
    set_incident_store,
)

from .incident_lifecycle_fixtures import make_full_incident


def _create_test_incident_with_signal(
    incident_id: str,
    run_id: str,
) -> IncidentStore:
    """Helper to create a test incident with a signal containing the run_id."""
    test_store = IncidentStore()
    
    # Create incident with signal via merge_candidate_into_incident approach
    # We need to directly insert into the store
    incident = make_full_incident(
        incident_id=incident_id,
        status=IncidentStatus.OPEN,
    )
    
    # Store the incident directly
    test_store._incidents[incident_id] = incident
    
    return test_store


class TestDiagnosisLoopPassesIntegration:
    """Test diagnosis_loop_passes integration in build_incident_case_file."""

    def test_case_file_includes_diagnosis_loop_passes(self) -> None:
        """Case file includes diagnosis_loop_passes when run_ids provided."""
        incident_id = "test-incident-001"
        run_id = "loop-pass-001"

        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            # Write a loop-pass artifact
            orchestrator_result = {
                "schema_version": "1.0",
                "incident_id": incident_id,
                "run_id": run_id,
                "decision": "run_allowed_read_only_checks",
                "case_file_linked_artifact": True,
            }
            write_diagnosis_loop_pass_artifact(
                external_analysis_dir=external_analysis_dir,
                run_id=run_id,
                incident_id=incident_id,
                orchestrator_result=orchestrator_result,
            )

            # Create incident with signal using helper
            test_store = _create_test_incident_with_signal(incident_id, run_id)
            set_incident_store(test_store)
            try:
                # Build case file with explicit loop-pass run_ids
                case_file = build_incident_case_file(
                    incident_id=incident_id,
                    external_analysis_dir=external_analysis_dir,
                    diagnosis_loop_pass_run_ids=[run_id],
                )

                assert case_file is not None
                assert "diagnosis_loop_passes" in case_file
                assert len(case_file["diagnosis_loop_passes"]) == 1
                assert case_file["diagnosis_loop_passes"][0]["run_id"] == run_id
            finally:
                set_incident_store(None)
                reset_incident_store()

    def test_case_file_without_loop_pass_run_ids(self) -> None:
        """Case file has empty diagnosis_loop_passes when no run_ids provided."""
        incident_id = "test-incident-002"
        test_store = _create_test_incident_with_signal(incident_id, "run-002")
        set_incident_store(test_store)
        try:
            # Build case file without external_analysis_dir
            case_file = build_incident_case_file(
                incident_id=incident_id,
                external_analysis_dir=None,
            )

            assert case_file is not None
            assert "diagnosis_loop_passes" in case_file
            assert len(case_file["diagnosis_loop_passes"]) == 0
        finally:
            set_incident_store(None)
            reset_incident_store()

    def test_wrong_incident_id_ignored(self) -> None:
        """Wrong incident_id loop-pass artifact is ignored."""
        incident_id = "test-incident-003"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            external_analysis_dir = Path(tmpdir)

            # Write a loop-pass artifact for a DIFFERENT incident
            orchestrator_result = {
                "schema_version": "1.0",
                "incident_id": "other-incident",
                "run_id": "loop-pass-003",
                "decision": "run_allowed_read_only_checks",
                "case_file_linked_artifact": False,
            }
            write_diagnosis_loop_pass_artifact(
                external_analysis_dir=external_analysis_dir,
                run_id="loop-pass-003",
                incident_id="other-incident",
                orchestrator_result=orchestrator_result,
            )

            # Create real incident
            test_store = _create_test_incident_with_signal(incident_id, "run-003")
            set_incident_store(test_store)
            try:
                # Build case file - should NOT include the artifact
                case_file = build_incident_case_file(
                    incident_id=incident_id,
                    external_analysis_dir=external_analysis_dir,
                    diagnosis_loop_pass_run_ids=["loop-pass-003"],
                )

                assert case_file is not None
                assert len(case_file["diagnosis_loop_passes"]) == 0
            finally:
                set_incident_store(None)
                reset_incident_store()

    def test_unsafe_run_id_not_used(self) -> None:
        """Unsafe explicit run IDs do not escape path construction."""
        incident_id = "test-incident-004"
        test_store = _create_test_incident_with_signal(incident_id, "run-004")
        set_incident_store(test_store)
        try:
            # Try to use path traversal run_id - should be safely ignored
            case_file = build_incident_case_file(
                incident_id=incident_id,
                external_analysis_dir=Path("/tmp/test"),
                diagnosis_loop_pass_run_ids=["../etc/passwd"],
            )

            # Should not crash, just return empty
            assert case_file is not None
            assert len(case_file["diagnosis_loop_passes"]) == 0
        finally:
            set_incident_store(None)
            reset_incident_store()

    def test_existing_behavior_unchanged(self) -> None:
        """Existing read_only_check_results, prior_analysis behavior remains intact."""
        incident_id = "test-incident-005"
        test_store = _create_test_incident_with_signal(incident_id, "run-005")
        set_incident_store(test_store)
        try:
            # Build case file without loop-pass context
            case_file = build_incident_case_file(
                incident_id=incident_id,
                external_analysis_dir=None,
            )

            assert case_file is not None
            # Existing fields should still be present
            assert "read_only_check_results" in case_file
            assert "prior_analysis" in case_file
            assert "suggested_checks" in case_file
            assert "signals" in case_file
            assert "events" in case_file
            # Safety fields
            assert case_file["read_only"] is True
            assert case_file["allowed_actions"] == []
        finally:
            set_incident_store(None)
            reset_incident_store()

    def test_diagnosis_loop_passes_consistently_present(self) -> None:
        """diagnosis_loop_passes is always present in output (not missing)."""
        incident_id = "test-incident-006"
        test_store = _create_test_incident_with_signal(incident_id, "run-006")
        set_incident_store(test_store)
        try:
            # Build case file
            case_file = build_incident_case_file(
                incident_id=incident_id,
            )

            assert case_file is not None
            # diagnosis_loop_passes should be present (even if empty)
            assert "diagnosis_loop_passes" in case_file
            assert isinstance(case_file["diagnosis_loop_passes"], list)
        finally:
            set_incident_store(None)
            reset_incident_store()
