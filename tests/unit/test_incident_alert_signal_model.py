"""Unit tests for AlertSignal domain model.

Tests cover:
- AlertSignal creation and serialization
- AlertStatus and AlertSourceType enums
- TruncationMetadata
- AlertCorrelationHints
- bound_labels and bound_annotations utilities
"""

from __future__ import annotations

from k8s_diag_agent.incident_alert_signal import (
    MAX_ANNOTATION_COUNT,
    MAX_KEY_LENGTH,
    MAX_LABEL_COUNT,
    MAX_VALUE_LENGTH,
    AlertCorrelationHints,
    AlertSignal,
    AlertSourceType,
    AlertStatus,
    TruncationMetadata,
    bound_annotations,
    bound_labels,
)


class TestAlertSourceType:
    """Tests for AlertSourceType enum."""

    def test_alertmanager_value(self) -> None:
        assert AlertSourceType.ALERTMANAGER.value == "alertmanager"

    def test_vmalert_value(self) -> None:
        assert AlertSourceType.VMALERT.value == "vmalert"

    def test_from_string(self) -> None:
        assert AlertSourceType("alertmanager") == AlertSourceType.ALERTMANAGER
        assert AlertSourceType("vmalert") == AlertSourceType.VMALERT


class TestAlertStatus:
    """Tests for AlertStatus enum."""

    def test_firing_value(self) -> None:
        assert AlertStatus.FIRING.value == "firing"

    def test_resolved_value(self) -> None:
        assert AlertStatus.RESOLVED.value == "resolved"

    def test_from_string(self) -> None:
        assert AlertStatus("firing") == AlertStatus.FIRING
        assert AlertStatus("resolved") == AlertStatus.RESOLVED


class TestTruncationMetadata:
    """Tests for TruncationMetadata."""

    def test_empty_truncation(self) -> None:
        tm = TruncationMetadata()
        assert tm.truncated_labels == 0
        assert tm.truncated_annotations == 0
        assert tm.label_value_truncated_keys == ()
        assert tm.annotation_value_truncated_keys == ()
        assert tm.label_bytes_exceeded is False
        assert tm.annotation_bytes_exceeded is False

    def test_with_truncation(self) -> None:
        tm = TruncationMetadata(
            truncated_labels=5,
            truncated_annotations=2,
            label_value_truncated_keys=("key1", "key2"),
            annotation_value_truncated_keys=("ann1",),
            label_bytes_exceeded=True,
            annotation_bytes_exceeded=False,
        )
        assert tm.truncated_labels == 5
        assert tm.truncated_annotations == 2
        assert tm.label_value_truncated_keys == ("key1", "key2")
        assert tm.annotation_value_truncated_keys == ("ann1",)
        assert tm.label_bytes_exceeded is True
        assert tm.annotation_bytes_exceeded is False

    def test_to_dict(self) -> None:
        tm = TruncationMetadata(
            truncated_labels=3,
            label_value_truncated_keys=("truncated_key",),
        )
        d = tm.to_dict()
        assert d["truncated_labels"] == 3
        assert d["label_value_truncated_keys"] == ["truncated_key"]


