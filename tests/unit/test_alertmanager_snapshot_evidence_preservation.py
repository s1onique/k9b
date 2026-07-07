"""Unit tests for ACT-K9B-ALERTMANAGER-ALERT-INGESTION01R1: Alert evidence preservation.

Tests that NormalizedAlert preserves richer evidence including:
- annotations (full annotation key-value pairs)
- generator_url
- ends_at
- updated_at
- receiver
"""

from datetime import UTC, datetime

from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    NormalizedAlert,
    _extract_receiver,
    _is_sensitive_key,
    normalize_alertmanager_payload,
)
from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
    adapt_snapshot_to_alert_signals,
)


def _make_normalized_alert(
    fingerprint="fp123",
    alertname="TestAlert",
    state="active",
    severity="warning",
    namespace="default",
    labels=None,
    summary=None,
    annotations=None,
    generator_url=None,
    ends_at=None,
    updated_at=None,
    receiver=None,
):
    """Helper to create test normalized alerts with ACT-R1 fields."""
    if labels is None:
        labels = [
            ("alertname", alertname),
            ("severity", severity),
        ]
        if namespace:
            labels.append(("namespace", namespace))
    if annotations is None:
        annotations = ()
    return NormalizedAlert(
        fingerprint=fingerprint,
        alertname=alertname,
        state=state,
        severity=severity,
        namespace=namespace,
        labels=tuple(labels),
        summary=summary,
        annotations=annotations,
        generator_url=generator_url,
        ends_at=ends_at,
        updated_at=updated_at,
        receiver=receiver,
    )


def _make_snapshot(alerts=None, status=AlertmanagerStatus.OK):
    """Helper to create test snapshots."""
    if alerts is None:
        alerts = []
    return AlertmanagerSnapshot(
        status=status,
        captured_at=datetime.now(UTC).isoformat(),
        source="http://alertmanager:9093",
        alert_count=len(alerts),
        alerts=tuple(alerts),
        errors=(),
        truncated=False,
        artifact_id="test-snapshot-id",
    )


class TestNormalizedAlertExtendedFields:
    """Tests for NormalizedAlert extended fields."""

    def test_normalized_alert_has_annotations_field(self) -> None:
        """NormalizedAlert supports annotations field."""
        annotations = (("summary", "Test alert"), ("runbook_url", "http://runbook"))
        alert = _make_normalized_alert(annotations=annotations)
        assert alert.annotations == annotations

    def test_normalized_alert_has_generator_url_field(self) -> None:
        """NormalizedAlert supports generator_url field."""
        url = "http://prometheus/alert?query=up"
        alert = _make_normalized_alert(generator_url=url)
        assert alert.generator_url == url

    def test_normalized_alert_has_ends_at_field(self) -> None:
        """NormalizedAlert supports ends_at field."""
        ends = "2024-01-15T12:00:00Z"
        alert = _make_normalized_alert(ends_at=ends)
        assert alert.ends_at == ends

    def test_normalized_alert_has_updated_at_field(self) -> None:
        """NormalizedAlert supports updated_at field."""
        updated = "2024-01-15T11:30:00Z"
        alert = _make_normalized_alert(updated_at=updated)
        assert alert.updated_at == updated

    def test_normalized_alert_has_receiver_field(self) -> None:
        """NormalizedAlert supports receiver field."""
        recv = "team-notifications"
        alert = _make_normalized_alert(receiver=recv)
        assert alert.receiver == recv

    def test_normalized_alert_serialization_roundtrip(self) -> None:
        """NormalizedAlert with extended fields serializes and deserializes correctly."""
        alert = _make_normalized_alert(
            annotations=(("summary", "Test"), ("description", "Details")),
            generator_url="http://prometheus/alert",
            ends_at="2024-01-15T12:00:00Z",
            updated_at="2024-01-15T11:00:00Z",
            receiver="team-pagerduty",
        )
        data = alert.to_dict()
        
        # Verify serialization includes extended fields
        assert "annotations" in data
        assert data["annotations"]["summary"] == "Test"
        assert data["annotations"]["description"] == "Details"
        assert data["generator_url"] == "http://prometheus/alert"
        assert data["ends_at"] == "2024-01-15T12:00:00Z"
        assert data["updated_at"] == "2024-01-15T11:00:00Z"
        assert data["receiver"] == "team-pagerduty"


