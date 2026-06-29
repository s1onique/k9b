"""Tests for OTel Demo K8s-native incident injection - Module Exports.

These tests verify the K8s injection module exports correctly.
"""

from __future__ import annotations


class TestK8sInjectionModuleExports:
    """Test that the K8s injection module exports correctly."""

    def test_phase_exported_from_phases(self) -> None:
        """phase_p2b_inject_unschedulable_shipping_rollout is exported from phases."""
        from scripts.k9b_otel_demo_lab_phases import (
            phase_p2b_inject_unschedulable_shipping_rollout,
        )

        assert callable(phase_p2b_inject_unschedulable_shipping_rollout)

    def test_cleanup_exported_from_phases(self) -> None:
        """cleanup_unschedulable_shipping_rollout is exported from phases."""
        from scripts.k9b_otel_demo_lab_phases import (
            cleanup_unschedulable_shipping_rollout,
        )

        assert callable(cleanup_unschedulable_shipping_rollout)

    def test_module_imports_successfully(self) -> None:
        """k9b_otel_demo_lab_k8s_injection imports without error."""
        from scripts.k9b_otel_demo_lab_k8s_injection import (
            K8sInjectionResult,
            cleanup_unschedulable_shipping_rollout,
            phase_p2b_inject_unschedulable_shipping_rollout,
        )

        assert K8sInjectionResult is not None
        assert callable(phase_p2b_inject_unschedulable_shipping_rollout)
        assert callable(cleanup_unschedulable_shipping_rollout)
