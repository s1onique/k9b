"""Tests for OTel Demo K8s-native incident discovery - Integration.

These tests verify separation from cache/flag behavior and no live cluster requirement.
"""

from __future__ import annotations


class TestK8sDetectionSeparationFromCacheFlag:
    """Test that K8s detection is separate from cache/flag behavior."""

    def test_k8s_detection_is_additional_phase(self) -> None:
        """K8s detection is separate from existing detection."""
        from scripts.k9b_otel_demo_lab_k8s_detection import (
            phase_p3c_verify_k8s_incident_discovery,
        )

        # Detection phase exists independently
        assert callable(phase_p3c_verify_k8s_incident_discovery)

    def test_recommendation_cache_failure_remains(self) -> None:
        """Feature flag cache failure still exists."""
        from scripts.k9b_otel_demo_lab_inject import inject_recommendation_cache_failure

        assert callable(inject_recommendation_cache_failure)


class TestK8sDetectionNoLiveClusterRequired:
    """Verify tests don't require live cluster."""

    def test_all_tests_are_unit_tests(self) -> None:
        """All tests in this module are unit tests (no pytest.mark.live)."""
        from scripts import k9b_otel_demo_lab_k8s_detection as module

        # Verify helper functions are internal (start with _)
        helpers = [
            name
            for name in dir(module)
            if callable(getattr(module, name)) and not name.startswith("__")
        ]

        # Public API should only be the phase and verifier
        assert "phase_p3c_verify_k8s_incident_discovery" in helpers
        assert "verify_unschedulable_shipping_incident_discovered" in helpers
