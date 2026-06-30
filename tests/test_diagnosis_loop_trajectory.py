#!/usr/bin/env python3
"""Tests for diagnosis loop trajectory evaluation.

Tests cover:
- P4c rejects valid-looking RCA if unsafe checks occurred
- P4c rejects final RCA if pass artifacts are missing
- P4c accepts valid RCA with clean trajectory
- unschedulable-shipping golden trajectory completes in ≤2 passes
- Trajectory evaluation uses artifact fields instead of proxies
- Pass artifact schema validation
"""

from __future__ import annotations

import pytest

from k8s_diag_agent.collect.incident_diagnosis_loop_policy import (
    PASS_ARTIFACT_FIELDS,
    WARNING_GRADE_P4C_STOP_REASONS,
    DiagnosisLoopPolicy,
    LoopStopReason,
    evaluate_trajectory,
    validate_pass_artifact_schema,
)


def _make_complete_pass_artifact(
    pass_index: int,
    stop_reason: str | None,
    run_id: str,
    check_fingerprints: list[str] | None = None,
    new_evidence_hashes: list[str] | None = None,
    unsafe_check_count: int = 0,
    duplicate_check_count: int = 0,
) -> dict:
    """Helper to create a complete pass artifact with all required fields."""
    return {
        "loop_run_id": f"loop-{run_id}",
        "incident_id": "inc-123",
        "pass_index": pass_index,
        "case_file_hash": f"hash-{pass_index}",
        "proposed_checks": ["check1", "check2"],
        "accepted_checks": ["check1"] if check_fingerprints else [],
        "rejected_checks": [],
        "check_fingerprints": check_fingerprints if check_fingerprints is not None else [f"fp-{pass_index}-1"],
        "new_evidence_hashes": new_evidence_hashes if new_evidence_hashes is not None else [f"evidence-{pass_index}"],
        "duplicate_check_count": duplicate_check_count,
        "unsafe_check_count": unsafe_check_count,
        "root_cause_summary": "",
        "confidence": "medium",
        "should_continue": False,
        "stop_reason": stop_reason,
    }

