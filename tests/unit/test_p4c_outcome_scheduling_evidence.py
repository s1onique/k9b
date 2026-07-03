"""Regression tests for P4c scheduling evidence in compute_p4c_outcome.

Tests the control flow for structured vs prose fallback paths.
"""

from __future__ import annotations

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
