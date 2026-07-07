"""Tests for silence ID, matcher, and temporal window preservation.

Part of ACT-K9B-ALERTMANAGER-SNAPSHOT-SPLIT01 split.
Note: Current NormalizedAlert doesn't directly store silence data,
but receiver extraction tests are included for completeness.
"""

from __future__ import annotations

from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    _extract_receiver,
)


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
        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            normalize_alertmanager_payload,
        )
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
        from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
            normalize_alertmanager_payload,
        )
        raw = [
            {
                "labels": {"alertname": "TestAlert"},
                "receiver": "team-notifications",
            }
        ]
        snapshot = normalize_alertmanager_payload(raw)
        
        assert len(snapshot.alerts) == 1
        assert snapshot.alerts[0].receiver == "team-notifications"