class TestTrajectoryEvaluation:
    """Tests for trajectory evaluation with artifact fields."""

    def test_valid_trajectory_with_rca(self) -> None:
        """Valid trajectory passes evaluation."""
        pass_artifacts = [
            _make_complete_pass_artifact(1, LoopStopReason.NO_NEW_EVIDENCE, "run-1"),
            _make_complete_pass_artifact(
                2,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-2",
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
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
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
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
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
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
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
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
                unsafe_check_count=1,
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping pods unschedulable nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.no_unsafe_checks is False
        assert score.unsafe_check_count == 1

    def test_trajectory_passes_within_budget(self) -> None:
        """Trajectory passes when pass count within budget."""
        pass_artifacts = [
            _make_complete_pass_artifact(1, LoopStopReason.NO_NEW_EVIDENCE, "run-1"),
            _make_complete_pass_artifact(2, LoopStopReason.NO_NEW_EVIDENCE, "run-2"),
        ]
        policy = DiagnosisLoopPolicy(max_passes=2)
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.pass_count_within_budget is True
        assert score.total_passes == 2

    def test_trajectory_fails_exceeds_budget(self) -> None:
        """Trajectory fails when pass count exceeds budget."""
        pass_artifacts = [
            _make_complete_pass_artifact(1, LoopStopReason.NO_NEW_EVIDENCE, "run-1"),
            _make_complete_pass_artifact(2, LoopStopReason.NO_NEW_EVIDENCE, "run-2"),
            _make_complete_pass_artifact(3, LoopStopReason.MAX_PASSES_REACHED, "run-3"),
        ]
        policy = DiagnosisLoopPolicy(max_passes=2)
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.pass_count_within_budget is False

    def test_trajectory_stop_reason_acceptable(self) -> None:
        """Trajectory accepts root_cause_confirmed_by_evidence as stop reason."""
        pass_artifacts = [
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.stop_reason_acceptable is True

    def test_trajectory_stop_reason_high_confidence(self) -> None:
        """Trajectory accepts high_confidence_root_cause as stop reason."""
        pass_artifacts = [
            _make_complete_pass_artifact(
                1,
                LoopStopReason.HIGH_CONFIDENCE_ROOT_CAUSE,
                "run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.stop_reason_acceptable is True

    def test_trajectory_stop_reason_max_passes_warning(self) -> None:
        """max_passes_reached is warning-grade if RCA is valid."""
        pass_artifacts = [
            _make_complete_pass_artifact(1, LoopStopReason.MAX_PASSES_REACHED, "run-1"),
            _make_complete_pass_artifact(2, LoopStopReason.MAX_PASSES_REACHED, "run-2"),
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
            _make_complete_pass_artifact(1, LoopStopReason.NO_NEW_EVIDENCE, "run-1"),
            _make_complete_pass_artifact(
                2,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-2",
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
            _make_complete_pass_artifact(1, LoopStopReason.NO_NEW_EVIDENCE, "run-1"),
            _make_complete_pass_artifact(
                2,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-2",
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
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping unschedulable nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)
        d = score.to_dict()

        assert d["passed"] is True
        assert d["total_passes"] == 1
        assert d["stop_reason"] == LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE

class TestTrajectoryArtifactFieldMetrics:
    """Tests for artifact field-based metrics instead of proxies."""

    def test_duplicate_checks_use_check_fingerprints(self) -> None:
        """Duplicate check detection uses check_fingerprints, not run_id."""
        # Artifacts with same run_id but different fingerprints should NOT be duplicates
        pass_artifacts = [
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "same-run-id",  # Same run_id
                check_fingerprints=["fp-1"],
            ),
            _make_complete_pass_artifact(
                2,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "same-run-id",  # Same run_id again
                check_fingerprints=["fp-2"],  # Different fingerprint
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        # Should NOT count as duplicates because fingerprints are different
        assert score.no_duplicate_checks is True
        assert score.duplicate_check_count == 0

    def test_duplicate_checks_detected_from_repeated_fingerprints(self) -> None:
        """Duplicate checks are detected when fingerprints repeat."""
        pass_artifacts = [
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
                check_fingerprints=["fp-1", "fp-2"],
            ),
            _make_complete_pass_artifact(
                2,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-2",
                check_fingerprints=["fp-1", "fp-3"],  # fp-1 is duplicate
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.no_duplicate_checks is False
        assert score.duplicate_check_count >= 1

    def test_new_evidence_requires_new_evidence_hashes(self) -> None:
        """New evidence detection requires non-empty new_evidence_hashes."""
        # Artifact with empty new_evidence_hashes should NOT count as adding evidence
        pass_artifacts = [
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
                new_evidence_hashes=[],  # No new evidence!
            ),
        ]
        policy = DiagnosisLoopPolicy()
        # Root cause includes scheduling failure term
        root_cause = "scheduling failure shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        # Should fail because no pass added new evidence
        assert score.passed is False
        assert any("no pass added new evidence" in f for f in score.failures)
        assert score.new_evidence_pass_count == 0

    def test_new_evidence_with_non_empty_hashes(self) -> None:
        """New evidence pass count increments when new_evidence_hashes is non-empty."""
        pass_artifacts = [
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
                new_evidence_hashes=["evidence-hash-1"],
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.new_evidence_pass_count == 1
        assert score.at_least_one_pass_adds_evidence is True

    def test_unsafe_count_uses_explicit_field(self) -> None:
        """Unsafe check count uses explicit unsafe_check_count field."""
        pass_artifacts = [
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
                unsafe_check_count=3,
            ),
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.unsafe_check_count == 3
        assert score.no_unsafe_checks is False

class TestPassArtifactSchemaValidation:
    """Tests for P4c pass artifact schema validation."""

    def test_p4c_rejects_missing_pass_artifact_schema_fields(self) -> None:
        """P4c trajectory evaluation fails when pass artifacts are missing required fields."""
        # Artifact missing required fields
        pass_artifacts = [
            {
                "run_id": "run-1",
                "pass_index": 1,
                "checks_run": 1,
                "stop_reason": LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
            },
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is False
        assert score.pass_artifact_schema_valid is False
        assert len(score.pass_artifact_schema_errors) > 0

    def test_p4c_accepts_clean_schema_exact_trajectory(self) -> None:
        """P4c trajectory evaluation passes with complete schema artifacts."""
        pass_artifacts = [
            _make_complete_pass_artifact(
                1,
                LoopStopReason.ROOT_CAUSE_CONFIRMED_BY_EVIDENCE,
                "run-1",
            ),
        ]
        policy = DiagnosisLoopPolicy()
        # Root cause includes scheduling failure term
        root_cause = "scheduling failure shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        assert score.passed is True
        assert score.pass_artifact_schema_valid is True
        assert score.pass_artifact_schema_errors == []

    def test_validate_pass_artifact_schema(self) -> None:
        """Schema validation correctly identifies missing fields."""
        artifact = {field: f"value-{i}" for i, field in enumerate(PASS_ARTIFACT_FIELDS)}
        is_valid, missing = validate_pass_artifact_schema(artifact)
        assert is_valid is True
        assert missing == []

    def test_validate_pass_artifact_schema_missing(self) -> None:
        """Schema validation correctly identifies missing fields."""
        artifact = {
            "loop_run_id": "run-1",
            "incident_id": "inc-1",
        }
        is_valid, missing = validate_pass_artifact_schema(artifact)
        assert is_valid is False
        assert "pass_index" in missing
        assert "check_fingerprints" in missing

class TestTrajectoryEvaluationEdgeCases:
    """Tests for trajectory evaluation edge cases."""

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
                "loop_run_id": "loop-run-1",
                "incident_id": "inc-1",
                "pass_index": 1,
                "case_file_hash": "hash-1",
                "proposed_checks": [],
                "accepted_checks": [],
                "rejected_checks": [],
                "check_fingerprints": [],
                "new_evidence_hashes": [],
                "duplicate_check_count": 0,
                "unsafe_check_count": 0,
                "root_cause_summary": "",
                "confidence": "unknown",
                "should_continue": False,
                "stop_reason": None,  # Missing!
            },
        ]
        policy = DiagnosisLoopPolicy()
        root_cause = "shipping nodeSelector k9b.dev/otel-lab-node=missing"

        score = evaluate_trajectory(pass_artifacts, policy, root_cause)

        # Missing stop reason is not acceptable
        assert score.passed is False

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
