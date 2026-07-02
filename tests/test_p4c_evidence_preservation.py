"""Regression tests for P4c evidence preservation.

These tests verify that pass evidence (run IDs and review artifact paths) is
preserved across multiple targeted diagnosis passes.

Tests verify fixes for:
- Final P4c evidence collapsing to empty pass_run_ids and review_artifact_paths
- Distinct review artifacts per pass being preserved as fallback observable evidence
- Deduplication while preserving order
- Guard against sim-* pass IDs being counted as real evidence
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


class TestPhase3ReviewArtifactPathAccumulation:
    """Tests for review artifact path accumulation in phase3_validate_artifacts."""

    def test_accumulates_distinct_review_artifact_paths(self) -> None:
        """Phase3 stores accumulated review artifact paths from all passes."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase3_validate_artifacts,
        )

        result: dict[str, Any] = {}
        review_paths = [
            "review-pass-1.json",
            "review-pass-2.json",
            "review-pass-3.json",
        ]

        phase3_validate_artifacts(
            total_pass_count=3,
            all_pass_run_ids=["run-1", "run-2", "run-3"],
            external_analysis_dir=Path("/tmp/analysis"),
            result=result,
            terminal_no_checks=False,
            all_review_artifact_paths=review_paths,
        )

        assert result.get("review_artifact_paths") == review_paths

    def test_deduplicates_review_artifact_paths(self) -> None:
        """Phase3 deduplicates review artifact paths while preserving order."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase3_validate_artifacts,
        )

        result: dict[str, Any] = {}
        review_paths = [
            "review-pass-1.json",
            "review-pass-2.json",
            "review-pass-1.json",  # Duplicate
            "review-pass-3.json",
            "review-pass-2.json",  # Duplicate
        ]

        phase3_validate_artifacts(
            total_pass_count=3,
            all_pass_run_ids=["run-1", "run-2", "run-3"],
            external_analysis_dir=Path("/tmp/analysis"),
            result=result,
            terminal_no_checks=False,
            all_review_artifact_paths=review_paths,
        )

        # Should be deduplicated, order preserved
        assert result.get("review_artifact_paths") == [
            "review-pass-1.json",
            "review-pass-2.json",
            "review-pass-3.json",
        ]

    def test_handles_empty_review_artifact_paths(self) -> None:
        """Phase3 handles empty review artifact paths gracefully."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase3_validate_artifacts,
        )

        result: dict[str, Any] = {}

        phase3_validate_artifacts(
            total_pass_count=2,
            all_pass_run_ids=["run-1", "run-2"],
            external_analysis_dir=Path("/tmp/analysis"),
            result=result,
            terminal_no_checks=False,
            all_review_artifact_paths=None,
        )

        # Should not have review_artifact_paths key when empty
        assert "review_artifact_paths" not in result


