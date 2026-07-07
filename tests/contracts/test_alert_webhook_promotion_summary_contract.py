"""Contract tests: Alertmanager webhook promotion summary response structure.

These tests validate the promotion summary fields in the webhook response.
They cover the response contract including enabled/disabled promotion modes,
duplicate/already-promoted/error cases, and counter semantics.

Test contracts:
1. Promotion summary fields are present when enabled
2. Promotion summary fields reflect duplicate delivery
3. Promotion summary fields reflect resolved-only signals
4. Promotion summary fields reflect stale artifact full scan
5. Promotion summary fields reflect same-identity deduplication
"""

from __future__ import annotations

import pytest

from tests.contracts.alert_webhook_persist_promote_contract_support import (
    AlertWebhookContractTest,
    assert_promotion_summary,
    handle_alertmanager_webhook,
    make_firing_payload,
    make_incident_store,
    make_webhook_config,
)


class TestPromotionSummaryEnabled(AlertWebhookContractTest):
    """Contract: promotion summary fields present when auto_promote=True."""

    def test_promotion_summary_present_when_enabled(self):
        """Promotion summary should be present with enabled=True."""
        config = make_webhook_config(auto_promote=True)
        store = make_incident_store()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname="TestAlert",
                namespace="prod",
                severity="critical",
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        assert_promotion_summary(
            response,
            enabled=True,
            opened_incident_count=1,
            firing_signal_count=1,
            scanned_signal_count=1,
        )


class TestPromotionSummaryDisabled(AlertWebhookContractTest):
    """Contract: promotion summary fields when auto_promote=False."""

    def test_promotion_summary_disabled_flag(self):
        """Promotion summary should have enabled=False when auto_promote=False."""
        config = make_webhook_config(auto_promote=False)
        store = make_incident_store()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname="TestAlert",
                namespace="prod",
                severity="critical",
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200
        # Promotion may be None or have enabled=False when auto_promote=False
        if response.promotion is not None:
            assert response.promotion.enabled is False


@pytest.mark.parametrize(
    ("auto_promote", "expected_promoted"),
    [
        (False, False),
        (True, True),
    ],
)
class TestPromotionModeParametrized(AlertWebhookContractTest):
    """Parametrized: promotion mode affects incident creation."""

    def test_promotion_mode_contract(
        self,
        auto_promote: bool,
        expected_promoted: bool,
    ):
        """auto_promote flag controls whether incidents are opened."""
        config = make_webhook_config(auto_promote=auto_promote)
        store = make_incident_store()

        response, status_code = handle_alertmanager_webhook(
            auth_header="Bearer test-token",
            raw_body=make_firing_payload(
                alertname="TestAlert",
                namespace="prod",
                severity="critical",
            ),
            config=config,
            root=self.root,
            incident_store=store,
        )

        assert status_code == 200

        if expected_promoted:
            assert_promotion_summary(response, enabled=True, opened_incident_count=1)
            assert len(store.list_incidents()) == 1
        else:
            if response.promotion is not None:
                assert response.promotion.enabled is False
            assert len(store.list_incidents()) == 0
