"""Multipass mode tests for compute_p4c_outcome()."""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    compute_p4c_outcome,
)


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
            "root_cause_summary": (
                "The shipping deployment has FailedScheduling due to nodeSelector mismatch "
                "on k9b.dev/otel-lab-node"
            ),
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
            "root_cause_summary": "shipping deployment",
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

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


class TestNonTerminalFallback:
    """Non-terminal evidence falls through to multipass mode."""

    def test_non_terminal_falls_through_to_multipass(self) -> None:
        """Non-terminal evidence must use multipass mode."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 1,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "Some text without required terms",
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(evidence)

        assert outcome.mode == "multipass"
        assert outcome.success is False
        assert any("insufficient_passes" in f for f in outcome.failure_reasons)

    def test_lab_strict_terminal_after_required_passes_uses_multipass_mode(self) -> None:
        """Lab-strict mode uses multipass when accept_terminal_single_pass=False."""
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
