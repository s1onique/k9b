"""Unit tests for AlertSignal normalizer.

Tests cover:
- normalize_alertmanager_payload function
- Single firing alert normalization
- Resolved alert normalization
- Grouped payload splitting
- Source type inference (alertmanager vs vmalert)
- Missing/invalid fields handling
- Large label/annotation bounds enforcement
"""

from __future__ import annotations

from datetime import UTC, datetime

from k8s_diag_agent.incident_alert_signal import (
    AlertSourceType,
    AlertStatus,
)
from k8s_diag_agent.incident_alert_signal_normalizer import (
    infer_source_type,
    normalize_alertmanager_payload,
    normalize_alertmanager_payloads,
)
from tests.fixtures.alertmanager_payload_fixtures import (
    empty_labels_payload,
    grouped_firing_alerts_payload,
    invalid_alerts_field_payload,
    invalid_status_payload,
    large_labels_payload,
    large_value_payload,
    minimal_alert_payload,
    missing_alertname_payload,
    missing_alerts_field_payload,
    mixed_firing_resolved_group_payload,
    non_string_labels_payload,
    single_firing_alert_payload,
    single_resolved_alert_payload,
    special_characters_payload,
    vmalert_firing_payload,
    vmalert_resolved_payload,
)


class TestInferSourceType:
    """Tests for source type inference."""

    def test_default_to_alertmanager(self) -> None:
        labels = {"alertname": "Test", "severity": "warning"}
        assert infer_source_type(labels) == AlertSourceType.ALERTMANAGER

    def test_explicit_vmalert_label(self) -> None:
        labels = {
            "alertname": "Test",
            "k9b.dev/source_type": "vmalert",
        }
        assert infer_source_type(labels) == AlertSourceType.VMALERT

    def test_case_insensitive_vmalert(self) -> None:
        labels = {
            "alertname": "Test",
            "k9b.dev/source_type": "VMALERT",
        }
        assert infer_source_type(labels) == AlertSourceType.VMALERT

    def test_generic_source_type_not_vmalert(self) -> None:
        labels = {
            "alertname": "Test",
            "source_type": "prometheus",
        }
        # Generic source_type doesn't trigger vmalert detection
        assert infer_source_type(labels) == AlertSourceType.ALERTMANAGER


class TestNormalizeSingleFiringAlert:
    """Tests for single firing alert normalization."""

    def test_basic_normalization(self) -> None:
        payload = single_firing_alert_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="http://alertmanager:9093",
        )
        assert result.is_valid
        assert len(result.signals) == 1

        signal = result.signals[0]
        assert signal.status == AlertStatus.FIRING
        assert signal.alertname == "HighCPUUsage"
        assert signal.severity == "warning"
        assert signal.source_type == AlertSourceType.ALERTMANAGER
        assert signal.external_fingerprint == "abc123def456"
        assert signal.group_key is not None
        assert signal.receiver == "k9b-receiver"
        assert signal.generator_url == "http://prometheus/alerts/123"
        assert signal.starts_at is not None

    def test_preserves_labels(self) -> None:
        payload = single_firing_alert_payload(
            alertname="TestAlert",
            namespace="test-ns",
            severity="critical",
        )
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test-instance",
        )
        assert result.is_valid

        signal = result.signals[0]
        label_dict = dict(signal.labels)
        assert label_dict["alertname"] == "TestAlert"
        assert label_dict["namespace"] == "test-ns"
        assert label_dict["severity"] == "critical"

    def test_preserves_annotations(self) -> None:
        payload = single_firing_alert_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert result.is_valid

        signal = result.signals[0]
        ann_dict = dict(signal.annotations)
        assert "summary" in ann_dict
        assert "description" in ann_dict


class TestNormalizeResolvedAlert:
    """Tests for resolved alert normalization."""

    def test_resolved_status(self) -> None:
        payload = single_resolved_alert_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="http://alertmanager:9093",
        )
        assert result.is_valid
        assert len(result.signals) == 1

        signal = result.signals[0]
        assert signal.status == AlertStatus.RESOLVED
        assert signal.ends_at is not None

    def test_resolved_has_end_time(self) -> None:
        payload = single_resolved_alert_payload(
            starts_at="2024-01-15T10:00:00.000Z",
            ends_at="2024-01-15T10:30:00.000Z",
        )
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert result.is_valid

        signal = result.signals[0]
        assert signal.starts_at is not None
        assert signal.ends_at is not None