class TestNormalizeAlertmanagerPayloadPreservesEvidence:
    """Tests for normalize_alertmanager_payload preserving evidence."""

    def test_preserves_full_annotations(self) -> None:
        """normalize_alertmanager_payload preserves full annotations."""
        raw = [
            {
                "labels": {"alertname": "TestAlert", "severity": "warning"},
                "annotations": {
                    "summary": "Test alert",
                    "description": "Detailed description",
                    "runbook_url": "http://runbook",
                },
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        alert = snapshot.alerts[0]
        # Check annotations are preserved
        ann_dict = dict(alert.annotations)
        assert "summary" in ann_dict
        assert ann_dict["summary"] == "Test alert"
        assert ann_dict["description"] == "Detailed description"
        assert ann_dict["runbook_url"] == "http://runbook"

    def test_preserves_generator_url(self) -> None:
        """normalize_alertmanager_payload preserves generatorURL."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "generatorURL": "http://prometheus/graph?query=up",
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].generator_url == "http://prometheus/graph?query=up"

    def test_preserves_ends_at(self) -> None:
        """normalize_alertmanager_payload preserves endsAt."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "endsAt": "2024-01-15T12:00:00Z",
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].ends_at == "2024-01-15T12:00:00Z"

    def test_preserves_updated_at(self) -> None:
        """normalize_alertmanager_payload preserves updatedAt."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "updatedAt": "2024-01-15T11:30:00Z",
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].updated_at == "2024-01-15T11:30:00Z"

    def test_preserves_receiver(self) -> None:
        """normalize_alertmanager_payload preserves receiver."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "receiver": "team-notifications",
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].receiver == "team-notifications"

    def test_handles_missing_annotations(self) -> None:
        """normalize_alertmanager_payload handles missing annotations gracefully."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].annotations == ()

    def test_handles_missing_generator_url(self) -> None:
        """normalize_alertmanager_payload handles missing generatorURL gracefully."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].generator_url is None

    def test_handles_missing_ends_at(self) -> None:
        """normalize_alertmanager_payload handles missing endsAt gracefully."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].ends_at is None

    def test_redacts_sensitive_annotation_keys(self) -> None:
        """Sensitive annotation keys are redacted."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "annotations": {
                    "summary": "Safe annotation",
                    "password": "secret123",
                    "api_key": "key123",
                },
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        ann_dict = dict(snapshot.alerts[0].annotations)
        assert ann_dict["summary"] == "Safe annotation"
        assert ann_dict["password"] == "[REDACTED]"
        assert ann_dict["api_key"] == "[REDACTED]"

    def test_deterministic_annotation_ordering(self) -> None:
        """Annotations are sorted for deterministic ordering."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "annotations": {
                    "zebra": "z",
                    "alpha": "a",
                    "middle": "m",
                },
            }
        ]
        snapshot1 = normalize_alertmanager_payload(raw)
        snapshot2 = normalize_alertmanager_payload(raw)
        
        # Same input should produce same annotation order
        assert snapshot1.alerts[0].annotations == snapshot2.alerts[0].annotations
        # Should be sorted alphabetically
        keys = [k for k, v in snapshot1.alerts[0].annotations]
        assert keys == sorted(keys)


class TestIsSensitiveKey:
    """Tests for _is_sensitive_key function."""

    def test_detects_password_pattern(self) -> None:
        """Password in key is detected as sensitive."""
        assert _is_sensitive_key("password") is True
        assert _is_sensitive_key("user_password") is True
        assert _is_sensitive_key("dbPassword") is True

    def test_detects_secret_pattern(self) -> None:
        """Secret in key is detected as sensitive."""
        assert _is_sensitive_key("secret") is True
        assert _is_sensitive_key("api_secret") is True

    def test_detects_token_pattern(self) -> None:
        """Token in key is detected as sensitive."""
        assert _is_sensitive_key("token") is True
        assert _is_sensitive_key("bearer_token") is True

    def test_detects_auth_pattern(self) -> None:
        """Auth in key is detected as sensitive."""
        assert _is_sensitive_key("auth") is True
        assert _is_sensitive_key("basic_auth") is True

    def test_detects_credential_pattern(self) -> None:
        """Credential in key is detected as sensitive."""
        assert _is_sensitive_key("credential") is True
        assert _is_sensitive_key("credentials") is True

    def test_detects_private_key_pattern(self) -> None:
        """Private in key is detected as sensitive."""
        assert _is_sensitive_key("private") is True
        assert _is_sensitive_key("private_key") is True

    def test_detects_api_key_patterns(self) -> None:
        """API key patterns are detected as sensitive."""
        assert _is_sensitive_key("api_key") is True
        assert _is_sensitive_key("apikey") is True
        assert _is_sensitive_key("apiKey") is True

    def test_safe_keys_pass(self) -> None:
        """Safe keys are not flagged as sensitive."""
        assert _is_sensitive_key("summary") is False
        assert _is_sensitive_key("description") is False
        assert _is_sensitive_key("runbook_url") is False
        assert _is_sensitive_key("dashboard_url") is False


class TestExtractReceiver:
    """Tests for _extract_receiver function (R2 fix)."""

    def test_scalar_receiver(self) -> None:
        """Scalar receiver field is extracted correctly."""
        alert = {"receiver": "team-notifications"}
        assert _extract_receiver(alert) == "team-notifications"

    def test_receivers_array_with_strings(self) -> None:
        """Receivers array with strings extracts first receiver."""
        alert = {"receivers": ["team-a", "team-b"]}
        assert _extract_receiver(alert) == "team-a"

    def test_receivers_array_with_dicts(self) -> None:
        """Receivers array with dicts extracts first receiver name."""
        alert = {"receivers": [{"name": "team-a"}, {"name": "team-b"}]}
        assert _extract_receiver(alert) == "team-a"

    def test_receivers_array_with_mixed(self) -> None:
        """Receivers array with mixed types extracts first valid receiver."""
        alert = {"receivers": [{"name": "team-a"}, "team-b"]}
        assert _extract_receiver(alert) == "team-a"

    def test_receivers_dict_with_empty_name(self) -> None:
        """Receivers dict with empty name returns None."""
        alert = {"receivers": [{"name": ""}, {"name": "team-b"}]}
        assert _extract_receiver(alert) is None

    def test_scalar_takes_precedence(self) -> None:
        """Scalar receiver takes precedence over receivers array."""
        alert = {"receiver": "team-a", "receivers": [{"name": "team-b"}]}
        assert _extract_receiver(alert) == "team-a"

    def test_no_receiver(self) -> None:
        """No receiver field returns None."""
        alert = {"labels": {"alertname": "TestAlert"}}
        assert _extract_receiver(alert) is None

    def test_empty_receivers_array(self) -> None:
        """Empty receivers array returns None."""
        alert: dict[str, list[object]] = {"receivers": []}
        assert _extract_receiver(alert) is None

    def test_receivers_with_api_v2_format(self) -> None:
        """Receivers extracted correctly from /api/v2/alerts format."""
        # Real Alertmanager API v2 format
        alert = {
            "receivers": [
                {"name": "team-pagerduty"},
                {"name": "team-slack"}
            ]
        }
        assert _extract_receiver(alert) == "team-pagerduty"

    def test_webhook_format_still_works(self) -> None:
        """Legacy webhook payload format still works."""
        # Webhook payloads have scalar receiver
        alert = {
            "receiver": "team-notifications",
            "alerts": []
        }
        assert _extract_receiver(alert) == "team-notifications"


class TestNormalizeAlertmanagerPayloadWithReceivers:
    """Tests for receiver handling in normalize_alertmanager_payload."""

    def test_receivers_from_api_v2(self) -> None:
        """normalize_alertmanager_payload handles /api/v2/alerts receivers format."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "receivers": [{"name": "team-a"}, {"name": "team-b"}],
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].receiver == "team-a"

    def test_receiver_from_webhook_format(self) -> None:
        """normalize_alertmanager_payload handles webhook receiver format."""
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "receiver": "team-notifications",
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].receiver == "team-notifications"


