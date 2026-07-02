"""Terminal single-pass success and failure cases."""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    compute_p4c_outcome,
)


class TestTerminalSinglePassSuccess:
    """Terminal single-pass success cases."""

    def test_terminal_single_pass_success_with_all_requirements(self) -> None:
        """All requirements met and flag set."""
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

        assert outcome.success is True
        assert outcome.mode == "terminal_single_pass"
        assert outcome.terminal_decision == "stop_no_checks_proposed"
        assert len(outcome.pass_run_ids) > 0
        assert outcome.failure_reasons == ()

    def test_terminal_single_pass_success_with_review_artifact(self) -> None:
        """review_artifact_path instead of pass_run_ids."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "review_packet_path": "/artifacts/review/test.json",
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is True
        assert len(outcome.review_artifact_paths) > 0


class TestTerminalSinglePassFailure:
    """Terminal single-pass failure cases."""

    def test_terminal_single_pass_missing_terminal_decision(self) -> None:
        """Terminal mode fails when terminal_decision_reached is missing."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is False
        assert "terminal_decision_missing" in outcome.failure_reasons

    def test_terminal_single_pass_wrong_terminal_decision(self) -> None:
        """Terminal mode fails when terminal_decision is not stop_no_checks_proposed."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_checks_proposed",
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is False
        assert any("terminal_decision_unexpected" in f for f in outcome.failure_reasons)

    def test_terminal_single_pass_missing_artifact_reference(self) -> None:
        """Terminal mode fails when no pass_run_ids and no review_artifact_paths."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is False
        assert "missing_review_artifact_reference" in outcome.failure_reasons

    def test_terminal_single_pass_read_only_violated(self) -> None:
        """Terminal mode fails when read-only constraints are violated."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": False,
            "read_only_violations": ["kubectl_apply_attempted"],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is False
        assert outcome.read_only_constraints_satisfied is False
        assert any("read_only_contract_violated" in f for f in outcome.failure_reasons)

    def test_terminal_single_pass_missing_scheduling_evidence(self) -> None:
        """Terminal mode fails when scheduling evidence is missing."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["run-123"],
            "root_cause_summary": "Some unrelated text",
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is False
        assert "missing_scheduling_root_cause_evidence" in outcome.failure_reasons


class TestTerminalModeExclusivity:
    """Terminal mode exclusivity regression tests."""

    def test_terminal_mode_is_exclusive(self) -> None:
        """Terminal single-pass success excludes multipass failure reasons."""
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

        assert outcome.success is True
        assert outcome.mode == "terminal_single_pass"
        assert outcome.failure_reasons == ()
        failure_reasons_str = " ".join(outcome.failure_reasons)
        assert "insufficient_passes" not in failure_reasons_str
        assert "missing_root_cause_term" not in failure_reasons_str
        assert "multipass" not in failure_reasons_str


class TestLegacyCleanup:
    """Tests that terminal single-pass clears legacy stale failure reasons."""

    def test_terminal_single_pass_clears_legacy_failure_reason(self) -> None:
        """Terminal single-pass success clears stale legacy failure_reason."""
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
            "failure_reason": "insufficient_passes: 1 < 2",
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is True
        assert "insufficient_passes" not in outcome.failure_reasons
        assert "missing_root_cause_term" not in outcome.failure_reasons
