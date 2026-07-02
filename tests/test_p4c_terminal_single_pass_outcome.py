"""Tests for compute_p4c_outcome() - premature_terminal_no_checks mode in lab-strict execution."""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    compute_p4c_outcome,
)


class TestPrematureTerminalNoChecks:
    """Tests for premature_terminal_no_checks mode in lab-strict execution."""

    def test_p4c_rejects_terminal_single_pass_when_multipass_required(self) -> None:
        """Lab-strict: terminal single-pass fails when multipass required."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert outcome.success is False
        assert outcome.mode == "premature_terminal_no_checks"
        assert any("premature_terminal_no_checks" in reason for reason in outcome.failure_reasons)
        assert any("missing_multipass_root_cause_confirmation" in reason for reason in outcome.failure_reasons)

    def test_p4c_rejects_terminal_single_pass_with_min_required_2(self) -> None:
        """pass_count=1 fails when min_required_passes=2."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, min_required_passes=2)

        assert outcome.success is False
        assert outcome.mode == "premature_terminal_no_checks"
        assert "1 < 2" in outcome.failure_reasons[0]

    def test_p4c_terminal_single_pass_requires_explicit_acceptance_flag(self) -> None:
        """accept_terminal_single_pass=True required for terminal success."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        strict = compute_p4c_outcome(evidence, accept_terminal_single_pass=False)
        assert strict.success is False
        assert strict.mode == "premature_terminal_no_checks"

        permissive = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)
        assert permissive.success is True
        assert permissive.mode == "terminal_single_pass"

    def test_p4c_preserves_pass_run_ids_on_premature_failure(self) -> None:
        """Pass run IDs preserved even when premature_terminal_no_checks fails."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["pass-a", "pass-b"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert outcome.pass_run_ids == ("pass-a", "pass-b")
        assert outcome.success is False
        assert outcome.mode == "premature_terminal_no_checks"


class TestPrematureModeIsDistinct:
    """premature_terminal_no_checks mode is distinct from multipass mode."""

    def test_premature_terminal_no_checks_mode_is_distinct(self) -> None:
        """premature_terminal_no_checks mode is distinct from multipass insufficient_passes."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=False)

        assert outcome.mode == "premature_terminal_no_checks"
        assert outcome.success is False
        assert "insufficient_passes" not in " ".join(outcome.failure_reasons)
        assert "premature_terminal_no_checks" in outcome.failure_reasons[0]


class TestNormalizedOutcomeStructure:
    """Tests for normalized outcome structure."""

    def test_outcome_has_all_required_fields(self) -> None:
        """Normalized outcome must have all required fields."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is not None
        assert outcome.mode in ("multipass", "terminal_single_pass", "premature_terminal_no_checks")
        assert isinstance(outcome.pass_count, int)
        assert isinstance(outcome.pass_run_ids, tuple)
        assert isinstance(outcome.review_artifact_paths, tuple)
        assert isinstance(outcome.read_only_constraints_satisfied, bool)
        assert isinstance(outcome.root_cause_evidence_satisfied, bool)
        assert isinstance(outcome.failure_reasons, tuple)
