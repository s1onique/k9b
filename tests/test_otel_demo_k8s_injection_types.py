"""Tests for OTel Demo K8s-native incident injection - K8sInjectionResult type.

These tests verify the K8sInjectionResult dataclass.
"""

from __future__ import annotations


class TestK8sInjectionResult:
    """Test the K8sInjectionResult dataclass."""

    def test_result_dataclass_fields(self) -> None:
        """K8sInjectionResult has required fields."""
        from scripts.k9b_otel_demo_lab_k8s_injection import K8sInjectionResult

        result = K8sInjectionResult(
            success=True,
            scenario="test-scenario",
            method="test-method",
            deployment="shipping",
            previous_template={"spec": {}},
            evidence={"test": "evidence"},
        )

        assert result.success is True
        assert result.scenario == "test-scenario"
        assert result.method == "test-method"
        assert result.deployment == "shipping"
        assert result.previous_template == {"spec": {}}
        assert result.evidence == {"test": "evidence"}
        assert result.error is None

    def test_result_with_error(self) -> None:
        """K8sInjectionResult can have an error field."""
        from scripts.k9b_otel_demo_lab_k8s_injection import K8sInjectionResult

        result = K8sInjectionResult(
            success=False,
            scenario="test-scenario",
            method="test-method",
            deployment="shipping",
            previous_template=None,
            evidence={},
            error="Something went wrong",
        )

        assert result.success is False
        assert result.error == "Something went wrong"