class TestNormalizeGroupedPayload:
    """Tests for grouped payload normalization."""

    def test_splits_into_multiple_signals(self) -> None:
        payload = grouped_firing_alerts_payload(
            pod_names=("pod-1", "pod-2", "pod-3"),
        )
        result = normalize_alertmanager_payload(
            payload,
            source_instance="http://alertmanager:9093",
        )
        assert result.is_valid
        assert len(result.signals) == 3

        # Each signal should have different pod label
        pod_labels = set()
        for signal in result.signals:
            label_dict = dict(signal.labels)
            if "pod" in label_dict:
                pod_labels.add(label_dict["pod"])

        assert pod_labels == {"pod-1", "pod-2", "pod-3"}

    def test_preserves_group_metadata(self) -> None:
        payload = grouped_firing_alerts_payload(
            alertname="GroupedAlert",
            namespace="grouped-ns",
        )
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test-instance",
        )
        assert result.is_valid

        # All signals should share group metadata
        for signal in result.signals:
            assert signal.group_key is not None
            assert signal.receiver == "k9b-receiver"
            assert signal.external_url is not None


class TestNormalizeMixedGroup:
    """Tests for mixed firing/resolved group normalization."""

    def test_handles_mixed_statuses(self) -> None:
        payload = mixed_firing_resolved_group_payload(
            firing_endpoints=("ep-1", "ep-2"),
            resolved_endpoint="ep-3",
        )
        result = normalize_alertmanager_payload(
            payload,
            source_instance="http://alertmanager:9093",
        )
        assert result.is_valid
        assert len(result.signals) == 3

        firing_signals = [s for s in result.signals if s.status == AlertStatus.FIRING]
        resolved_signals = [s for s in result.signals if s.status == AlertStatus.RESOLVED]

        assert len(firing_signals) == 2
        assert len(resolved_signals) == 1


class TestNormalizeVMAlert:
    """Tests for vmalert source type detection."""

    def test_vmalert_source_type(self) -> None:
        payload = vmalert_firing_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="http://vmalert:8880",
        )
        assert result.is_valid
        assert len(result.signals) == 1

        signal = result.signals[0]
        assert signal.source_type == AlertSourceType.VMALERT

    def test_vmalert_resolved(self) -> None:
        payload = vmalert_resolved_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="http://vmalert:8880",
        )
        assert result.is_valid

        signal = result.signals[0]
        assert signal.source_type == AlertSourceType.VMALERT
        assert signal.status == AlertStatus.RESOLVED


class TestNormalizeMissingFields:
    """Tests for missing/invalid field handling."""

    def test_missing_alerts_field(self) -> None:
        payload = missing_alerts_field_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert not result.is_valid
        assert len(result.errors) == 1
        assert "alerts" in result.errors[0].field

    def test_missing_alertname(self) -> None:
        payload = missing_alertname_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        # Normalization still produces a signal with fallback "unknown" alertname
        assert len(result.signals) == 1
        assert result.signals[0].alertname == "unknown"
        # But we have an error/warning
        assert len(result.errors) == 1
        assert "alertname" in result.errors[0].message
        # is_valid is False because of the warning
        assert not result.is_valid

    def test_minimal_payload(self) -> None:
        payload = minimal_alert_payload(alertname="MinimalAlert")
        result = normalize_alertmanager_payload(
            payload,
            source_instance="minimal-test",
        )
        assert result.is_valid
        assert len(result.signals) == 1
        assert result.signals[0].alertname == "MinimalAlert"

    def test_invalid_alerts_field_type(self) -> None:
        payload = invalid_alerts_field_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert not result.is_valid
        assert len(result.errors) == 1

    def test_invalid_status(self) -> None:
        payload = invalid_status_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        # Should still normalize with fallback to FIRING
        assert len(result.signals) == 1
        # But is_valid is False due to the error
        assert not result.is_valid
        # Should produce error about invalid status
        assert len(result.errors) == 1


