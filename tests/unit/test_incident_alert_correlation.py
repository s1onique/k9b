"""Unit tests for alert correlation key builder.

Tests cover:
- Correlation key is deterministic
- Correlation key excludes dynamic annotation values
- Explicit incident key wins
- Correct key format for various scenarios
"""

from __future__ import annotations

from k8s_diag_agent.incident_alert_classifier import (
    AlertIncidentClass,
    AlertIncidentClassification,
    EntityKind,
)
from k8s_diag_agent.incident_alert_correlation import build_alert_incident_correlation_key
from k8s_diag_agent.incident_alert_signal import AlertSignal, AlertSourceType, AlertStatus


def _make_signal(
    alertname: str = "TestAlert",
    source_instance: str = "http://alertmanager:9093",
    labels: dict | None = None,
    annotations: dict | None = None,
) -> AlertSignal:
    """Helper to create a test signal."""
    return AlertSignal(
        signal_id="test-sig-123",
        source_type=AlertSourceType.ALERTMANAGER,
        source_instance=source_instance,
        status=AlertStatus.FIRING,
        alertname=alertname,
        severity="critical",
        labels=tuple((k, v) for k, v in (labels or {"alertname": alertname}).items()),
        annotations=tuple((k, v) for k, v in (annotations or {}).items()),
    )


def _make_classification(
    class_: AlertIncidentClass = AlertIncidentClass.EXTERNAL_ALERT,
    entity_kind: EntityKind = EntityKind.ALERT,
    entity_name: str = "TestAlert",
    namespace: str = "prod",
    incident_key: str | None = None,
    source_instance: str | None = "http://alertmanager:9093",
) -> AlertIncidentClassification:
    """Helper to create a test classification."""
    return AlertIncidentClassification(
        class_=class_,
        entity_kind=entity_kind,
        entity_name=entity_name,
        namespace=namespace,
        incident_key=incident_key,
        source_instance=source_instance,
    )


class TestExplicitIncidentKey:
    """Tests for explicit incident key handling."""

    def test_explicit_incident_key_wins(self):
        """Test that explicit incident key is used directly."""
        signal = _make_signal()
        classification = _make_classification(
            incident_key="my-custom-key",
        )

        result = build_alert_incident_correlation_key(signal, classification)

        assert result == "my-custom-key"

    def test_explicit_key_normalized(self):
        """Test that explicit incident key is normalized."""
        signal = _make_signal()
        classification = _make_classification(
            incident_key="My-Custom-KEY_With_Special!Chars",
        )

        result = build_alert_incident_correlation_key(signal, classification)

        # Should be normalized to lowercase with special chars replaced
        assert result == "my-custom-key-with-special-chars"


class TestCorrelationKeyFormat:
    """Tests for correlation key format."""

    def test_correct_format(self):
        """Test correct key format: source:class:namespace:entity_kind:entity_name."""
        signal = _make_signal(source_instance="alertmanager-main")
        classification = _make_classification(
            class_=AlertIncidentClass.CRASH_LOOP,
            entity_kind=EntityKind.POD,
            entity_name="checkout-7d8f",
            namespace="prod",
            source_instance="alertmanager-main",
        )

        result = build_alert_incident_correlation_key(signal, classification)

        assert result == "alertmanager-main:crash_loop:prod:pod:checkout-7d8f"

    def test_deployment_key_format(self):
        """Test key format for deployment incidents."""
        signal = _make_signal(source_instance="alertmanager-main")
        classification = _make_classification(
            class_=AlertIncidentClass.DEPLOYMENT_UNAVAILABLE,
            entity_kind=EntityKind.DEPLOYMENT,
            entity_name="checkout",
            namespace="prod",
            source_instance="alertmanager-main",
        )

        result = build_alert_incident_correlation_key(signal, classification)

        assert result == "alertmanager-main:deployment_unavailable:prod:deployment:checkout"

    def test_service_key_format(self):
        """Test key format for service incidents."""
        signal = _make_signal(source_instance="alertmanager-main")
        classification = _make_classification(
            class_=AlertIncidentClass.TARGET_UNREACHABLE,
            entity_kind=EntityKind.SERVICE,
            entity_name="prometheus",
            namespace="monitoring",
            source_instance="alertmanager-main",
        )

        result = build_alert_incident_correlation_key(signal, classification)

        assert result == "alertmanager-main:target_unreachable:monitoring:service:prometheus"