class TestSnapshotAdapterPreservesEvidence:
    """Tests for snapshot adapter preserving evidence in AlertSignal."""

    def test_generator_url_maps_to_signal(self) -> None:
        """generatorURL from NormalizedAlert maps to AlertSignal.generator_url."""
        alert = _make_normalized_alert(
            generator_url="http://prometheus/alert"
        )
        snapshot = _make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        assert signals[0].generator_url == "http://prometheus/alert"

    def test_full_annotations_map_to_signal(self) -> None:
        """Full annotations from NormalizedAlert map to AlertSignal.annotations."""
        annotations = (
            ("summary", "Test alert"),
            ("description", "Detailed description"),
            ("runbook_url", "http://runbook"),
        )
        alert = _make_normalized_alert(annotations=annotations)
        snapshot = _make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        ann_dict = dict(signals[0].annotations)
        assert ann_dict["summary"] == "Test alert"
        assert ann_dict["description"] == "Detailed description"
        assert ann_dict["runbook_url"] == "http://runbook"

    def test_summary_not_duplicated(self) -> None:
        """Summary is not duplicated when present in annotations."""
        annotations = (
            ("summary", "Test summary"),
            ("other", "value"),
        )
        alert = _make_normalized_alert(
            summary="Test summary",
            annotations=annotations,
        )
        snapshot = _make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        # Should have full annotations, not just summary
        ann_dict = dict(signals[0].annotations)
        assert ann_dict["summary"] == "Test summary"
        assert ann_dict["other"] == "value"
        # Should not have duplicate summary
        count = sum(1 for k, v in signals[0].annotations if k == "summary")
        assert count == 1

    def test_ends_at_maps_to_signal(self) -> None:
        """endsAt from NormalizedAlert maps to AlertSignal.ends_at."""
        alert = _make_normalized_alert(ends_at="2024-01-15T12:00:00Z")
        snapshot = _make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        assert signals[0].ends_at is not None
        assert signals[0].ends_at.year == 2024

    def test_receiver_maps_to_signal(self) -> None:
        """receiver from NormalizedAlert maps to AlertSignal.receiver."""
        alert = _make_normalized_alert(receiver="team-notifications")
        snapshot = _make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        assert signals[0].receiver == "team-notifications"

    def test_missing_fingerprint_passes_through(self) -> None:
        """Empty fingerprint passes through without error."""
        # Note: Deterministic fingerprint generation happens in normalize_alertmanager_payload,
        # not in the adapter. The adapter just preserves whatever fingerprint is set.
        alert = _make_normalized_alert(fingerprint="")
        snapshot = _make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        # Empty fingerprint becomes None when passed through adapter
        # (normalize_alertmanager_payload would generate a deterministic one)
        assert signals[0].external_fingerprint is None

    def test_legacy_summary_only_alert_still_works(self) -> None:
        """Legacy summary-only alert still works (backward compat)."""
        # Create alert without extended fields (as in legacy snapshots)
        alert = NormalizedAlert(
            fingerprint="fp123",
            alertname="LegacyAlert",
            state="active",
            severity="warning",
            namespace="default",
            labels=(("alertname", "LegacyAlert"),),
            # No annotations, generator_url, etc.
        )
        snapshot = _make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        assert signals[0].alertname == "LegacyAlert"
        assert signals[0].generator_url is None
        assert signals[0].annotations == ()


