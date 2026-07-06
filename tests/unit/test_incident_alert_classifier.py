"""Unit tests for alert classifier.

Tests cover:
- Explicit k9b.dev/class wins
- Explicit k9b.dev/incident.key wins
- KubePodCrashLooping maps to crash_loop
- KubeDeploymentReplicasMismatch maps to deployment_unavailable
- KubePodNotReady maps to pending_pod
- TargetDown maps to target_unreachable
- Unknown alert maps to external_alert
- Entity extraction from pod label
- Entity extraction from deployment label
- Fallback entity from alertname
"""

from __future__ import annotations

from k8s_diag_agent.incident_alert_classifier import (
    AlertIncidentClass,
    EntityKind,
    classify_alert_signal,
)
from k8s_diag_agent.incident_alert_signal import AlertSignal, AlertSourceType, AlertStatus


def _make_signal(
    alertname: str = "TestAlert",
    labels: dict | None = None,
    severity: str | None = "critical",
) -> AlertSignal:
    """Helper to create a test signal."""
    return AlertSignal(
        signal_id="test-sig-123",
        source_type=AlertSourceType.ALERTMANAGER,
        source_instance="http://alertmanager:9093",
        status=AlertStatus.FIRING,
        alertname=alertname,
        severity=severity,
        labels=tuple((k, v) for k, v in (labels or {"alertname": alertname}).items()),
    )


class TestExplicitLabels:
    """Tests for explicit k9b.dev/* label handling."""

    def test_explicit_class_wins(self):
        """Test that explicit k9b.dev/class label takes precedence."""
        signal = _make_signal(
            alertname="KubePodCrashLooping",
            labels={
                "alertname": "KubePodCrashLooping",
                "k9b.dev/class": "custom_class",
            },
        )

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.EXTERNAL_ALERT
        assert result.incident_key is None

    def test_explicit_incident_key_wins(self):
        """Test that explicit k9b.dev/incident.key label takes precedence."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "k9b.dev/incident.key": "my-custom-key",
            },
        )

        result = classify_alert_signal(signal)

        assert result.incident_key == "my-custom-key"

    def test_explicit_entity_kind(self):
        """Test that explicit k9b.dev/entity.kind label is used."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "k9b.dev/entity.kind": "deployment",
            },
        )

        result = classify_alert_signal(signal)

        assert result.entity_kind == EntityKind.DEPLOYMENT

    def test_explicit_entity_namespace(self):
        """Test that explicit k9b.dev/entity.namespace label is used."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "k9b.dev/entity.namespace": "custom-ns",
            },
        )

        result = classify_alert_signal(signal)

        assert result.namespace == "custom-ns"

    def test_explicit_entity_name(self):
        """Test that explicit k9b.dev/entity.name label is used."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "k9b.dev/entity.name": "my-entity",
            },
        )

        result = classify_alert_signal(signal)

        assert result.entity_name == "my-entity"


class TestKnownAlertnameMappings:
    """Tests for known alertname to classification mappings."""

    def test_kube_pod_crash_looping_maps_to_crash_loop(self):
        """Test that KubePodCrashLooping maps to crash_loop."""
        signal = _make_signal(alertname="KubePodCrashLooping")

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.CRASH_LOOP

    def test_kube_deployment_replicas_mismatch_maps_to_deployment_unavailable(self):
        """Test that KubeDeploymentReplicasMismatch maps to deployment_unavailable."""
        signal = _make_signal(alertname="KubeDeploymentReplicasMismatch")

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.DEPLOYMENT_UNAVAILABLE

    def test_kube_pod_not_ready_maps_to_pending_pod(self):
        """Test that KubePodNotReady maps to pending_pod."""
        signal = _make_signal(alertname="KubePodNotReady")

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.PENDING_POD

    def test_kube_pod_image_pull_backoff_maps_to_image_pull_error(self):
        """Test that KubePodImagePullBackOff maps to image_pull_error."""
        signal = _make_signal(alertname="KubePodImagePullBackOff")

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.IMAGE_PULL_ERROR

    def test_kube_node_not_ready_maps_to_node_unavailable(self):
        """Test that KubeNodeNotReady maps to node_unavailable."""
        signal = _make_signal(alertname="KubeNodeNotReady")

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.NODE_UNAVAILABLE

    def test_target_down_maps_to_target_unreachable(self):
        """Test that TargetDown maps to target_unreachable."""
        signal = _make_signal(alertname="TargetDown")

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.TARGET_UNREACHABLE

    def test_endpoint_down_maps_to_target_unreachable(self):
        """Test that EndpointDown maps to target_unreachable."""
        signal = _make_signal(alertname="EndpointDown")

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.TARGET_UNREACHABLE


