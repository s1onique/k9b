"""Tests for OTel Demo K8s-native diagnosis - Module Exports.

These tests verify the K8s diagnosis module exports correctly.
"""

from __future__ import annotations


class TestK8sDiagnosisModuleExports:
    """Test that the K8s diagnosis module exports correctly."""

    def test_phase_exported_from_phases(self) -> None:
        """phase_p4c_verify_k8s_mult_pass_diagnosis is exported from phases."""
        from scripts.k9b_otel_demo_lab_phases import (
            phase_p4c_verify_k8s_mult_pass_diagnosis,
        )

        assert callable(phase_p4c_verify_k8s_mult_pass_diagnosis)

    def test_verifier_exported_from_phases(self) -> None:
        """verify_unschedulable_shipping_mult_pass_diagnosis is exported from phases."""
        from scripts.k9b_otel_demo_lab_phases import (
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        assert callable(verify_unschedulable_shipping_mult_pass_diagnosis)

    def test_module_imports_successfully(self) -> None:
        """k9b_otel_demo_lab_k8s_diagnosis imports without error."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis import (
            MIN_REQUIRED_PASSES,
            PHASE_NAME,
            phase_p4c_verify_k8s_mult_pass_diagnosis,
            verify_unschedulable_shipping_mult_pass_diagnosis,
        )

        assert callable(phase_p4c_verify_k8s_mult_pass_diagnosis)
        assert callable(verify_unschedulable_shipping_mult_pass_diagnosis)
        assert MIN_REQUIRED_PASSES == 2
        assert PHASE_NAME == "p4c-k8s-multipass-diagnosis"


class TestK8sDiagnosisConstants:
    """Test K8s diagnosis constants."""

    def test_phase_name_constant(self) -> None:
        """Phase name is correct."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import PHASE_NAME

        assert PHASE_NAME == "p4c-k8s-multipass-diagnosis"

    def test_min_required_passes(self) -> None:
        """Minimum required passes is 2."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import MIN_REQUIRED_PASSES

        assert MIN_REQUIRED_PASSES == 2

    def test_forbidden_mutating_patterns_not_empty(self) -> None:
        """Forbidden mutating patterns list is not empty."""
        from scripts.k9b_otel_demo_lab_k8s_diagnosis_constants import (
            FORBIDDEN_MUTATING_PATTERNS,
        )

        assert len(FORBIDDEN_MUTATING_PATTERNS) > 0
        assert "kubectl apply" in FORBIDDEN_MUTATING_PATTERNS
        assert "kubectl delete" in FORBIDDEN_MUTATING_PATTERNS