class TestBackwardCompatibility:
    """Tests for backward compatibility with legacy artifacts."""

    def test_legacy_snapshot_without_extended_fields_loads(self) -> None:
        """Legacy snapshot without extended fields loads without errors."""
        # Simulate legacy snapshot format (before ACT-R1)
        legacy_data = {
            "status": "ok",
            "captured_at": "2024-01-15T10:00:00Z",
            "source": "http://alertmanager:9093",
            "alert_count": 1,
            "alerts": [
                {
                    "fingerprint": "fp123",
                    "alertname": "LegacyAlert",
                    "state": "active",
                    "severity": "warning",
                    "labels": {"alertname": "LegacyAlert", "severity": "warning"},
                    # No annotations, generator_url, etc.
                }
            ],
            "errors": [],
            "truncated": False,
        }
        
        snapshot = AlertmanagerSnapshot.from_dict(legacy_data)
        
        assert snapshot.status == AlertmanagerStatus.OK
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].alertname == "LegacyAlert"
        # Extended fields should default to empty/None
        assert snapshot.alerts[0].annotations == ()
        assert snapshot.alerts[0].generator_url is None
        assert snapshot.alerts[0].ends_at is None
        assert snapshot.alerts[0].receiver is None

    def test_roundtrip_preserves_legacy_format(self) -> None:
        """Roundtrip serialization preserves legacy format for old artifacts."""
        legacy_data = {
            "status": "ok",
            "captured_at": "2024-01-15T10:00:00Z",
            "source": "http://alertmanager:9093",
            "alert_count": 1,
            "alerts": [
                {
                    "fingerprint": "fp123",
                    "alertname": "LegacyAlert",
                    "state": "active",
                    "severity": "warning",
                    "labels": {"alertname": "LegacyAlert"},
                }
            ],
            "errors": [],
            "truncated": False,
        }
        
        snapshot = AlertmanagerSnapshot.from_dict(legacy_data)
        serialized = snapshot.to_dict()
        
        # Should not crash and should have valid data
        assert serialized["status"] == "ok"
        assert serialized["alerts"][0]["alertname"] == "LegacyAlert"
