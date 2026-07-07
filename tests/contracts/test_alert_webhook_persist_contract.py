"""Contract tests: Alertmanager webhook persists alert/candidate data.

These tests prove the persist path:
    Alertmanager webhook payload
      → normalize AlertSignal
      → write alert-signal artifact

Tests that auto_promote=False is also covered here (signal is persisted
but no incident is opened).

Test contracts:
1. Firing webhook stores alert-signal artifact on disk
2. Resolved-only webhook stores signal but opens no incident
3. Auto-promote disabled stores signal but opens no incident
4. Artifact schema_version is correct
"""

from __future__ import annotations

from k8s_diag_agent.incident_alert_signal_store import ALERT_SIGNAL_SCHEMA_VERSION
from k8s_diag_agent.incident_alertmanager_webhook import (
    handle_alertmanager_webhook,
)
from tests.contracts.alert_webhook_persist_promote_contract_support import (
    AlertWebhookContractTest,
    assert_any_alert_signal_artifact_exists,
    assert_incident_count,
    assert_promotion_summary,
    assert_stored_signal_count,
    make_firing_payload,
    make_incident_store,
    make_resolved_payload,
    make_webhook_config,
    read_artifact,
)


class TestPersistFiringAlert(AlertWebhookContractTest):
    """Contract: firing webhook stores alert-signal artifact."""

    def test_firing_webhook_stores_artifact(self):
        """Firing webhook should store alert-signal artifact on disk."""
        config = make_webhook_config(auto_promote=False)
        store = make_incident_store()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname="KubePodCrashLooping",
                namespace="prod",
                pod="crashloop-pod-xyz",
                severity="critical",
                summary="Pod is in crash loop",
                description="Pod crashloop-pod-xyz has been restarting",
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200, f"Expected 200, got {status_code}"
        assert response.accepted is True, "Webhook should be accepted"
        assert_stored_signal_count(response, 1)

        # Artifact exists on disk
        artifact_path = assert_any_alert_signal_artifact_exists(self.root)
        artifact_data = read_artifact(artifact_path)
        assert artifact_data["schema_version"] == ALERT_SIGNAL_SCHEMA_VERSION
        assert artifact_data["signal"] is not None

        # No incident opened (auto_promote=False)
        assert_incident_count(store, 0)


class TestPersistResolvedOnly(AlertWebhookContractTest):
    """Contract: resolved-only webhook stores signal but opens no incident."""

    def test_resolved_only_opens_no_incident(self):
        """Resolved-only webhook should not open incident."""
        config = make_webhook_config(auto_promote=True)
        store = make_incident_store()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_resolved_payload(
                alertname="KubePodCrashLooping",
                namespace="prod",
                pod="crashloop-pod-xyz",
                severity="critical",
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        assert_stored_signal_count(response, 1)

        # Promotion reflects resolved-only
        assert response.promotion is not None
        assert_promotion_summary(
            response,
            resolved_signal_count=1,
            opened_incident_count=0,
            skipped_resolved_without_open_incident_count=1,
        )

        # No incident
        assert_incident_count(store, 0)


class TestPersistAutoPromoteDisabled(AlertWebhookContractTest):
    """Contract: auto_promote=False stores signal but opens no incident."""

    def test_auto_promote_disabled_stores_signal_no_incident(self):
        """With auto_promote=False, signal should be stored but no incident opened."""
        config = make_webhook_config(auto_promote=False)
        store = make_incident_store()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname="KubePodCrashLooping",
                namespace="prod",
                pod="crashloop-pod-xyz",
                severity="critical",
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        assert response.accepted is True
        assert_stored_signal_count(response, 1)

        # Artifact exists
        assert_any_alert_signal_artifact_exists(self.root)

        # Promotion disabled
        if response.promotion is not None:
            assert response.promotion.enabled is False

        # No incident
        assert_incident_count(store, 0)