class TestNormalizeBounds:
    """Tests for label/annotation bounds enforcement."""

    def test_large_labels_truncated(self) -> None:
        payload = large_labels_payload(label_count=150)
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert result.is_valid
        assert len(result.signals) == 1

        signal = result.signals[0]
        # Should have truncation metadata - the large values hit the bytes limit
        assert signal.truncation is not None
        # With 150 labels of large values, bytes limit (16KB) is hit
        assert signal.truncation.label_bytes_exceeded is True

    def test_large_value_truncated(self) -> None:
        payload = large_value_payload(value_length=10000)
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert result.is_valid

        signal = result.signals[0]
        assert signal.truncation is not None
        # Large annotation value should be truncated
        assert len(signal.truncation.annotation_value_truncated_keys) > 0


class TestNormalizeEdgeCases:
    """Tests for edge case handling."""

    def test_empty_labels(self) -> None:
        payload = empty_labels_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert result.is_valid
        assert len(result.signals) == 1
        # Empty string labels should be handled
        assert result.signals[0].alertname == "EmptyLabelsAlert"

    def test_special_characters(self) -> None:
        payload = special_characters_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert result.is_valid
        assert len(result.signals) == 1
        # Special characters should be preserved
        signal = result.signals[0]
        label_dict = dict(signal.labels)
        assert "special_key" in label_dict

    def test_non_string_labels(self) -> None:
        payload = non_string_labels_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        assert result.is_valid
        assert len(result.signals) == 1
        # Non-string values should be converted to strings
        label_dict = dict(result.signals[0].labels)
        assert label_dict["int_value"] == "123"
        assert label_dict["float_value"] == "45.67"
        assert label_dict["bool_value"] == "True"


class TestNormalizationResult:
    """Tests for NormalizationResult structure."""

    def test_is_valid_property(self) -> None:
        # Valid result
        payload = single_firing_alert_payload()
        result = normalize_alertmanager_payload(payload, source_instance="test")
        assert result.is_valid is True

        # Invalid result
        payload = missing_alerts_field_payload()
        result = normalize_alertmanager_payload(payload, source_instance="test")
        assert result.is_valid is False

    def test_to_dict(self) -> None:
        payload = single_firing_alert_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        d = result.to_dict()
        assert "signals" in d
        assert "errors" in d
        assert "is_valid" in d
        assert d["is_valid"] is True


class TestBatchNormalization:
    """Tests for batch normalization."""

    def test_multiple_payloads(self) -> None:
        payloads = [
            single_firing_alert_payload(alertname="Alert1"),
            single_firing_alert_payload(alertname="Alert2"),
            missing_alerts_field_payload(),
        ]
        results = normalize_alertmanager_payloads(
            payloads,
            source_instance="test",
        )
        assert len(results) == 3
        assert results[0].is_valid
        assert results[1].is_valid
        assert not results[2].is_valid

    def test_non_mapping_payload(self) -> None:
        # Test with payloads that are technically valid dicts but missing required fields
        payloads: list[dict[str, object]] = [
            {},  # Empty but valid dict - has no alerts field
        ]
        results = normalize_alertmanager_payloads(
            payloads,
            source_instance="test",
        )
        assert len(results) == 1
        # Empty payload has no alerts field, so it's not valid
        assert not results[0].is_valid


class TestReceivedAt:
    """Tests for received_at parameter."""

    def test_custom_received_at(self) -> None:
        custom_time = datetime(2024, 6, 15, 12, 30, 0, tzinfo=UTC)
        payload = single_firing_alert_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
            received_at=custom_time,
        )
        assert result.is_valid
        assert result.signals[0].received_at == custom_time

    def test_default_received_at(self) -> None:
        before = datetime.now(UTC)
        payload = single_firing_alert_payload()
        result = normalize_alertmanager_payload(
            payload,
            source_instance="test",
        )
        after = datetime.now(UTC)

        assert result.is_valid
        signal_time = result.signals[0].received_at
        assert before <= signal_time <= after