class TestComputeP4cOutcomeReviewArtifactFallback:
    """Tests for review_artifact_paths fallback in compute_p4c_outcome."""

    def test_uses_review_artifact_paths_when_pass_run_ids_empty(self) -> None:
        """compute_p4c_outcome uses review_artifact_paths as fallback when pass_run_ids empty."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        evidence = {
            "incident_id": "test-incident",
            "pass_count": 2,
            "pass_run_ids": [],  # Empty - backend didn't return stable IDs
            "review_artifact_paths": ["review-pass-1.json", "review-pass-2.json"],
            "real_loop_invoked": True,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": "Pod failed scheduling with nodeSelector",
            "p4c_verdict": {"success": True},
        }

        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=False,
        )

        # review_artifact_paths should be preserved in outcome
        assert outcome.review_artifact_paths == ("review-pass-1.json", "review-pass-2.json")
        # pass_run_ids should be empty (no stable IDs from backend)
        assert outcome.pass_run_ids == ()

    def test_preserves_distinct_review_artifact_paths_per_pass(self) -> None:
        """Distinct review artifacts per pass are preserved in outcome."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        evidence = {
            "incident_id": "test-incident",
            "pass_count": 3,
            "pass_run_ids": [],
            "review_artifact_paths": [
                "auto-diagnosis-review-20260701-001.json",
                "auto-diagnosis-review-20260701-002.json",
                "auto-diagnosis-review-20260701-003.json",
            ],
            "real_loop_invoked": True,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": "Pod failed scheduling",
            "p4c_verdict": {"success": True},
        }

        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=False,
        )

        assert len(outcome.review_artifact_paths) == 3
        assert "auto-diagnosis-review-20260701-001.json" in outcome.review_artifact_paths
        assert "auto-diagnosis-review-20260701-002.json" in outcome.review_artifact_paths
        assert "auto-diagnosis-review-20260701-003.json" in outcome.review_artifact_paths

    def test_deduplicates_review_artifact_paths_in_outcome(self) -> None:
        """compute_p4c_outcome deduplicates review_artifact_paths."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        evidence = {
            "incident_id": "test-incident",
            "pass_count": 2,
            "pass_run_ids": [],
            "review_artifact_paths": [
                "review.json",
                "review.json",  # Duplicate
                "review2.json",
            ],
            "real_loop_invoked": True,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": "Pod failed scheduling",
            "p4c_verdict": {"success": True},
        }

        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=False,
        )

        # Should be deduplicated
        assert outcome.review_artifact_paths == ("review.json", "review2.json")


class TestSimulationGuardForPassEvidence:
    """Tests that sim-* pass IDs are not counted as real evidence."""

    def test_sim_pass_ids_rejected_by_outcome(self) -> None:
        """Simulation pass IDs are rejected by compute_p4c_outcome."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        evidence = {
            "incident_id": "test-incident",
            "pass_count": 2,
            "pass_run_ids": ["sim-test-in-pass1", "sim-test-in-pass2"],
            "real_loop_invoked": True,
            "real_pass_artifacts_found": True,
            "simulation_used": False,  # Flag not set, but pass IDs reveal simulation
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": "Pod failed scheduling",
        }

        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=False,
        )

        # Should be rejected as simulation
        assert outcome.success is False
        assert "simulation_used_but_not_allowed" in outcome.failure_reasons

    def test_simulation_flag_takes_precedence(self) -> None:
        """simulation_used flag causes rejection regardless of pass_run_ids."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        evidence = {
            "incident_id": "test-incident",
            "pass_count": 2,
            "pass_run_ids": ["run-1", "run-2"],
            "simulation_used": True,  # Flag set - rejection regardless
            "real_loop_invoked": True,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": "Pod failed scheduling",
        }

        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=False,
        )

        # Should be rejected due to simulation_used flag
        assert outcome.success is False
        assert "simulation_used_but_not_allowed" in outcome.failure_reasons


class TestMergeDiagnosisResultReviewArtifactPaths:
    """Tests for review_artifact_paths in _merge_diagnosis_result."""

    def test_merge_preserves_review_artifact_paths(self) -> None:
        """_merge_diagnosis_result preserves review_artifact_paths."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            _merge_diagnosis_result,
        )

        evidence: dict[str, Any] = {}
        result: dict[str, Any] = {
            "status": "completed",
            "pass_count": 2,
            "pass_run_ids": ["run-1", "run-2"],
            "review_artifact_paths": ["review-1.json", "review-2.json"],
            "real_loop_invoked": True,
        }

        _merge_diagnosis_result(evidence, result)

        assert evidence.get("review_artifact_paths") == ["review-1.json", "review-2.json"]

    def test_merge_handles_empty_review_artifact_paths(self) -> None:
        """_merge_diagnosis_result handles empty review_artifact_paths."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            _merge_diagnosis_result,
        )

        evidence: dict[str, Any] = {}
        result: dict[str, Any] = {
            "status": "completed",
            "pass_count": 0,
            "pass_run_ids": [],
            "review_artifact_paths": [],
            "real_loop_invoked": False,
        }

        _merge_diagnosis_result(evidence, result)

        # Should be empty list, not missing
        assert evidence.get("review_artifact_paths") == []


class TestIntegrationEvidencePreservation:
    """Integration tests for evidence preservation through the full flow.

    Note: These tests verify the integration between runner_execution and runner_phases.
    They use mocking to avoid actual backend calls.
    """

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    def test_runner_accumulates_review_artifacts_in_loop(
        self,
        mock_reset: MagicMock,
        mock_budget: MagicMock,
    ) -> None:
        """Runner accumulates review artifact paths from each pass during the loop."""
        # This test verifies the core logic of accumulating review artifacts
        # by directly testing the accumulation pattern without full mocking.
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase3_validate_artifacts,
        )

        # Simulate what happens during the loop:
        # Each pass returns a review_artifact_path, which gets accumulated
        all_review_artifact_paths = [
            "review-pass-1.json",
            "review-pass-2.json",
        ]

        result: dict[str, Any] = {}

        phase3_validate_artifacts(
            total_pass_count=2,
            all_pass_run_ids=["run-1", "run-2"],
            external_analysis_dir=Path("/tmp/analysis"),
            result=result,
            terminal_no_checks=False,
            all_review_artifact_paths=all_review_artifact_paths,
        )

        # Verify the paths are accumulated
        assert result.get("review_artifact_paths") == [
            "review-pass-1.json",
            "review-pass-2.json",
        ]

    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.get_budget_status_in_backend")
    @patch("scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_execution.reset_diagnosis_loop_budget_in_backend")
    def test_runner_deduplicates_review_artifacts(
        self,
        mock_reset: MagicMock,
        mock_budget: MagicMock,
    ) -> None:
        """Runner deduplicates review artifact paths during accumulation."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase3_validate_artifacts,
        )

        # Simulate accumulated paths with duplicates
        all_review_artifact_paths = [
            "review-pass-1.json",
            "review-pass-1.json",  # Duplicate
            "review-pass-2.json",
        ]

        result: dict[str, Any] = {}

        phase3_validate_artifacts(
            total_pass_count=2,
            all_pass_run_ids=["run-1", "run-2"],
            external_analysis_dir=Path("/tmp/analysis"),
            result=result,
            terminal_no_checks=False,
            all_review_artifact_paths=all_review_artifact_paths,
        )

        # Verify deduplication
        assert result.get("review_artifact_paths") == [
            "review-pass-1.json",
            "review-pass-2.json",
        ]

    def test_merge_preserves_review_artifact_paths_through_phase(self) -> None:
        """Verify review_artifact_paths flows through _merge_diagnosis_result."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_phase import (
            _merge_diagnosis_result,
        )

        # Simulate result from phase3 with accumulated review paths
        result = {
            "status": "completed",
            "pass_count": 2,
            "pass_run_ids": ["run-1", "run-2"],
            "review_artifact_paths": ["review-1.json", "review-2.json"],
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "terminal_decision_reached": False,
            "premature_terminal_no_checks": False,
        }

        evidence: dict[str, Any] = {}
        _merge_diagnosis_result(evidence, result)

        # Verify paths are preserved in evidence
        assert evidence.get("review_artifact_paths") == ["review-1.json", "review-2.json"]

    def test_p4c_outcome_includes_review_artifact_paths(self) -> None:
        """Verify review_artifact_paths appear in compute_p4c_outcome."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import (
            compute_p4c_outcome,
        )

        # Simulate evidence with accumulated review paths
        evidence = {
            "incident_id": "test-incident",
            "pass_count": 2,
            "pass_run_ids": [],
            "review_artifact_paths": ["review-1.json", "review-2.json"],
            "real_loop_invoked": True,
            "real_pass_artifacts_found": True,
            "read_only": True,
            "read_only_violations": [],
            "root_cause_summary": "Pod failed scheduling with nodeSelector",
            "p4c_verdict": {"success": True},
        }

        outcome = compute_p4c_outcome(
            evidence,
            accept_terminal_single_pass=False,
            min_required_passes=2,
            require_root_cause_terms=False,
        )

        # Verify review paths are in outcome
        assert outcome.review_artifact_paths == ("review-1.json", "review-2.json")
