"""Multipass mode tests for compute_p4c_outcome()."""

from __future__ import annotations

import pytest

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
                "on k9b.dev/otel-lab-node=missing"
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

    def test_multipass_generic_mode_succeeds_without_root_cause_evidence(self) -> None:
        """Generic multipass (default) succeeds without root-cause evidence."""
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

        # Generic multipass (require_root_cause_terms=False, default) does NOT require evidence
        outcome = compute_p4c_outcome(evidence)

        assert outcome.success is True
        assert outcome.mode == "multipass"
        assert outcome.root_cause_evidence_satisfied is True

    def test_multipass_lab_strict_mode_requires_root_cause_evidence(self) -> None:
        """Lab-strict multipass requires root-cause evidence for scheduling."""
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

        # Lab-strict multipass (require_root_cause_terms=True) requires evidence
        outcome = compute_p4c_outcome(evidence, require_root_cause_terms=True)

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


class TestSchedulingEvidenceBoundaryRobustness:
    """Regression tests for malformed scheduling_evidence boundary handling.
    
    These tests ensure that compute_p4c_outcome() does not crash on
    malformed/missing scheduling_evidence. Missing/legacy evidence should
    fail semantically, not explode mechanically.
    """

    @pytest.mark.parametrize("scheduling_evidence", [None, {}, [], "bad", 42])
    def test_p4c_scheduling_evidence_boundary_is_non_crashing(
        self, scheduling_evidence: object
    ) -> None:
        """Malformed scheduling_evidence should not raise an exception.
        
        Expected behavior: no exception, falls back to prose/structured evidence check.
        If neither can prove the root cause, returns a deterministic failure.
        """
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "scheduling_evidence": scheduling_evidence,
            "root_cause_summary": (
                "The shipping deployment has FailedScheduling due to nodeSelector mismatch "
                "on k9b.dev/otel-lab-node=missing"
            ),
            "read_only": True,
            "read_only_violations": [],
        }
        
        # Should not raise
        outcome = compute_p4c_outcome(evidence)
        
        # Should have a deterministic result (success depends on evidence completeness)
        assert outcome is not None
        assert isinstance(outcome.success, bool)

    def test_p4c_none_scheduling_evidence_falls_back_to_prose(self) -> None:
        """None scheduling_evidence falls back to prose term checking."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "scheduling_evidence": None,
            # Complete prose evidence should satisfy FALLBACK
            "root_cause_summary": (
                "The shipping deployment has FailedScheduling due to nodeSelector mismatch "
                "on k9b.dev/otel-lab-node=missing"
            ),
            "read_only": True,
            "read_only_violations": [],
        }
        
        outcome = compute_p4c_outcome(evidence)
        
        # With complete prose evidence, should succeed
        assert outcome.success is True

    def test_p4c_empty_dict_scheduling_evidence_falls_back_to_prose(self) -> None:
        """Empty dict scheduling_evidence falls back to prose term checking."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "scheduling_evidence": {},
            # Complete prose evidence should satisfy FALLBACK
            "root_cause_summary": (
                "The shipping deployment has FailedScheduling due to nodeSelector mismatch "
                "on k9b.dev/otel-lab-node=missing"
            ),
            "read_only": True,
            "read_only_violations": [],
        }
        
        outcome = compute_p4c_outcome(evidence)
        
        # With complete prose evidence, should succeed
        assert outcome.success is True
