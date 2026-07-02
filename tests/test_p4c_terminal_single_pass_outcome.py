"""Tests for compute_p4c_outcome() - the single authoritative source for P4c outcome.

Lab-strict mode (accept_terminal_single_pass=False) is the default and required for
live lab execution. Terminal single-pass before required passes is a FAILURE.
"""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    compute_p4c_outcome,
)


class TestPrematureTerminalNoChecks:
    """Tests for premature_terminal_no_checks mode in lab-strict execution."""

    def test_p4c_rejects_terminal_single_pass_when_multipass_required(self) -> None:
        """Terminal single-pass fails when lab-strict mode requires multipass diagnosis."""
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

        # LAB-STRICT: accept_terminal_single_pass=False (default)
        outcome = compute_p4c_outcome(evidence)

        assert outcome.success is False
        assert outcome.mode == "premature_terminal_no_checks"
        assert any("premature_terminal_no_checks" in reason for reason in outcome.failure_reasons)
        assert any("missing_multipass_root_cause_confirmation" in reason for reason in outcome.failure_reasons)

    def test_p4c_rejects_terminal_single_pass_with_min_required_2(self) -> None:
        """Terminal single-pass with pass_count=1 fails when min_required_passes=2."""
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

        # Explicit min_required_passes=2 (lab-strict)
        outcome = compute_p4c_outcome(evidence, min_required_passes=2)

        assert outcome.success is False
        assert outcome.mode == "premature_terminal_no_checks"
        assert "1 < 2" in outcome.failure_reasons[0]

    def test_p4c_terminal_single_pass_requires_explicit_acceptance_flag(self) -> None:
        """Terminal single-pass requires accept_terminal_single_pass=True to succeed."""
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

        # STRICT: should fail
        strict = compute_p4c_outcome(evidence, accept_terminal_single_pass=False)
        assert strict.success is False
        assert strict.mode == "premature_terminal_no_checks"

        # PERMISSIVE: should succeed (all requirements met)
        permissive = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)
        assert permissive.success is True
        assert permissive.mode == "terminal_single_pass"

    def test_p4c_preserves_pass_run_ids_on_premature_failure(self) -> None:
        """Pass run IDs are preserved even when premature_terminal_no_checks fails."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["pass-a", "pass-b"],  # IDs collected during loop
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        # pass_run_ids should be preserved
        assert outcome.pass_run_ids == ("pass-a", "pass-b")
        assert outcome.success is False
        assert outcome.mode == "premature_terminal_no_checks"


class TestTerminalSinglePassSuccess:
    """Terminal single-pass success cases (only with accept_terminal_single_pass=True)."""

    def test_terminal_single_pass_success_with_all_requirements(self) -> None:
        """Terminal single-pass succeeds when all requirements are met and flag is set."""
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
        """Terminal single-pass succeeds with review_artifact_path instead of pass_run_ids."""
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
    """Terminal single-pass failure cases (negative cases with accept_terminal_single_pass=True)."""

    def test_terminal_single_pass_missing_terminal_decision(self) -> None:
        """Terminal mode fails when terminal_decision_reached is missing."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            # No terminal_decision_reached
            "pass_run_ids": ["run-123"],
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is False
        assert "terminal_decision_missing" in outcome.failure_reasons

    def test_terminal_single_pass_wrong_terminal_decision(self) -> None:
        """Terminal mode fails when terminal_decision_reached is not stop_no_checks_proposed."""
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
            # No pass_run_ids, no review_packet_path
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
            # No p4c_verdict with scheduling markers
            "root_cause_summary": "Some unrelated text",
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is False
        assert "missing_scheduling_root_cause_evidence" in outcome.failure_reasons


