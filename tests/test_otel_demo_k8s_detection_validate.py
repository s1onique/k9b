"""Tests for OTel Demo K8s-native incident discovery - Validation Logic.

These tests verify namespace, shipping reference, and evidence validation.
"""

from __future__ import annotations


class TestK8sDetectionNamespaceValidation:
    """Test namespace validation."""

    def test_validate_namespace_matches(self) -> None:
        """Namespace validation passes when namespace matches."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_namespace

        incident = {"namespace": "otel-demo"}
        result = _validate_namespace(incident, "otel-demo")
        assert result is True

    def test_validate_namespace_mismatch(self) -> None:
        """Namespace validation fails when namespace differs."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_namespace

        incident = {"namespace": "other-namespace"}
        result = _validate_namespace(incident, "otel-demo")
        assert result is False

    def test_validate_empty_namespace_accepts_all(self) -> None:
        """Empty namespace is accepted (no filtering)."""
        from typing import Any

        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_namespace

        incident: dict[str, Any] = {}
        result = _validate_namespace(incident, "otel-demo")
        assert result is True


class TestK8sDetectionShippingReferenceValidation:
    """Test shipping reference validation."""

    def test_validate_shipping_reference_by_name(self) -> None:
        """Shipping reference validated by object_name."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_shipping_reference

        incident = {"object_name": "shipping"}
        result = _validate_shipping_reference(incident)
        assert result is True

    def test_validate_shipping_reference_by_pod_name(self) -> None:
        """Shipping reference validated by pod name prefix."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_shipping_reference

        incident = {"object_name": "shipping-abc123"}
        result = _validate_shipping_reference(incident)
        assert result is True

    def test_validate_shipping_reference_by_evidence(self) -> None:
        """Shipping reference validated by evidence mention."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_shipping_reference

        incident = {
            "object_name": "some-pod",
            "evidence": [{"message": "shipping pod is pending"}],
        }
        result = _validate_shipping_reference(incident)
        assert result is True

    def test_validate_no_shipping_reference(self) -> None:
        """No shipping reference fails validation."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_shipping_reference

        incident = {"object_name": "nginx", "evidence": [{"message": "nginx is running"}]}
        result = _validate_shipping_reference(incident)
        assert result is False


class TestK8sDetectionEvidenceValidation:
    """Test evidence validation logic."""

    def test_validate_with_all_checks_pass(self) -> None:
        """Validation passes when all checks pass."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_discovery_evidence

        incident = {
            "id": "inc-123",
            "object_name": "shipping-abc",
            "signals": [{"type": "PendingPod"}],
        }

        validation = _validate_discovery_evidence(incident, "pending_pod", "otel-demo")
        assert validation["valid"] is True
        assert len(validation["checks"]) == 6  # has_id, has_class, class_accepted, has_evidence, references_shipping, namespace_matches
        assert all(c["passed"] for c in validation["checks"])

    def test_validate_rejects_unknown_candidate_class(self) -> None:
        """Validation fails for unknown candidate class."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_discovery_evidence

        incident = {
            "id": "inc-123",
            "object_name": "shipping-abc",
            "signals": [],
        }

        validation = _validate_discovery_evidence(incident, "unknown_class", "otel-demo")
        assert validation["valid"] is False

    def test_validate_rejects_no_shipping_reference(self) -> None:
        """Validation fails when shipping not in object_name and no shipping evidence."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_discovery_evidence

        # Object name is not shipping, and signals don't contain shipping
        incident = {
            "id": "inc-123",
            "object_name": "other-pod",
            "signals": [{"type": "SomeEvent", "message": "generic message"}],
        }

        validation = _validate_discovery_evidence(incident, "pending_pod", "otel-demo")
        assert validation["valid"] is False

    def test_validate_requires_evidence(self) -> None:
        """Validation fails when no evidence/signals."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_discovery_evidence

        incident = {
            "id": "inc-123",
            "object_name": "shipping",
            "signals": [],
        }

        validation = _validate_discovery_evidence(incident, "pending_pod", "otel-demo")
        assert validation["valid"] is False

    def test_validate_passes_with_warning_event_burst_and_evidence(self) -> None:
        """Validation passes for warning_event_burst with shipping in evidence."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_discovery_evidence

        # Object name not shipping, but evidence mentions shipping and FailedScheduling
        incident = {
            "id": "inc-123",
            "object_name": "some-pod",
            "signals": [
                {"type": "Warning", "message": "Pod shipping-xyz is Pending: FailedScheduling - Unschedulable"}
            ],
        }

        validation = _validate_discovery_evidence(incident, "warning_event_burst", "otel-demo")
        assert validation["valid"] is True

    def test_validate_passes_with_pending_pod_and_shipping_name(self) -> None:
        """Validation passes for pending_pod with shipping-* object name."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_discovery_evidence

        incident = {
            "id": "inc-123",
            "object_name": "shipping-abc123",
            "signals": [
                {"type": "PendingPod", "message": "Pod is pending"}
            ],
        }

        validation = _validate_discovery_evidence(incident, "pending_pod", "otel-demo")
        assert validation["valid"] is True

    def test_validate_rejects_accepted_class_with_evidence_but_no_shipping(self) -> None:
        """Validation fails for accepted class with evidence but no shipping reference."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _validate_discovery_evidence

        incident = {
            "id": "inc-123",
            "object_name": "other-deployment",
            "signals": [
                {"type": "SomeEvent", "message": "generic event without shipping reference"}
            ],
        }

        validation = _validate_discovery_evidence(incident, "pending_pod", "otel-demo")
        assert validation["valid"] is False


class TestK8sDetectionExtractionHelpers:
    """Test signal/evidence extraction helpers."""

    def test_extract_matching_signals(self) -> None:
        """Extract signals matching shipping/failure patterns."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _extract_matching_signals

        signals = [
            {"type": "PendingPod", "message": "shipping-xyz is pending"},
            {"type": "Normal", "message": "some event"},
            {"type": "FailedScheduling", "message": "Unschedulable"},
        ]

        matching = _extract_matching_signals(signals)
        assert len(matching) == 2
        assert matching[0]["type"] == "PendingPod"
        assert matching[1]["type"] == "FailedScheduling"

    def test_extract_matching_signals_empty(self) -> None:
        """Extract returns empty list when no signals match."""
        from scripts.k9b_otel_demo_lab_k8s_detection import _extract_matching_signals

        signals = [{"type": "Normal", "message": "healthy pod"}]

        matching = _extract_matching_signals(signals)
        assert len(matching) == 0
