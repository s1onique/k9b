"""Tests for OTel Demo K8s-native incident injection - Constants.

These tests verify that K8s injection constants are correctly defined.
"""

from __future__ import annotations


class TestK8sInjectionConstants:
    """Test that K8s injection constants are correctly defined."""

    def test_shipping_deployment_is_correct(self) -> None:
        """Target workload is 'shipping' per chart 0.40.9 naming."""
        from scripts.k9b_otel_demo_lab_constants import SHIPPING_DEPLOYMENT

        assert SHIPPING_DEPLOYMENT == "shipping"

    def test_node_selector_key_is_correct(self) -> None:
        """nodeSelector key is 'k9b.dev/otel-lab-node'."""
        from scripts.k9b_otel_demo_lab_constants import K8S_INJECTION_NODE_SELECTOR_KEY

        assert K8S_INJECTION_NODE_SELECTOR_KEY == "k9b.dev/otel-lab-node"

    def test_node_selector_value_is_missing(self) -> None:
        """nodeSelector value is 'missing' (no node has this label)."""
        from scripts.k9b_otel_demo_lab_constants import K8S_INJECTION_NODE_SELECTOR_VALUE

        assert K8S_INJECTION_NODE_SELECTOR_VALUE == "missing"

    def test_failure_classes_defined(self) -> None:
        """Failure classes for K8s injection are defined."""
        from scripts.k9b_otel_demo_lab_constants import (
            FAILURE_K8S_INJECTION_FAILED,
            FAILURE_K8S_INJECTION_NO_SYMPTOM,
        )

        assert FAILURE_K8S_INJECTION_FAILED == "k8s_injection_failed"
        assert FAILURE_K8S_INJECTION_NO_SYMPTOM == "k8s_injection_no_symptom"
