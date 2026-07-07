"""Tests for snapshot adapter preserving evidence in AlertSignal.

Part of ACT-K9B-ALERTMANAGER-SNAPSHOT-SPLIT01 split.
Tests integration between AlertmanagerSnapshot and AlertSignal.
"""

from __future__ import annotations

from tests.unit.alertmanager_snapshot_evidence_preservation_support import (
    make_normalized_alert,
    make_snapshot,
)


class TestSnapshotAdapterPreservesEvidence:
    """Tests for snapshot adapter preserving evidence in AlertSignal."""

    def test_generator_url_maps_to_signal(self) -> None:
        """generatorURL from NormalizedAlert maps to AlertSignal.generator_url."""
        from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
            adapt_snapshot_to_alert_signals,
        )
        alert = make_normalized_alert(
            generator_url="http://prometheus/alert"
        )
        snapshot = make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        assert signals[0].generator_url == "http://prometheus/alert"

    def test_full_annotations_map_to_signal(self) -> None:
        """Full annotations from NormalizedAlert map to AlertSignal.annotations."""
        from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
            adapt_snapshot_to_alert_signals,
        )
        annotations = (
            ("summary", "Test alert"),
            ("description", "Detailed description"),
            ("runbook_url", "http://runbook"),
        )
        alert = make_normalized_alert(annotations=annotations)
        snapshot = make_snapshot(alerts=[alert])
        
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
        from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
            adapt_snapshot_to_alert_signals,
        )
        annotations = (
            ("summary", "Test summary"),
            ("other", "value"),
        )
        alert = make_normalized_alert(
            summary="Test summary",
            annotations=annotations,
        )
        snapshot = make_snapshot(alerts=[alert])
        
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
        from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
            adapt_snapshot_to_alert_signals,
        )
        alert = make_normalized_alert(ends_at="2024-01-15T12:00:00Z")
        snapshot = make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        assert signals[0].ends_at is not None
        assert signals[0].ends_at.year == 2024

    def test_receiver_maps_to_signal(self) -> None:
        """receiver from NormalizedAlert maps to AlertSignal.receiver."""
        from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
            adapt_snapshot_to_alert_signals,
        )
        alert = make_normalized_alert(receiver="team-notifications")
        snapshot = make_snapshot(alerts=[alert])
        
        signals, _ = adapt_snapshot_to_alert_signals(
            snapshot=snapshot,
            source_instance="monitoring/alertmanager",
        )
        
        assert len(signals) == 1
        assert signals[0].receiver == "team-notifications"

    def test_missing_fingerprint_passes_through(self) -> None:
        """Empty fingerprint passes through without error."""
        from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
            adapt_snapshot_to_alert_signals,
        )
        # Note: Deterministic fingerprint generation happens in normalize_alertmanager_payload,
        # not in the adapter. The adapter just preserves whatever fingerprint is set.
        alert = make_normalized_alert(fingerprint="")
        snapshot = make_snapshot(alerts=[alert])
        
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
        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            NormalizedAlert,
        )
        from k8s_diag_agent.incident_alert_signal_snapshot_adapter import (
            adapt_snapshot_to_alert_signals,
        )
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
        snapshot = make_snapshot(alerts=[alert])
        
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
        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            AlertmanagerSnapshot,
            AlertmanagerStatus,
        )
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
        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            AlertmanagerSnapshot,
        )
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