class TestAlertSignal:
    """Tests for AlertSignal model."""

    def test_basic_creation(self) -> None:
        signal = AlertSignal(
            signal_id="sig-123",
            source_type=AlertSourceType.ALERTMANAGER,
            source_instance="http://alertmanager:9093",
            status=AlertStatus.FIRING,
            alertname="HighCPU",
        )
        assert signal.signal_id == "sig-123"
        assert signal.source_type == AlertSourceType.ALERTMANAGER
        assert signal.status == AlertStatus.FIRING
        assert signal.alertname == "HighCPU"
        assert signal.received_at is not None

    def test_with_labels_and_annotations(self) -> None:
        labels = (
            ("alertname", "HighCPU"),
            ("severity", "warning"),
            ("namespace", "prod"),
        )
        annotations = (
            ("summary", "CPU is high"),
            ("description", "CPU above 90%"),
        )
        signal = AlertSignal(
            signal_id="sig-456",
            source_type=AlertSourceType.VMALERT,
            source_instance="vmalert-prod",
            status=AlertStatus.RESOLVED,
            alertname="HighCPU",
            severity="warning",
            labels=labels,
            annotations=annotations,
        )
        assert signal.labels == labels
        assert signal.annotations == annotations
        assert signal.severity == "warning"

    def test_to_dict(self) -> None:
        signal = AlertSignal(
            signal_id="sig-789",
            source_type=AlertSourceType.ALERTMANAGER,
            source_instance="http://alertmanager:9093",
            status=AlertStatus.FIRING,
            alertname="TestAlert",
            external_fingerprint="fp-abc",
            group_key="{namespace=prod}",
            receiver="k9b-receiver",
            severity="critical",
        )
        d = signal.to_dict()
        assert d["signal_id"] == "sig-789"
        assert d["source_type"] == "alertmanager"
        assert d["status"] == "firing"
        assert d["alertname"] == "TestAlert"
        assert d["external_fingerprint"] == "fp-abc"
        assert d["group_key"] == "{namespace=prod}"
        assert d["receiver"] == "k9b-receiver"

    def test_to_dict_with_truncation(self) -> None:
        signal = AlertSignal(
            signal_id="sig-trunc",
            source_type=AlertSourceType.ALERTMANAGER,
            source_instance="test",
            status=AlertStatus.FIRING,
            alertname="Test",
            truncation=TruncationMetadata(
                truncated_labels=2,
                label_bytes_exceeded=True,
            ),
        )
        d = signal.to_dict()
        assert d["truncation"]["truncated_labels"] == 2
        assert d["truncation"]["label_bytes_exceeded"] is True

    def test_from_dict(self) -> None:
        data = {
            "signal_id": "sig-from-dict",
            "source_type": "vmalert",
            "source_instance": "vmalert.local",
            "status": "resolved",
            "alertname": "FromDict",
            "severity": "warning",
            "external_fingerprint": "fp-dict",
            "group_key": None,
            "receiver": "receiver-1",
            "labels": {"alertname": "FromDict", "severity": "warning"},
            "annotations": {"summary": "Test"},
            "starts_at": "2024-01-15T10:00:00+00:00",
            "ends_at": "2024-01-15T10:30:00+00:00",
            "received_at": "2024-01-15T10:35:00+00:00",
            "generator_url": "http://prometheus/rule/123",
            "external_url": "http://alertmanager:9093",
        }
        signal = AlertSignal.from_dict(data)
        assert signal.signal_id == "sig-from-dict"
        assert signal.source_type == AlertSourceType.VMALERT
        assert signal.status == AlertStatus.RESOLVED
        assert signal.alertname == "FromDict"
        assert signal.severity == "warning"
        assert signal.starts_at is not None
        assert signal.ends_at is not None

    def test_from_dict_minimal(self) -> None:
        data = {
            "signal_id": "sig-minimal",
            "source_instance": "test",
            "alertname": "Minimal",
        }
        signal = AlertSignal.from_dict(data)
        assert signal.signal_id == "sig-minimal"
        assert signal.source_type == AlertSourceType.ALERTMANAGER
        assert signal.status == AlertStatus.FIRING
        assert signal.alertname == "Minimal"


class TestAlertCorrelationHints:
    """Tests for AlertCorrelationHints."""

    def test_creation(self) -> None:
        hints = AlertCorrelationHints(
            source_instance="http://alertmanager:9093",
            alertname="HighCPU",
            severity="warning",
            stable_labels=(("namespace", "prod"), ("severity", "warning")),
        )
        assert hints.source_instance == "http://alertmanager:9093"
        assert hints.alertname == "HighCPU"
        assert hints.severity == "warning"
        assert len(hints.stable_labels) == 2

    def test_to_dict(self) -> None:
        hints = AlertCorrelationHints(
            source_instance="test",
            alertname="TestAlert",
            external_fingerprint="fp-123",
        )
        d = hints.to_dict()
        assert d["source_instance"] == "test"
        assert d["alertname"] == "TestAlert"
        assert d["external_fingerprint"] == "fp-123"