class TestFallbackClassification:
    """Tests for fallback classification."""

    def test_unknown_alert_maps_to_external_alert(self):
        """Test that unknown alert maps to external_alert."""
        signal = _make_signal(alertname="UnknownAlertXYZ")

        result = classify_alert_signal(signal)

        assert result.class_ == AlertIncidentClass.EXTERNAL_ALERT


class TestEntityExtraction:
    """Tests for entity extraction from labels."""

    def test_entity_extraction_from_pod_label(self):
        """Test entity extraction from pod label."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "pod": "checkout-7d8f9c6d5-xkq2p",
                "namespace": "prod",
            },
        )

        result = classify_alert_signal(signal)

        assert result.entity_kind == EntityKind.POD
        assert result.entity_name == "checkout-7d8f9c6d5-xkq2p"
        assert result.namespace == "prod"

    def test_entity_extraction_from_deployment_label(self):
        """Test entity extraction from deployment label."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "deployment": "checkout",
                "namespace": "prod",
            },
        )

        result = classify_alert_signal(signal)

        assert result.entity_kind == EntityKind.DEPLOYMENT
        assert result.entity_name == "checkout"

    def test_entity_extraction_from_node_label(self):
        """Test entity extraction from node label."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "node": "worker-node-1",
            },
        )

        result = classify_alert_signal(signal)

        assert result.entity_kind == EntityKind.NODE
        assert result.entity_name == "worker-node-1"

    def test_entity_extraction_from_service_label(self):
        """Test entity extraction from service label."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "service": "prometheus",
                "namespace": "monitoring",
            },
        )

        result = classify_alert_signal(signal)

        assert result.entity_kind == EntityKind.SERVICE
        assert result.entity_name == "prometheus"
        assert result.namespace == "monitoring"

    def test_fallback_entity_from_alertname(self):
        """Test fallback entity from alertname."""
        signal = _make_signal(
            alertname="HighCPU",
            labels={
                "alertname": "HighCPU",
            },
        )

        result = classify_alert_signal(signal)

        assert result.entity_kind == EntityKind.ALERT
        assert result.entity_name == "HighCPU"

    def test_fallback_namespace_from_labels(self):
        """Test fallback namespace from labels."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "namespace": "default",
            },
        )

        result = classify_alert_signal(signal)

        assert result.namespace == "default"

    def test_fallback_namespace_unknown(self):
        """Test fallback namespace is 'unknown' when not present."""
        signal = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
            },
        )

        result = classify_alert_signal(signal)

        assert result.namespace == "unknown"


class TestClassificationDeterminism:
    """Tests for classification determinism."""

    def test_same_signal_produces_same_classification(self):
        """Test that same signal always produces same classification."""
        signal1 = _make_signal(
            alertname="KubePodCrashLooping",
            labels={
                "alertname": "KubePodCrashLooping",
                "pod": "test-pod",
                "namespace": "test-ns",
            },
        )
        signal2 = _make_signal(
            alertname="KubePodCrashLooping",
            labels={
                "alertname": "KubePodCrashLooping",
                "pod": "test-pod",
                "namespace": "test-ns",
            },
        )

        result1 = classify_alert_signal(signal1)
        result2 = classify_alert_signal(signal2)

        assert result1.to_dict() == result2.to_dict()

    def test_different_labels_produce_different_classification(self):
        """Test that different labels produce potentially different classification."""
        signal1 = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "pod": "pod-1",
            },
        )
        signal2 = _make_signal(
            alertname="TestAlert",
            labels={
                "alertname": "TestAlert",
                "pod": "pod-2",
            },
        )

        result1 = classify_alert_signal(signal1)
        result2 = classify_alert_signal(signal2)

        # Same class but different entity name
        assert result1.class_ == result2.class_
        assert result1.entity_name != result2.entity_name
