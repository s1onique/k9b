"""Tests for OTel Demo K8s-native incident discovery - Module Exports.

These tests verify the detection module exports correctly.
"""

from __future__ import annotations


class TestK8sDetectionModuleExports:
    """Test that the detection module exports correctly."""

    def test_phase_exported(self) -> None:
        """phase_p3c_verify_k8s_incident_discovery is exported."""
        from scripts.k9b_otel_demo_lab_k8s_detection import (
            phase_p3c_verify_k8s_incident_discovery,
        )

        assert callable(phase_p3c_verify_k8s_incident_discovery)

    def test_verifier_exported(self) -> None:
        """verify_unschedulable_shipping_incident_discovered is exported."""
        from scripts.k9b_otel_demo_lab_k8s_detection import (
            verify_unschedulable_shipping_incident_discovered,
        )

        assert callable(verify_unschedulable_shipping_incident_discovered)

    def test_module_imports_successfully(self) -> None:
        """k9b_otel_demo_lab_k8s_detection imports without error."""
        from scripts.k9b_otel_demo_lab_k8s_detection import (
            ACCEPTED_CANDIDATE_CLASSES,
            FAILED_SCHEDULING_PATTERNS,
            phase_p3c_verify_k8s_incident_discovery,
            verify_unschedulable_shipping_incident_discovered,
        )

        assert ACCEPTED_CANDIDATE_CLASSES is not None
        assert FAILED_SCHEDULING_PATTERNS is not None
        assert callable(phase_p3c_verify_k8s_incident_discovery)
        assert callable(verify_unschedulable_shipping_incident_discovered)

    def test_phase_exported_from_phases(self) -> None:
        """phase_p3c_verify_k8s_incident_discovery is exported from phases module."""
        from scripts.k9b_otel_demo_lab_phases import (
            phase_p3c_verify_k8s_incident_discovery,
        )

        assert callable(phase_p3c_verify_k8s_incident_discovery)

    def test_verifier_exported_from_phases(self) -> None:
        """verify_unschedulable_shipping_incident_discovered is exported from phases module."""
        from scripts.k9b_otel_demo_lab_phases import (
            verify_unschedulable_shipping_incident_discovered,
        )

        assert callable(verify_unschedulable_shipping_incident_discovered)
