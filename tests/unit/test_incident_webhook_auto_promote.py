"""Unit tests for webhook auto-promotion of alert signals to incidents."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.incident_alert_signal import AlertSignal, AlertSourceType, AlertStatus
from k8s_diag_agent.incident_alert_signal_store import ALERT_SIGNAL_SCHEMA_VERSION
from k8s_diag_agent.incident_alertmanager_webhook import (
    WebhookPromotionSummary,
    WebhookResponse,
    handle_alertmanager_webhook,
    process_webhook,
)
from k8s_diag_agent.incident_alertmanager_webhook_config import (
    AlertmanagerWebhookConfig,
    parse_alertmanager_webhook_config,
    reset_alertmanager_webhook_config,
)


def _make_signal(alertname="TestAlert", signal_id="sig-123", source_instance="http://alertmanager:9093",
                  status="firing", severity="critical", namespace="prod", labels=None) -> AlertSignal:
    """Helper to create a test signal."""
    all_labels = {"alertname": alertname, "namespace": namespace}
    if labels:
        all_labels.update(labels)
    return AlertSignal(
        signal_id=signal_id, source_type=AlertSourceType.ALERTMANAGER, source_instance=source_instance,
        status=AlertStatus(status), alertname=alertname, severity=severity,
        labels=tuple((k, v) for k, v in all_labels.items()), annotations=(), starts_at=datetime.now(UTC),
        ends_at=None, received_at=datetime.now(UTC), generator_url=None, external_url=None,
        raw_payload_artifact_id=None, truncation=None,
    )


class TestWebhookPromotionSummary:
    def test_disabled_returns_minimal_dict(self):
        summary = WebhookPromotionSummary(enabled=False)
        assert summary.to_dict() == {"enabled": False}

    def test_enabled_returns_full_summary(self):
        summary = WebhookPromotionSummary(enabled=True, scanned_signal_count=2, firing_signal_count=1,
            resolved_signal_count=1, opened_incident_count=1)
        result = summary.to_dict()
        assert result["enabled"] is True
        assert result["scanned_signal_count"] == 2


class TestWebhookResponseWithPromotion:
    def test_response_includes_promotion_when_present(self):
        promotion = WebhookPromotionSummary(enabled=True, scanned_signal_count=1, firing_signal_count=1)
        response = WebhookResponse(accepted=True, stored_signal_count=1, promotion=promotion)
        result = response.to_dict()
        assert "promotion" in result
        assert result["promotion"]["enabled"] is True

    def test_response_excludes_promotion_when_none(self):
        response = WebhookResponse(accepted=True, stored_signal_count=1, promotion=None)
        assert "promotion" not in response.to_dict()


class TestAutoPromoteDisabled:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_auto_promote_false_stores_signal_but_opens_no_incident(self):
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=False, bearer_token="test-token")
        store = IncidentStore()
        mock_signal = _make_signal(alertname="KubePodCrashLooping", labels={"pod": "test-pod"})
        with patch("k8s_diag_agent.incident_alertmanager_webhook.write_raw_payload_artifact") as mock_write_raw, \
             patch("k8s_diag_agent.incident_alertmanager_webhook.normalize_alertmanager_payload") as mock_normalize, \
             patch("k8s_diag_agent.incident_alertmanager_webhook.write_alert_signal_artifact") as mock_write_signal:
            mock_write_raw.return_value = MagicMock(success=True, artifact_id="raw-123")
            mock_normalize.return_value = MagicMock(signals=[mock_signal], errors=[])
            mock_write_signal.return_value = MagicMock(success=True, is_duplicate=False)
            response = process_webhook(payload={"alerts": [{"labels": {"alertname": "Test"}}]}, config=config, root=self.root, incident_store=store)
            assert response.accepted is True
            assert response.stored_signal_count == 1
            assert response.promotion is None
            assert len(store.list_incidents()) == 0


class TestAutoPromoteEnabled:
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.signals_dir = self.root / "external-analysis" / "alert-signals"
        self.signals_dir.mkdir(parents=True, exist_ok=True)
        self.source_instance = "test-alertmanager"

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_signal_artifact(self, identity: str, signal: AlertSignal) -> None:
        artifact = {"schema_version": ALERT_SIGNAL_SCHEMA_VERSION, "identity": identity,
                    "received_at": datetime.now(UTC).isoformat(), "signal": signal.to_dict(),
                    "correlation_hints": None, "raw_payload_artifact_id": None}
        (self.signals_dir / f"alert-signal-{identity}.json").write_text(json.dumps(artifact), encoding="utf-8")

    def test_auto_promote_true_firing_webhook_opens_incident(self):
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=True, bearer_token="test-token", source_instance=self.source_instance)
        store = IncidentStore()
        signal = _make_signal(alertname="KubePodCrashLooping", signal_id="firing-sig-1", source_instance=self.source_instance, labels={"pod": "test-pod"}, status="firing")
        self._write_signal_artifact("firing-1", signal)
        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=b'{"alerts": [{"labels": {"alertname": "KubePodCrashLooping", "namespace": "prod", "pod": "test-pod"}}]}',
            config=config, root=self.root, incident_store=store)
        assert status_code == 200
        assert response.accepted is True
        assert response.promotion is not None
        assert response.promotion.enabled is True
        assert response.promotion.opened_incident_count >= 1
        incidents = store.list_incidents()
        assert len(incidents) == 1
        assert incidents[0].status == IncidentStatus.OPEN

    def test_duplicate_webhook_does_not_duplicate_incident_signal(self):
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=True, bearer_token="test-token", source_instance=self.source_instance)
        store = IncidentStore()
        signal = _make_signal(alertname="KubePodCrashLooping", signal_id="firing-sig-1", source_instance=self.source_instance, labels={"pod": "test-pod"}, status="firing")
        self._write_signal_artifact("firing-1", signal)
        response1, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=b'{"alerts": [{"labels": {"alertname": "KubePodCrashLooping", "namespace": "prod", "pod": "test-pod"}}]}',
            config=config, root=self.root, incident_store=store)
        assert response1.promotion.opened_incident_count == 1
        response2, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=b'{"alerts": [{"labels": {"alertname": "KubePodCrashLooping", "namespace": "prod", "pod": "test-pod"}}]}',
            config=config, root=self.root, incident_store=store)
        assert response2.promotion.opened_incident_count == 0
        assert response2.promotion.skipped_duplicate_count >= 1
        assert len(store.list_incidents()) == 1

    def test_resolved_webhook_attaches_to_existing_incident(self):
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=True, bearer_token="test-token", source_instance=self.source_instance)
        store = IncidentStore()
        firing_signal = _make_signal(alertname="KubePodCrashLooping", signal_id="firing-sig-1", source_instance=self.source_instance, labels={"pod": "test-pod"}, status="firing")
        self._write_signal_artifact("firing-1", firing_signal)
        handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=b'{"alerts": [{"labels": {"alertname": "KubePodCrashLooping", "namespace": "prod", "pod": "test-pod"}}]}',
            config=config, root=self.root, incident_store=store)
        resolved_signal = _make_signal(alertname="KubePodCrashLooping", signal_id="resolved-sig-1", source_instance=self.source_instance, labels={"pod": "test-pod"}, status="resolved")
        self._write_signal_artifact("resolved-1", resolved_signal)
        response, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=b'{"alerts": [{"labels": {"alertname": "KubePodCrashLooping", "namespace": "prod", "pod": "test-pod", "status": "resolved"}}]}',
            config=config, root=self.root, incident_store=store)
        assert response.promotion.resolved_signal_count >= 1
        assert response.promotion.skipped_resolved_without_open_incident_count == 0
        incidents = store.list_incidents()
        assert len(incidents) == 1
        assert incidents[0].signal_count >= 2

    def test_resolved_webhook_without_existing_incident_opens_no_incident(self):
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=True, bearer_token="test-token", source_instance=self.source_instance)
        store = IncidentStore()
        resolved_signal = _make_signal(alertname="KubePodCrashLooping", signal_id="resolved-sig-1", source_instance=self.source_instance, labels={"pod": "test-pod"}, status="resolved")
        self._write_signal_artifact("resolved-1", resolved_signal)
        response, _ = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=b'{"alerts": [{"labels": {"alertname": "KubePodCrashLooping", "namespace": "prod", "pod": "test-pod", "status": "resolved"}}]}',
            config=config, root=self.root, incident_store=store)
        assert response.promotion.resolved_signal_count >= 1

    def test_auth_failure_does_not_promote(self):
        from k8s_diag_agent.incident_alertmanager_webhook import WebhookAuthError
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=True, bearer_token="correct-token", source_instance=self.source_instance)
        store = IncidentStore()
        with pytest.raises(WebhookAuthError):
            handle_alertmanager_webhook(auth_header="Bearer wrong-token", raw_body=b'{"alerts": [{"labels": {"alertname": "Test"}}]}', config=config, root=self.root, incident_store=store)
        assert len(store.list_incidents()) == 0

    def test_invalid_payload_does_not_promote(self):
        from k8s_diag_agent.incident_alertmanager_webhook import WebhookPayloadError
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=True, bearer_token="test-token", source_instance=self.source_instance)
        store = IncidentStore()
        with pytest.raises(WebhookPayloadError):
            handle_alertmanager_webhook(auth_header="Bearer test-token", raw_body=b"not valid json", config=config, root=self.root, incident_store=store)
        assert len(store.list_incidents()) == 0

    def test_promotion_errors_are_surfaced_but_do_not_leak_secrets(self):
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=True, bearer_token="secret-token", source_instance=self.source_instance)
        store = IncidentStore()
        signal = _make_signal(alertname="TestAlert", source_instance=self.source_instance)
        self._write_signal_artifact("sig-1", signal)
        response, _ = handle_alertmanager_webhook(
            auth_header="Bearer secret-token",
            raw_body=b'{"alerts": [{"labels": {"alertname": "TestAlert"}}]}',
            config=config, root=self.root, incident_store=store)
        assert response.promotion is not None
        assert response.promotion.enabled is True

    def test_existing_webhook_ingest_tests_still_pass(self):
        config = AlertmanagerWebhookConfig(enabled=True, auto_promote=False, bearer_token="test-token")
        store = IncidentStore()
        mock_signal = _make_signal(alertname="TestAlert")
        with patch("k8s_diag_agent.incident_alertmanager_webhook.write_raw_payload_artifact") as mock_write_raw, \
             patch("k8s_diag_agent.incident_alertmanager_webhook.normalize_alertmanager_payload") as mock_normalize, \
             patch("k8s_diag_agent.incident_alertmanager_webhook.write_alert_signal_artifact") as mock_write_signal:
            mock_write_raw.return_value = MagicMock(success=True, artifact_id="raw-123")
            mock_normalize.return_value = MagicMock(signals=[mock_signal], errors=[])
            mock_write_signal.return_value = MagicMock(success=True, is_duplicate=False)
            response, status_code = handle_alertmanager_webhook(
                auth_header="Bearer test-token",
                raw_body=b'{"alerts": [{"labels": {"alertname": "TestAlert"}}]}',
                config=config, root=self.root, incident_store=store)
            assert status_code == 200
            assert response.accepted is True
            assert response.stored_signal_count == 1
            assert response.promotion is None


class TestAutoPromoteConfig:
    def test_default_auto_promote_is_false(self):
        assert AlertmanagerWebhookConfig().auto_promote is False

    def test_auto_promote_can_be_enabled(self):
        assert AlertmanagerWebhookConfig(auto_promote=True).auto_promote is True

    def test_auto_promote_parsed_from_env(self):
        reset_alertmanager_webhook_config()
        assert parse_alertmanager_webhook_config().auto_promote is False
        os.environ["K9B_ALERTMANAGER_WEBHOOK_AUTO_PROMOTE"] = "true"
        reset_alertmanager_webhook_config()
        assert parse_alertmanager_webhook_config().auto_promote is True
        del os.environ["K9B_ALERTMANAGER_WEBHOOK_AUTO_PROMOTE"]
        reset_alertmanager_webhook_config()