class TestCorrelationKeyDeterminism:
    """Tests for correlation key determinism."""

    def test_same_inputs_produce_same_key(self):
        """Test that same inputs always produce same key."""
        signal1 = _make_signal(source_instance="test-instance")
        classification1 = _make_classification(
            class_=AlertIncidentClass.CRASH_LOOP,
            entity_kind=EntityKind.POD,
            entity_name="test-pod",
            namespace="default",
            source_instance="test-instance",
        )

        signal2 = _make_signal(source_instance="test-instance")
        classification2 = _make_classification(
            class_=AlertIncidentClass.CRASH_LOOP,
            entity_kind=EntityKind.POD,
            entity_name="test-pod",
            namespace="default",
            source_instance="test-instance",
        )

        key1 = build_alert_incident_correlation_key(signal1, classification1)
        key2 = build_alert_incident_correlation_key(signal2, classification2)

        assert key1 == key2

    def test_different_inputs_produce_different_keys(self):
        """Test that different inputs produce different keys."""
        signal1 = _make_signal(source_instance="test-instance")
        classification1 = _make_classification(
            class_=AlertIncidentClass.CRASH_LOOP,
            entity_kind=EntityKind.POD,
            entity_name="pod-1",
            namespace="default",
            source_instance="test-instance",
        )

        signal2 = _make_signal(source_instance="test-instance")
        classification2 = _make_classification(
            class_=AlertIncidentClass.CRASH_LOOP,
            entity_kind=EntityKind.POD,
            entity_name="pod-2",
            namespace="default",
            source_instance="test-instance",
        )

        key1 = build_alert_incident_correlation_key(signal1, classification1)
        key2 = build_alert_incident_correlation_key(signal2, classification2)

        assert key1 != key2

    def test_case_normalization(self):
        """Test that case is normalized."""
        signal1 = _make_signal(source_instance="Alertmanager-MAIN")
        classification1 = _make_classification(
            entity_name="MyPod",
            namespace="Prod",
            source_instance="Alertmanager-MAIN",
        )

        signal2 = _make_signal(source_instance="alertmanager-main")
        classification2 = _make_classification(
            entity_name="mypod",
            namespace="prod",
            source_instance="alertmanager-main",
        )

        key1 = build_alert_incident_correlation_key(signal1, classification1)
        key2 = build_alert_incident_correlation_key(signal2, classification2)

        assert key1 == key2


class TestCorrelationKeyExcludesDynamicValues:
    """Tests that correlation keys exclude dynamic values."""

    def test_excludes_annotations(self):
        """Test that annotations are not included in correlation key."""
        signal_with_annotations = _make_signal(
            annotations={"metric_value": "95.5", "description": "CPU above threshold"},
        )
        signal_without_annotations = _make_signal(
            annotations={},
        )
        classification = _make_classification()

        key_with = build_alert_incident_correlation_key(signal_with_annotations, classification)
        key_without = build_alert_incident_correlation_key(signal_without_annotations, classification)

        # Keys should be the same since annotations are not used
        assert key_with == key_without

    def test_excludes_group_key(self):
        """Test that Alertmanager groupKey is not used in correlation key."""
        signal = _make_signal()
        classification = _make_classification()

        # The correlation key should be based on entity fields, not groupKey
        result = build_alert_incident_correlation_key(signal, classification)

        # Verify key format doesn't include groupKey-like patterns
        assert "{" not in result
        assert "}" not in result
        assert "=" not in result

    def test_excludes_dynamic_metric_values(self):
        """Test that dynamic metric values don't affect correlation key."""
        # Create signals with different metric values in labels
        signal1 = _make_signal(
            labels={
                "alertname": "HighCPU",
                "namespace": "prod",
                "cpu_usage_percent": "95.5",  # Dynamic value
            },
        )
        signal2 = _make_signal(
            labels={
                "alertname": "HighCPU",
                "namespace": "prod",
                "cpu_usage_percent": "75.2",  # Different dynamic value
            },
        )
        classification = _make_classification(
            entity_kind=EntityKind.SERVICE,  # Not using container
            entity_name="HighCPU",
        )

        # Both should produce the same key since we're using entity fields
        key1 = build_alert_incident_correlation_key(signal1, classification)
        key2 = build_alert_incident_correlation_key(signal2, classification)

        assert key1 == key2


class TestCorrelationKeyNormalization:
    """Tests for key component normalization."""

    def test_special_characters_normalized(self):
        """Test that special characters are normalized to hyphens."""
        signal = _make_signal(source_instance="test.instance.com")
        classification = _make_classification(
            entity_name="my-service_v1",
            namespace="my-namespace",
        )

        result = build_alert_incident_correlation_key(signal, classification)

        # Should have normalized to lowercase with hyphens
        assert "my-service-v1" in result
        assert "my-namespace" in result

    def test_empty_source_instance_defaults_to_unknown(self):
        """Test that empty source instance defaults to 'unknown'."""
        signal = _make_signal(source_instance="")
        classification = _make_classification(
            source_instance="",
        )

        result = build_alert_incident_correlation_key(signal, classification)

        assert result.startswith("unknown:")

    def test_empty_namespace_defaults_to_unknown(self):
        """Test that empty namespace defaults to 'unknown'."""
        signal = _make_signal()
        classification = _make_classification(
            namespace="",
        )

        result = build_alert_incident_correlation_key(signal, classification)

        assert ":unknown:" in result
