"""Tests for OTel Demo K8s-native incident discovery - Strict Incident Matching.

These tests verify strict incident matching - requires positive shipping match.
"""

from __future__ import annotations


class TestK8sDetectionStrictIncidentMatching:
    """Test strict incident matching - requires positive shipping match."""

    def test_match_shipping_by_deployment_name(self) -> None:
        """Incident with object_name='shipping' is matched."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_name": "shipping",
            "namespace": "otel-demo",
            "candidate_class": "pending_pod",
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is True

    def test_match_shipping_by_pod_prefix(self) -> None:
        """Incident with object_name='shipping-abc123' is matched."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_name": "shipping-abc123",
            "namespace": "otel-demo",
            "candidate_class": "pending_pod",
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is True

    def test_match_shipping_deployment_kind(self) -> None:
        """Incident with object_kind='Deployment' and 'shipping' in name is matched."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_kind": "Deployment",
            "object_name": "shipping",
            "namespace": "otel-demo",
            "candidate_class": "deployment_unavailable",
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is True

    def test_match_shipping_evidence_with_failure_pattern(self) -> None:
        """Incident with shipping + FailedScheduling in evidence is matched."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_name": "some-pod",
            "namespace": "otel-demo",
            "candidate_class": "warning_event_burst",
            "evidence": [
                {"message": "Pod shipping-xyz is Pending: FailedScheduling - Unschedulable"}
            ],
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is True

    def test_reject_namespace_mismatch(self) -> None:
        """Incident in different namespace is rejected."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_name": "shipping",
            "namespace": "other-namespace",
            "candidate_class": "pending_pod",
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is False

    def test_reject_unrelated_pending_incident(self) -> None:
        """Unrelated pending incident in same namespace is rejected (no shipping reference)."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_name": "nginx-deployment-abc123",
            "namespace": "otel-demo",
            "candidate_class": "pending_pod",
            "status": "pending",
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is False

    def test_reject_unrelated_failed_incident(self) -> None:
        """Unrelated failed incident in same namespace is rejected (no shipping reference)."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_name": "redis-pod-xyz",
            "namespace": "otel-demo",
            "candidate_class": "deployment_unavailable",
            "status": "failed",
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is False

    def test_reject_generic_pending_without_shipping(self) -> None:
        """Generic pending status alone does not match."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_name": "some-random-pod",
            "namespace": "otel-demo",
            "candidate_class": "pending_pod",
            "status": "pending",
            "evidence": [{"message": "Pod is pending"}],
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is False

    def test_reject_generic_failed_without_shipping(self) -> None:
        """Generic failed status alone does not match."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _match_shipping_incident

        incident = {
            "object_name": "other-deployment",
            "namespace": "otel-demo",
            "candidate_class": "deployment_unavailable",
            "status": "failed",
        }

        match = _match_shipping_incident(incident, "otel-demo")
        assert match is False
