"""Tests for phase3_validate_artifacts terminal single-pass detection.

These tests verify that phase3_validate_artifacts correctly detects and flags
premature terminal no-checks (terminal reached but insufficient passes) in
lab-strict mode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    FAILURE_TARGETED_INSUFFICIENT_PASSES,
)


class TestPhase3TerminalValidation:
    """Tests for phase3_validate_artifacts with terminal single-pass."""

    def test_premature_terminal_single_pass_detected(self) -> None:
        """LAB-STRICT: Terminal no-checks with 1 pass is premature and must be flagged.

        The phase3_validate_artifacts now correctly detects premature terminal no-checks
        (terminal reached but insufficient passes) and sets failure_reason.
        The final success/failure determination is made by compute_p4c_outcome() in phase.py.
        """
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase3_validate_artifacts,
        )

        result: dict[str, Any] = {}
        external_dir = Path("/tmp/analysis")

        # With terminal_no_checks=True and total_pass_count=1 (premature case)
        updated_result = phase3_validate_artifacts(
            total_pass_count=1,
            all_pass_run_ids=["auto-test-run"],
            external_analysis_dir=external_dir,
            result=result,
            terminal_no_checks=True,
        )

        # LAB-STRICT: Should detect premature terminal and set failure_reason
        # The premature_terminal_no_checks flag is set for compute_p4c_outcome()
        assert updated_result.get("premature_terminal_no_checks") is True
        assert updated_result.get("failure_reason") is not None
        assert "premature_terminal_no_checks" in updated_result.get("failure_reason", "")
        assert updated_result.get("real_pass_artifacts_found") is True  # Still set True for compute_p4c_outcome
        assert updated_result.get("pass_count") == 1

    def test_valid_terminal_with_sufficient_passes(self) -> None:
        """Terminal no-checks with sufficient passes should not set premature flag."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase3_validate_artifacts,
        )

        result: dict[str, Any] = {}
        external_dir = Path("/tmp/analysis")

        # With terminal_no_checks=True and total_pass_count=2 (sufficient)
        updated_result = phase3_validate_artifacts(
            total_pass_count=2,
            all_pass_run_ids=["auto-test-run-1", "auto-test-run-2"],
            external_analysis_dir=external_dir,
            result=result,
            terminal_no_checks=True,
        )

        # Should NOT detect premature (sufficient passes)
        assert updated_result.get("premature_terminal_no_checks") is not True
        assert updated_result.get("failure_reason") is None  # No failure in phase3
        assert updated_result.get("real_pass_artifacts_found") is True
        assert updated_result.get("pass_count") == 2

    def test_non_terminal_single_pass_fails(self) -> None:
        """Non-terminal single pass should still fail (require 2 passes)."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_runner_phases import (
            phase3_validate_artifacts,
        )

        result: dict[str, Any] = {}
        external_dir = Path("/tmp/analysis")

        # Without terminal_no_checks (or False) and total_pass_count=1
        updated_result = phase3_validate_artifacts(
            total_pass_count=1,
            all_pass_run_ids=["auto-test-run"],
            external_analysis_dir=external_dir,
            result=result,
            terminal_no_checks=False,
        )

        # Should fail with insufficient_passes
        assert updated_result.get("failure_reason") == FAILURE_TARGETED_INSUFFICIENT_PASSES
        assert updated_result.get("real_pass_artifacts_found") is False
