"""Tests for require_root_cause_terms parameter in compute_p4c_outcome()."""

from __future__ import annotations

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_contracts import (
    compute_p4c_outcome,
)


class TestRequireRootCauseTermsParameter:
    """Tests for require_root_cause_terms parameter."""

    def test_requires_root_cause_terms_when_true(self) -> None:
        """Root cause terms are required when require_root_cause_terms=True."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "Generic deployment unavailable",  # Missing scheduling terms
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(
            evidence,
            require_root_cause_terms=True,
        )

        assert outcome.success is False
        assert any("missing_root_cause_term" in f for f in outcome.failure_reasons)

    def test_skips_root_cause_terms_when_false(self) -> None:
        """Root cause terms are skipped when require_root_cause_terms=False."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "Generic deployment unavailable",  # Missing scheduling terms
            "read_only": True,
            "read_only_violations": [],
        }

        outcome = compute_p4c_outcome(
            evidence,
            require_root_cause_terms=False,
        )

        assert outcome.success is True
        assert outcome.root_cause_evidence_satisfied is True
        assert outcome.failure_reasons == ()

    def test_assumes_root_cause_satisfied_when_terms_skipped_and_no_verdict_present(self) -> None:
        """Root cause evidence is assumed satisfied when require_root_cause_terms=False and no p4c_verdict.

        This is the intentional permissive/product-mode behavior: when terms are not required
        and there is no p4c_verdict to check, we assume root cause evidence is satisfied.
        """
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "Generic deployment unavailable",
            "read_only": True,
            "read_only_violations": [],
            # No p4c_verdict
        }

        outcome = compute_p4c_outcome(
            evidence,
            require_root_cause_terms=False,
        )

        # Should succeed because require_root_cause_terms=False skips prose check
        # and no p4c_verdict means root_cause_evidence is assumed satisfied
        assert outcome.success is True

    def test_scheduling_evidence_required_when_both_roots_missing(self) -> None:
        """Both prose and p4c_verdict are checked when require_root_cause_terms=True."""
        evidence = {
            "real_loop_invoked": True,
            "terminal_no_checks_accepted": False,
            "pass_count": 2,
            "real_pass_artifacts_found": True,
            "incident_id": "test-incident",
            "root_cause_summary": "Generic deployment unavailable",  # Missing prose terms
            "read_only": True,
            "read_only_violations": [],
            "p4c_verdict": {"success": False},  # p4c_verdict also fails
        }

        outcome = compute_p4c_outcome(
            evidence,
            require_root_cause_terms=True,
        )

        assert outcome.success is False
        assert outcome.root_cause_evidence_satisfied is False
