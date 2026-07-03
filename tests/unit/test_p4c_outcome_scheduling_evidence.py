"""Regression tests for P4c scheduling evidence in compute_p4c_outcome.

Tests the control flow for structured vs prose fallback paths.
"""

from __future__ import annotations

import pytest

from scripts.k9b_otel_demo_lab_k8s_diagnosis_backend_p4c_outcome import compute_p4c_outcome


class TestP4cSchedulingEvidenceFallback:
    """Tests for scheduling evidence control flow in compute_p4c_outcome."""

    def test_p4c_legacy_prose_fallback_when_scheduling_evidence_missing(self) -> None:
        """Verify prose fallback works when scheduling_evidence is not present."""
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "root_cause_summary": (
                    "Deployment/shipping FailedScheduling Unschedulable "
                    "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                ),
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is True
        assert outcome.root_cause_evidence_satisfied is True

    def test_p4c_non_dict_scheduling_evidence_does_not_crash(self) -> None:
        """Verify non-dict scheduling_evidence falls back to prose without crashing."""
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "scheduling_evidence": "invalid legacy value",
                "root_cause_summary": (
                    "Deployment/shipping FailedScheduling "
                    "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                ),
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is True
        assert outcome.root_cause_evidence_satisfied is True

    @pytest.mark.parametrize(
        "malformed_scheduling_evidence",
        [None, {}, [], "bad", 42, 3.14, True],
    )
    def test_p4c_outcome_tolerates_malformed_scheduling_evidence(
        self, malformed_scheduling_evidence: object
    ) -> None:
        """Regression test: compute_p4c_outcome should not crash on malformed scheduling_evidence.

        This prevents the "'str' object has no attribute 'keys'" error that occurred
        when forensic dump modules called .keys() on non-dict values.
        """
        # Provide valid prose fallback so we can verify the function completes
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "scheduling_evidence": malformed_scheduling_evidence,
                "root_cause_summary": (
                    "Deployment/shipping FailedScheduling "
                    "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                ),
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )
        assert outcome is not None
        assert outcome.success in (True, False)
        assert isinstance(outcome.failure_reasons, tuple)

    def test_p4c_incomplete_structured_evidence_does_not_fallback_to_prose(self) -> None:
        """Verify incomplete structured evidence fails without falling back to prose.

        Even if root_cause_summary has all terms, an incomplete structured
        evidence dict should NOT fall back to prose - it should fail.
        """
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "scheduling_evidence": {
                    "workload_name": "shipping",
                    "failed_scheduling": True,
                    "root_cause_summary": "Deployment/shipping FailedScheduling",
                    # Missing: selector_key, selector_value, nodeSelector term
                },
                "root_cause_summary": (
                    "Deployment/shipping FailedScheduling "
                    "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                ),
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is False
        assert "missing_scheduling_root_cause_evidence" in outcome.failure_reasons

    def test_p4c_complete_structured_evidence_succeeds(self) -> None:
        """Verify complete structured evidence passes."""
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "scheduling_evidence": {
                    "workload_name": "shipping",
                    "selector_key": "k9b.dev/otel-lab-node",
                    "selector_value": "missing",
                    "selector_literal": "k9b.dev/otel-lab-node=missing",
                    "failed_scheduling": True,
                    "unschedulable": False,
                    "root_cause_summary": (
                        "Deployment/shipping FailedScheduling "
                        "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                    ),
                },
                "root_cause_summary": (
                    "Deployment/shipping FailedScheduling "
                    "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                ),
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is True
        assert outcome.root_cause_evidence_satisfied is True

    def test_p4c_empty_scheduling_evidence_dict_falls_back_to_prose(self) -> None:
        """Verify empty scheduling_evidence dict falls back to prose."""
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "scheduling_evidence": {},
                "root_cause_summary": (
                    "Deployment/shipping FailedScheduling "
                    "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                ),
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is True
        assert outcome.root_cause_evidence_satisfied is True

    def test_p4c_legacy_prose_fallback_requires_selector_value(self) -> None:
        """Verify fallback path still requires the exact selector literal for lab contract."""
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "root_cause_summary": (
                    "Deployment/shipping FailedScheduling "
                    "nodeSelector k9b.dev/otel-lab-node no matching node"
                ),
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is False
        assert any(
            "k9b.dev/otel-lab-node=missing" in reason
            for reason in outcome.failure_reasons
        )


class TestP4cSchedulingEvidenceEmptyProse:
    """Tests for P4c outcome with complete structured evidence but empty prose."""

    def test_p4c_succeeds_with_complete_structured_evidence_empty_prose(self) -> None:
        """Verify complete structured evidence passes even when root_cause_summary is empty.

        This is test E from the requirements: P4c outcome accepts complete structured
        evidence even when prose summary is empty.
        """
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "scheduling_evidence": {
                    "namespace": "otel-demo",
                    "workload_name": "shipping",
                    "selector_key": "k9b.dev/otel-lab-node",
                    "selector_value": "missing",
                    "selector_literal": "k9b.dev/otel-lab-node=missing",
                    "failed_scheduling": True,
                    "unschedulable": False,
                    "root_cause_summary": (
                        "Deployment/shipping FailedScheduling "
                        "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                    ),
                },
                # Empty root_cause_summary - structured evidence should still pass
                "root_cause_summary": "",
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is True, f"Expected success but got failure reasons: {outcome.failure_reasons}"
        assert outcome.root_cause_evidence_satisfied is True
        # Should not fail for missing_root_cause_term since structured evidence is complete
        assert not any("missing_root_cause_term" in r for r in outcome.failure_reasons)

    def test_p4c_succeeds_with_from_dict_reconstructed_evidence(self) -> None:
        """Verify from_dict reconstructed evidence works in P4c outcome.

        This tests the full round-trip: extract -> to_dict -> from_dict -> validate.
        """
        from src.k8s_diag_agent.collect.incident_scheduling_root_cause import (
            SchedulingRootCauseEvidence,
        )

        # Create evidence using from_dict
        original = SchedulingRootCauseEvidence(
            namespace="otel-demo",
            workload_name="shipping",
            selector_key="k9b.dev/otel-lab-node",
            selector_value="missing",
            selector_literal="k9b.dev/otel-lab-node=missing",
            failed_scheduling=True,
            unschedulable=False,
            root_cause_summary="Deployment/shipping FailedScheduling nodeSelector k9b.dev/otel-lab-node=missing no matching node",
        )

        # Round-trip through dict
        evidence_dict = original.to_dict()
        reconstructed = SchedulingRootCauseEvidence.from_dict(evidence_dict)

        # Verify round-trip preserves data
        assert reconstructed.namespace == original.namespace
        assert reconstructed.workload_name == original.workload_name
        assert reconstructed.selector_key == original.selector_key
        assert reconstructed.selector_value == original.selector_value
        assert reconstructed.failed_scheduling == original.failed_scheduling

        # Verify outcome passes with reconstructed evidence
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "scheduling_evidence": reconstructed.to_dict(),
                "root_cause_summary": "",
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is True, f"Expected success but got failure reasons: {outcome.failure_reasons}"


class TestP4cSchedulingEvidenceIncompleteStructured:
    """Tests for P4c outcome rejecting incomplete structured evidence."""

    def test_p4c_fails_with_incomplete_structured_evidence_no_fallback(self) -> None:
        """Verify incomplete structured evidence fails without falling back to prose.

        This is test F from the requirements: P4c outcome rejects incomplete
        structured evidence without compatible text fallback.
        """
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                # Incomplete structured evidence - missing selector key
                "scheduling_evidence": {
                    "workload_name": "shipping",
                    "selector_key": None,  # Missing selector key
                    "failed_scheduling": True,
                    "root_cause_summary": "Deployment/shipping FailedScheduling scheduling failure",
                },
                # Prose has all terms but structured is incomplete
                "root_cause_summary": (
                    "Deployment/shipping FailedScheduling "
                    "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                ),
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        # Should fail because structured evidence is incomplete
        assert outcome.success is False
        assert "missing_scheduling_root_cause_evidence" in outcome.failure_reasons
        # Should NOT fall back to prose and succeed
        assert not outcome.root_cause_evidence_satisfied

    def test_p4c_fails_with_non_shipping_workload_structured_evidence(self) -> None:
        """Verify non-shipping workload structured evidence fails without fallback.

        Even if the structured evidence has all required fields, if the workload
        is not 'shipping', the P4c validation should fail.
        """
        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "test-incident",
                "pass_count": 2,
                "scheduling_evidence": {
                    "workload_name": "payments",  # Not shipping
                    "selector_key": "k9b.dev/otel-lab-node",
                    "selector_value": "missing",
                    "selector_literal": "k9b.dev/otel-lab-node=missing",
                    "failed_scheduling": True,
                    "root_cause_summary": (
                        "Deployment/payments FailedScheduling "
                        "nodeSelector k9b.dev/otel-lab-node=missing no matching node"
                    ),
                },
                "root_cause_summary": "",
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        # Should fail because workload is not 'shipping'
        assert outcome.success is False
        assert outcome.root_cause_evidence_satisfied is False


class TestP4cMultipassStructuredEvidenceWithoutLLMProse:
    """Regression tests for P4c multipass accepting structured evidence without LLM prose markers.

    These tests verify that compute_p4c_outcome() accepts complete structured scheduling_evidence
    even when the prose root_cause_summary does not contain marker terms.

    This addresses the OTel Demo Lab P4c failure where:
    - Multi-pass accounting satisfied
    - Read-only constraints satisfied
    - Structured scheduling_evidence present in case file
    - But LLM prose did NOT mention scheduling markers

    The fix ensures structured evidence is validated as first-class root-cause evidence,
    not only via LLM prose text matching.
    """

    def test_multipass_accepts_structured_scheduling_evidence_without_llm_prose_markers(self) -> None:
        """Verify multipass mode accepts complete structured evidence even when prose has no markers.

        This is the primary regression test for the OTel Demo Lab P4c failure.
        The scenario:
        - Multi-pass diagnosis completed (pass_count >= 2)
        - Read-only constraints satisfied
        - Structured scheduling_evidence dict is complete
        - But root_cause_summary prose does NOT mention scheduling markers

        The P4c outcome should PASS because structured evidence proves the root cause.
        """
        # Complete structured scheduling evidence - all required fields present
        complete_scheduling_evidence = {
            "namespace": "otel-demo",
            "workload_name": "shipping",
            "selector_key": "k9b.dev/otel-lab-node",
            "selector_value": "missing",
            "selector_literal": "k9b.dev/otel-lab-node=missing",
            "failed_scheduling": True,
            "unschedulable": True,
            "scheduler_message": "0/8 nodes are available: 8 node(s) didn't match Pod's node affinity/selector",
            "root_cause_summary": (
                "Deployment/shipping in namespace otel-demo failed scheduling: "
                "pods cannot be scheduled - no nodes match nodeSelector k9b.dev/otel-lab-node=missing"
            ),
        }

        # Prose has NO scheduling markers - simulates LLM not mentioning them
        prose_without_markers = "The shipping deployment appears to have availability issues."

        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "shipping-otel-lab",
                "pass_count": 2,
                "terminal_no_checks_accepted": True,
                "real_pass_artifacts_found": True,
                "scheduling_evidence": complete_scheduling_evidence,
                "root_cause_summary": prose_without_markers,
                "read_only": True,
                "read_only_violations": [],
                # Simulate the root_cause_matches dict that would have all False
                "root_cause_matches": {
                    "mentions_shipping": False,
                    "mentions_node_selector": False,
                    "mentions_selector_key": False,
                    "mentions_selector_value": False,
                    "mentions_no_matching_node": False,
                },
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is True, (
            f"Expected success with complete structured evidence, but got: {outcome.failure_reasons}"
        )
        assert outcome.mode == "multipass"
        assert outcome.root_cause_evidence_satisfied is True
        assert "missing_scheduling_root_cause_evidence" not in outcome.failure_reasons

    def test_multipass_rejects_incomplete_structured_scheduling_evidence(self) -> None:
        """Verify multipass mode rejects incomplete structured evidence.

        The negative boundary test: even with pass_count >= 2 and read_only satisfied,
        an incomplete scheduling_evidence dict should fail P4c validation.
        """
        # Incomplete scheduling evidence - missing critical fields
        incomplete_scheduling_evidence = {
            "workload_name": "shipping",
            # Missing: selector_key, selector_value, selector_literal
            "failed_scheduling": True,
            "root_cause_summary": "Deployment/shipping failed scheduling",
        }

        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "shipping-otel-lab",
                "pass_count": 2,
                "terminal_no_checks_accepted": True,
                "real_pass_artifacts_found": True,
                "scheduling_evidence": incomplete_scheduling_evidence,
                "root_cause_summary": "The shipping deployment has issues.",
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is False
        assert "missing_scheduling_root_cause_evidence" in outcome.failure_reasons
        assert outcome.root_cause_evidence_satisfied is False

    def test_multipass_rejects_workload_name_mismatch_with_complete_evidence(self) -> None:
        """Verify multipass fails even with complete evidence if workload is not shipping.

        The OTel lab specifically requires shipping as the workload name.
        """
        complete_non_shipping_evidence = {
            "namespace": "otel-demo",
            "workload_name": "payments",  # Not the lab's shipping workload
            "selector_key": "k9b.dev/otel-lab-node",
            "selector_value": "missing",
            "selector_literal": "k9b.dev/otel-lab-node=missing",
            "failed_scheduling": True,
            "unschedulable": True,
            "root_cause_summary": "Deployment/payments in otel-demo failed scheduling",
        }

        outcome = compute_p4c_outcome(
            evidence={
                "incident_id": "payments-otel-lab",
                "pass_count": 2,
                "scheduling_evidence": complete_non_shipping_evidence,
                "root_cause_summary": "Payments deployment unavailable.",
                "read_only": True,
                "read_only_violations": [],
            },
            require_root_cause_terms=True,
        )

        assert outcome.success is False
        assert outcome.root_cause_evidence_satisfied is False
        assert "missing_scheduling_root_cause_evidence" in outcome.failure_reasons
