"""Tests for alert labels, annotations, status, and temporal fields preservation.

Part of ACT-K9B-ALERTMANAGER-SNAPSHOT-SPLIT01 split.
Tests alert field extraction from normalize_alertmanager_payload.
"""

from __future__ import annotations

from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    normalize_alertmanager_payload,
)


class TestNormalizedAlertExtendedFields:
    """Tests for NormalizedAlert extended fields."""

    def test_normalized_alert_has_annotations_field(self) -> None:
        """NormalizedAlert supports annotations field."""
        from tests.unit.alertmanager_snapshot_evidence_preservation_support import (
            make_normalized_alert,
        )
        annotations = (("summary", "Test alert"), ("runbook_url", "http://runbook"))
        alert = make_normalized_alert(annotations=annotations)
        assert alert.annotations == annotations

    def test_normalized_alert_has_generator_url_field(self) -> None:
        """NormalizedAlert supports generator_url field."""
        from tests.unit.alertmanager_snapshot_evidence_preservation_support import (
            make_normalized_alert,
        )
        url = "http://prometheus/alert?query=up"
        alert = make_normalized_alert(generator_url=url)
        assert alert.generator_url == url

    def test_normalized_alert_has_ends_at_field(self) -> None:
        """NormalizedAlert supports ends_at field."""
        from tests.unit.alertmanager_snapshot_evidence_preservation_support import (
            make_normalized_alert,
        )
        ends = "2024-01-15T12:00:00Z"
        alert = make_normalized_alert(ends_at=ends)
        assert alert.ends_at == ends

    def test_normalized_alert_has_updated_at_field(self) -> None:
        """NormalizedAlert supports updated_at field."""
        from tests.unit.alertmanager_snapshot_evidence_preservation_support import (
            make_normalized_alert,
        )
        updated = "2024-01-15T11:30:00Z"
        alert = make_normalized_alert(updated_at=updated)
        assert alert.updated_at == updated

    def test_normalized_alert_has_receiver_field(self) -> None:
        """NormalizedAlert supports receiver field."""
        from tests.unit.alertmanager_snapshot_evidence_preservation_support import (
            make_normalized_alert,
        )
        recv = "team-notifications"
        alert = make_normalized_alert(receiver=recv)
        assert alert.receiver == recv

    def test_normalized_alert_serialization_roundtrip(self) -> None:
        """NormalizedAlert with extended fields serializes and deserializes correctly."""
        from tests.unit.alertmanager_snapshot_evidence_preservation_support import (
            make_normalized_alert,
        )
        alert = make_normalized_alert(
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