class TestBoundLabels:
    """Tests for bound_labels utility."""

    def test_empty_labels(self) -> None:
        bounded, metadata = bound_labels({})
        assert bounded == ()
        assert metadata.truncated_labels == 0

    def test_normal_labels(self) -> None:
        labels = {
            "alertname": "TestAlert",
            "severity": "warning",
            "namespace": "prod",
        }
        bounded, metadata = bound_labels(labels)
        assert len(bounded) == 3
        assert metadata.truncated_labels == 0
        assert metadata.label_bytes_exceeded is False

    def test_key_truncation(self) -> None:
        long_key = "x" * (MAX_KEY_LENGTH + 50)
        labels = {
            long_key: "value",
            "alertname": "Test",
        }
        bounded, metadata = bound_labels(labels)
        # Long key should be truncated
        keys = [k for k, v in bounded]
        assert any(k.startswith("x") and k.endswith("...") for k in keys)

    def test_value_truncation(self) -> None:
        long_value = "x" * (MAX_VALUE_LENGTH + 50)
        labels = {
            "alertname": "Test",
            "description": long_value,
        }
        bounded, metadata = bound_labels(labels)
        # Description should be truncated
        desc_value = next((v for k, v in bounded if k == "description"), None)
        assert desc_value is not None
        assert desc_value.endswith("...")
        assert metadata.label_value_truncated_keys == ("description",)

    def test_max_count(self) -> None:
        labels = {f"label_{i}": f"value_{i}" for i in range(MAX_LABEL_COUNT + 50)}
        labels["alertname"] = "Test"
        bounded, metadata = bound_labels(labels)
        assert len(bounded) == MAX_LABEL_COUNT
        assert metadata.truncated_labels > 0

    def test_non_string_values(self) -> None:
        labels = {
            "alertname": "Test",
            "int_value": 123,
            "float_value": 45.67,
            "bool_value": True,
        }
        bounded, metadata = bound_labels(labels)
        assert len(bounded) == 4
        # Values should be converted to strings
        int_val = next(v for k, v in bounded if k == "int_value")
        assert int_val == "123"

    def test_empty_keys_skipped(self) -> None:
        labels = {
            "": "empty_key_value",
            "alertname": "Test",
        }
        bounded, metadata = bound_labels(labels)
        keys = [k for k, v in bounded]
        assert "" not in keys
        assert "alertname" in keys


class TestBoundAnnotations:
    """Tests for bound_annotations utility."""

    def test_empty_annotations(self) -> None:
        bounded, metadata = bound_annotations({})
        assert bounded == ()
        assert metadata.truncated_annotations == 0

    def test_normal_annotations(self) -> None:
        annotations = {
            "summary": "Test summary",
            "description": "Test description",
        }
        bounded, metadata = bound_annotations(annotations)
        assert len(bounded) == 2
        assert metadata.truncated_annotations == 0

    def test_max_count(self) -> None:
        annotations = {f"annotation_{i}": f"value_{i}" for i in range(MAX_ANNOTATION_COUNT + 20)}
        annotations["summary"] = "Required"
        bounded, metadata = bound_annotations(annotations)
        assert len(bounded) == MAX_ANNOTATION_COUNT
        assert metadata.truncated_annotations > 0

    def test_value_truncation(self) -> None:
        long_value = "x" * (MAX_VALUE_LENGTH + 100)
        annotations = {
            "summary": "Test",
            "description": long_value,
        }
        bounded, metadata = bound_annotations(annotations)
        desc_value = next((v for k, v in bounded if k == "description"), None)
        assert desc_value is not None
        assert desc_value.endswith("...")
        assert metadata.annotation_value_truncated_keys == ("description",)