class TestMultipassMode:
    """Multipass mode tests."""

    def test_multipass_success_with_2_passes(self) -> None:
        """Multipass succeeds with 2+ passes and required evidence."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "The shipping deployment has FailedScheduling due to nodeSelector mismatch on k9b.dev/otel-lab-node",
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert outcome.success is True
        assert outcome.mode == "multipass"

    def test_multipass_failure_insufficient_passes(self) -> None:
        """Multipass fails with insufficient passes."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "The shipping deployment has FailedScheduling",
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert outcome.success is False
        assert outcome.mode == "multipass"
        assert any("insufficient_passes" in f for f in outcome.failure_reasons)

    def test_multipass_passes_only_with_multipass_root_cause_evidence(self) -> None:
        """Multipass requires root-cause evidence for scheduling."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "shipping deployment",  # Missing scheduling terms
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        # Should fail due to missing root cause terms
        assert outcome.success is False
        assert outcome.mode == "multipass"
        assert any("missing_root_cause_term" in f for f in outcome.failure_reasons)

    def test_multipass_success_with_complete_scheduling_evidence(self) -> None:
        """Multipass succeeds with complete scheduling root-cause evidence."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": (
                "The shipping deployment has FailedScheduling due to nodeSelector mismatch. "
                "Pod requires k9b.dev/otel-lab-node=missing but no node matches. "
                "This is an Unschedulable pod situation."
            ),
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert outcome.success is True
        assert outcome.mode == "multipass"
        assert outcome.root_cause_evidence_satisfied is True
        assert outcome.failure_reasons == ()


class TestLegacyCleanup:
    """Tests that terminal single-pass clears legacy stale failure reasons."""

    def test_terminal_single_pass_clears_legacy_failure_reason(self) -> None:
        """Terminal single-pass success must clear stale legacy failure_reason."""
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
            # Legacy stale values
            "failure_reason": "insufficient_passes: 1 < 2",
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=True)

        assert outcome.success is True
        assert "insufficient_passes" not in outcome.failure_reasons
        assert "missing_root_cause_term" not in outcome.failure_reasons


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


class TestTerminalModeExclusivity:
    """Regression tests for terminal mode exclusivity.

    These tests prove that:
    1. Terminal single-pass success is exclusive (no multipass failures)
    2. Non-terminal evidence correctly falls through to multipass mode
    """

    def test_terminal_mode_is_exclusive(self) -> None:
        """Terminal single-pass success must not contain multipass failure reasons."""
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

        # Core assertions
        assert outcome.success is True
        assert outcome.mode == "terminal_single_pass"
        assert outcome.failure_reasons == ()

        # Explicitly assert multipass failure reasons are absent
        failure_reasons_str = " ".join(outcome.failure_reasons)
        assert "insufficient_passes" not in failure_reasons_str
        assert "missing_root_cause_term" not in failure_reasons_str
        assert "multipass" not in failure_reasons_str

    def test_non_terminal_falls_through_to_multipass(self) -> None:
        """Non-terminal evidence (pass_count=1, not terminal) must use multipass mode."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,  # NOT terminal
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "Some text without required terms",
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        # Should fall through to multipass mode
        assert outcome.mode == "multipass"
        # And correctly fail due to insufficient passes
        assert outcome.success is False
        assert any("insufficient_passes" in f for f in outcome.failure_reasons)

    def test_premature_terminal_no_checks_mode_is_distinct(self) -> None:
        """premature_terminal_no_checks mode is distinct from multipass mode."""
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

        # LAB-STRICT: should get premature_terminal_no_checks
        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=False)

        assert outcome.mode == "premature_terminal_no_checks"
        assert outcome.success is False
        # Verify it's NOT the same as multipass insufficient_passes
        assert "insufficient_passes" not in " ".join(outcome.failure_reasons)
        assert "premature_terminal_no_checks" in outcome.failure_reasons[0]

    def test_lab_strict_terminal_after_required_passes_uses_multipass_mode(self) -> None:
        """Lab-strict mode should not return terminal_single_pass unless explicitly accepted."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": True,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "terminal_decision_reached": "stop_no_checks_proposed",
            "pass_run_ids": ["pass-a", "pass-b"],
            "root_cause_summary": (
                "The shipping pod is Unschedulable because FailedScheduling reports "
                "a nodeSelector mismatch for k9b.dev/otel-lab-node=missing."
            ),
            "p4c_verdict": {"matched_evidence": ["FailedScheduling"], "success": True},
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence, accept_terminal_single_pass=False)

        assert outcome.success is True
        assert outcome.mode == "multipass"
        assert outcome.pass_count == 2
