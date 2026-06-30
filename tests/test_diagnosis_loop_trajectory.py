#!/usr/bin/env python3
"""Tests for diagnosis loop trajectory evaluation.

Tests cover:
- P4c rejects valid-looking RCA if unsafe checks occurred
- P4c rejects final RCA if pass artifacts are missing
- P4c accepts valid RCA with clean trajectory
- unschedulable-shipping golden trajectory completes in ≤2 passes
"""

from __future__ import annotations

import pytest

from src.k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    WARNING_GRADE_P4C_STOP_REASONS,
    DiagnosisLoopPolicy,
    LoopStopReason,
    evaluate_trajectory,
)


class TestTrajectoryEvaluation:
    """Tests for trajectory evaluation."""

    def _make_pass_artifact(
        self,
        pass_index: int,
        checks_run: int = 1,
        stop_reason: str | None = None,
        run_id: str = "run-1",
    ) -> dict:
        """Helper to create a pass artifact."""
        return {
            "run_id": run_id,
            "pass_index": pass_index,
            "checks_run": checks_run,
            "checks_rejected": 0,
            "stop_reason": stop_reason,
            "runner_result": {
                "checks_run": checks_run,
                "checks_rejected": 0,
            },
        }

    def test_valid_trajectory_with_rca(self) -> None:
        """Valid trajectory passes evaluation."""
        pass_artifacts = [
            self._make_pass_artifact(1, stop_reason=LoopStopReason.NO_NEW_EVIDENCE, run_id="run-1"),
            self._make_pass_artifact(
                2,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-2",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping deployment pods unschedulable due to impossible nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is True
        assert score.root_cause_mentions_shipping is True
        assert score.root_cause_identifies_scheduling_failure is True
        assert score.root_cause_identifies_node_selector is True
        assert score.root_cause_includes_otel_lab_node_missing is True
        assert score.no_unsafe_checks is True
        assert score.stop_reason_acceptable is True

    def test_trajectory_fails_missing_shipping(self) -> None:
        """Trajectory fails if root cause doesn't mention shipping."""
        pass_artifacts = [
            self._make_pass_artifact(
                1,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "deployment has scheduling issues"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.root_cause_mentions_shipping is False
        assert "shipping" in score.failures[0]

    def test_trajectory_fails_missing_node_selector(self) -> None:
        """Trajectory fails if root cause doesn't identify nodeSelector."""
        pass_artifacts = [
            self._make_pass_artifact(
                1,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping pods unschedulable due to resource constraints"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.root_cause_identifies_node_selector is False

    def test_trajectory_fails_missing_otel_lab_node(self) -> None:
        """Trajectory fails if root cause doesn't include k9b.dev/otel-lab-node=missing."""
        pass_artifacts = [
            self._make_pass_artifact(
                1,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping pods unschedulable due to nodeSelector key=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.root_cause_includes_otel_lab_node_missing is False

    def test_trajectory_fails_unsafe_checks(self) -> None:
        """Trajectory fails if unsafe checks occurred."""
        pass_artifacts = [
            self._make_pass_artifact(
                1,
                checks_run=1,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-1",
            ),
        ]
        # Manually set unsafe_check_count in runner_result
        pass_artifacts[0]["runner_result"]["checks_rejected"] = 1

        policy = DiagnosisLoopPolicy()
        root_cause = "shipping pods unschedulable nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.no_unsafe_checks is False

    def test_trajectory_passes_within_budget(self) -> None:
        """Trajectory passes when pass count within budget."""
        pass_artifacts = [
            self._make_pass_artifact(1, run_id="run-1"),
            self._make_pass_artifact(2, run_id="run-2"),
        ]
        policy = DiagnosisLoopPolicy(max_passes=2)
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.pass_count_within_budget is True
        assert score.total_passes == 2

    def test_trajectory_fails_exceeds_budget(self) -> None:
        """Trajectory fails when pass count exceeds budget."""
        pass_artifacts = [
            self._make_pass_artifact(1, run_id="run-1"),
            self._make_pass_artifact(2, run_id="run-2"),
            self._make_pass_artifact(3, run_id="run-3"),
        ]
        policy = DiagnosisLoopPolicy(max_passes=2)
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.pass_count_within_budget is False

    def test_trajectory_stop_reason_acceptable(self) -> None:
        """Trajectory accepts root_cause_confirmed_by_evidence as stop reason."""
        pass_artifacts = [
            self._make_pass_artifact(
                1,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.stop_reason_acceptable is True

    def test_trajectory_stop_reason_high_confidence(self) -> None:
        """Trajectory accepts high_confidence_root_cause as stop reason."""
        pass_artifacts = [
            self._make_pass_artifact(
                1,
                stop_reason=LoopStopReason.HIGH_CONFIDENCE_ROOT_CAUSE,
                run_id="run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.stop_reason_acceptable is True

    def test_trajectory_stop_reason_max_passes_warning(self) -> None:
        """max_passes_reached is warning-grade if RCA is valid."""
        pass_artifacts = [
            self._make_pass_artifact(1, stop_reason=LoopStopReason.MAX_PASSES_REACHED, run_id="run-1"),
            self._make_pass_artifact(2, stop_reason=LoopStopReason.MAX_PASSES_REACHED, run_id="run-2"),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        # Warning-grade reasons are acceptable if RCA is valid
        assert score.stop_reason in WARNING_GRADE_P4C_STOP_REASONS
        assert score.root_cause_mentions_shipping is True

    def test_trajectory_stops_after_rca_confirmed(self) -> None:
        """Trajectory correctly identifies stops after RCA confirmed."""
        pass_artifacts = [
            self._make_pass_artifact(1, stop_reason=LoopStopReason.NO_NEW_EVIDENCE, run_id="run-1"),
            self._make_pass_artifact(
                2,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-2",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.stops_after_rca_confirmed is True
        assert score.stop_reason == LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE

    def test_trajectory_two_passes_within_budget(self) -> None:
        """Golden trajectory for unschedulable-shipping completes in ≤2 passes."""
        pass_artifacts = [
            self._make_pass_artifact(1, stop_reason=LoopStopReason.NO_NEW_EVIDENCE, run_id="run-1"),
            self._make_pass_artifact(
                2,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-2",
            ),
        ]
        policy = DiagnosisLoopPolicy()  # max_passes=2
        root_cause = "shipping unschedulable pod FailedScheduling nodeSelector k9b.dev/otel-lab-node=missing no matching node"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is True
        assert score.total_passes == 2
        assert score.total_passes <= policy.max_passes

    def test_trajectory_score_to_dict(self) -> None:
        """TrajectoryScore serializes to dict correctly."""
        pass_artifacts = [
            self._make_pass_artifact(
                1,
                stop_reason=LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                run_id="run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping unschedulable nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)
        d = score.to_dict()

        assert d["passed"] is True
        assert d["total_passes"] == 1
        assert d["stop_reason"] == LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE


class TestTrajectoryEvaluationEdgeCases:
    """Tests for trajectory evaluation edge cases."""

    def _make_pass_artifact(self, pass_index: int, stop_reason: str | None, run_id: str = "run-1") -> dict:
        """Helper to create a pass artifact."""
        return {
            "run_id": run_id,
            "pass_index": pass_index,
            "checks_run": 1,
            "stop_reason": stop_reason,
            "runner_result": {"checks_run": 1, "checks_rejected": 0},
        }

    def test_empty_pass_artifacts(self) -> None:
        """Empty pass artifacts fails evaluation."""
        pass_artifacts: list[dict] = []
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.total_passes == 0

    def test_missing_stop_reason(self) -> None:
        """Missing stop reason fails evaluation."""
        pass_artifacts = [
            {
                "run_id": "run-1",
                "pass_index": 1,
                "checks_run": 1,
                "stop_reason": None,
            },
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        # Missing stop reason is not acceptable
        assert score.passed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
