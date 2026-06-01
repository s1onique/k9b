"""Unit tests for vmalert rule state normalization module.

Tests cover:
- normalize_vmalert_response() for /api/v1/alerts and /api/v1/rules shapes
- VmalertAlertSignal model: firing, pending, severity, namespace/workload derivation
- VmalertRuleGroup model: to_dict/from_dict roundtrip
- String truncation for long fields
- AlertState enum values
"""

from __future__ import annotations

from typing import Any

import pytest

from k8s_diag_agent.external_analysis.vmalert_rule_state import (
    AlertState,
    VmalertAlertSignal,
    VmalertRule,
    VmalertRuleGroup,
    normalize_vmalert_response,
)

# --- Test Fixtures ---


@pytest.fixture
def alerts_response() -> dict[str, Any]:
    """Valid /api/v1/alerts response shape."""
    return {
        "status": "success",
        "data": {
            "alerts": [
                {
                    "state": "firing",
                    "labels": {
                        "alertname": "CriticalAlert",
                        "severity": "critical",
                        "namespace": "monitoring",
                        "cluster": "prod-01",
                        "pod": "myapp-abc123",
                    },
                    "annotations": {
                        "summary": "Critical issue detected",
                        "description": "Action required immediately",
                    },
                    "activeAt": "2024-01-01T10:00:00Z",
                    "value": "0.95",
                    "expr": "metric > threshold",
                },
                {
                    "state": "pending",
                    "labels": {
                        "alertname": "WarningAlert",
                        "severity": "warning",
                    },
                },
                {
                    "state": "firing",
                    "labels": {
                        "alertname": "InActiveAlert",
                        "severity": "info",
                        "state": "inactive",  # Should use top-level state
                    },
                },
            ]
        },
    }


@pytest.fixture
def rules_response() -> dict[str, Any]:
    """Valid /api/v1/rules response shape."""
    return {
        "status": "success",
        "data": {
            "groups": [
                {
                    "name": "node-alerts",
                    "file": "/etc/vmalert/rules.yaml",
                    "interval": "30s",
                    "rules": [
                        {
                            "name": "NodeNotReady",
                            "type": "alerting",
                            "health": "ok",
                            "alerts": [
                                {
                                    "state": "firing",
                                    "labels": {
                                        "alertname": "NodeNotReady",
                                        "severity": "critical",
                                        "k8s_namespace": "default",
                                    },
                                    "annotations": {
                                        "summary": "Node is not ready",
                                    },
                                }
                            ],
                        },
                        {
                            "name": "HealthyRule",
                            "type": "recording",
                            "health": "ok",
                        },
                        {
                            "name": "ErrorRule",
                            "type": "alerting",
                            "health": "err",
                            "last_error": "query timeout after 30s",
                        },
                    ],
                },
                {
                    "name": "pod-alerts",
                    "interval": "60s",
                    "rules": [],
                },
            ]
        },
    }


@pytest.fixture
def error_response() -> dict[str, Any]:
    """Error response shape."""
    return {
        "status": "error",
        "error": "some error occurred",
    }


# --- normalize_vmalert_response Tests ---


class TestNormalizeVmalertResponse:
    """Tests for normalize_vmalert_response()."""

    def test_handles_alerts_shape(self, alerts_response: dict[str, Any]) -> None:
        """normalize_vmalert_response() handles /api/v1/alerts shape."""
        alerts, rule_groups = normalize_vmalert_response(alerts_response, "http://test:8080")

        assert len(alerts) == 3
        assert len(rule_groups) == 0

    def test_handles_rules_shape(self, rules_response: dict[str, Any]) -> None:
        """normalize_vmalert_response() handles /api/v1/rules shape."""
        alerts, rule_groups = normalize_vmalert_response(rules_response, "http://test:8080")

        # Should have alerts from the rules
        assert len(alerts) >= 1
        # Should have rule groups
        assert len(rule_groups) == 2

    def test_firing_alert_has_correct_state(self, alerts_response: dict[str, Any]) -> None:
        """Firing alert normalizes to AlertState.FIRING."""
        alerts, _ = normalize_vmalert_response(alerts_response, "http://test:8080")

        firing_alerts = [a for a in alerts if a.state == AlertState.FIRING]
        assert len(firing_alerts) >= 2

        critical = [a for a in alerts if a.is_firing and a.is_critical]
        assert len(critical) >= 1

    def test_pending_alert_is_pending_but_not_firing(self, alerts_response: dict[str, Any]) -> None:
        """Pending alert has pending state but is not firing."""
        alerts, _ = normalize_vmalert_response(alerts_response, "http://test:8080")

        pending = [a for a in alerts if a.state == AlertState.PENDING]
        assert len(pending) >= 1
        assert all(not a.is_firing for a in pending)

    def test_namespace_derivation_from_labels(self, alerts_response: dict[str, Any]) -> None:
        """Namespace is derived from labels."""
        alerts, _ = normalize_vmalert_response(alerts_response, "http://test:8080")

        # Find the alert with namespace in labels
        ns_alert = next((a for a in alerts if a.namespace == "monitoring"), None)
        assert ns_alert is not None

    def test_workload_derivation_from_pod(self, alerts_response: dict[str, Any]) -> None:
        """Workload is derived from pod label by stripping common suffixes."""
        alerts, _ = normalize_vmalert_response(alerts_response, "http://test:8080")

        # Pod myapp-abc123 should derive workload myapp
        workload_alert = next((a for a in alerts if a.workload == "myapp"), None)
        assert workload_alert is not None

    def test_unknown_state_maps_to_unknown(self) -> None:
        """Unknown state value maps to AlertState.UNKNOWN."""
        response = {
            "status": "success",
            "data": {
                "alerts": [
                    {
                        "state": "unknown-state-value",
                        "labels": {
                            "alertname": "TestAlert",
                        },
                    }
                ]
            },
        }

        alerts, _ = normalize_vmalert_response(response, "http://test:8080")
        assert len(alerts) == 1
        assert alerts[0].state == AlertState.UNKNOWN

    def test_long_fields_are_truncated(self) -> None:
        """Long summary/expression fields are truncated."""
        long_string = "x" * 300
        response = {
            "status": "success",
            "data": {
                "alerts": [
                    {
                        "state": "firing",
                        "labels": {
                            "alertname": "TestAlert",
                        },
                        "annotations": {
                            "summary": long_string,
                        },
                        "expr": long_string,
                    }
                ]
            },
        }

        alerts, _ = normalize_vmalert_response(response, "http://test:8080", max_string_length=200)
        assert len(alerts) == 1

        # Summary should be truncated
        if alerts[0].summary:
            assert len(alerts[0].summary) <= 200

        # Expression should be truncated
        if alerts[0].expression:
            assert len(alerts[0].expression) <= 200

    def test_returns_empty_on_error_response(self, error_response: dict[str, Any]) -> None:
        """Returns empty tuples on error response."""
        alerts, rule_groups = normalize_vmalert_response(error_response, "http://test:8080")

        assert alerts == ()
        assert rule_groups == ()

    def test_skips_non_dict_alerts(self) -> None:
        """Skips non-dict items in alerts list."""
        response = {
            "status": "success",
            "data": {
                "alerts": [
                    {"state": "firing", "labels": {"alertname": "ValidAlert"}},
                    None,  # Invalid
                    "not a dict",  # Invalid
                    123,  # Invalid
                ]
            },
        }

        alerts, _ = normalize_vmalert_response(response, "http://test:8080")
        assert len(alerts) == 1
        assert alerts[0].alertname == "ValidAlert"

    def test_skips_non_dict_groups(self) -> None:
        """Skips non-dict items in groups list."""
        response = {
            "status": "success",
            "data": {
                "groups": [
                    {"name": "valid-group", "rules": []},
                    None,
                    "not a dict",
                ]
            },
        }

        _, rule_groups = normalize_vmalert_response(response, "http://test:8080")
        assert len(rule_groups) == 1
        assert rule_groups[0].name == "valid-group"

    def test_source_endpoint_in_alerts(self, alerts_response: dict[str, Any]) -> None:
        """Source endpoint is set on alerts."""
        endpoint = "http://vmalert.ns:8080"
        alerts, _ = normalize_vmalert_response(alerts_response, endpoint)

        assert all(a.source_endpoint == endpoint for a in alerts)

    def test_cluster_label_extracted(self, alerts_response: dict[str, Any]) -> None:
        """Cluster label is extracted from labels."""
        alerts, _ = normalize_vmalert_response(alerts_response, "http://test:8080")

        cluster_alert = next((a for a in alerts if a.cluster_label == "prod-01"), None)
        assert cluster_alert is not None

    def test_rule_group_counts(self, rules_response: dict[str, Any]) -> None:
        """Rule groups have correct rule and alert counts."""
        _, rule_groups = normalize_vmalert_response(rules_response, "http://test:8080")

        node_group = next((g for g in rule_groups if g.name == "node-alerts"), None)
        assert node_group is not None
        assert node_group.rule_count == 3
        assert node_group.firing_alert_count >= 1
        assert node_group.error_count == 1  # One rule has health=err

    def test_rule_group_includes_source_endpoint(self, rules_response: dict[str, Any]) -> None:
        """Rule groups include source endpoint."""
        endpoint = "http://vmalert.ns:8080"
        _, rule_groups = normalize_vmalert_response(rules_response, endpoint)

        assert all(g.source_endpoint == endpoint for g in rule_groups)

    def test_rule_group_interval_and_file(self, rules_response: dict[str, Any]) -> None:
        """Rule groups include interval and file if present."""
        _, rule_groups = normalize_vmalert_response(rules_response, "http://test:8080")

        node_group = next((g for g in rule_groups if g.name == "node-alerts"), None)
        assert node_group is not None
        assert node_group.interval == "30s"
        assert node_group.file == "/etc/vmalert/rules.yaml"


# --- VmalertAlertSignal Tests ---


class TestVmalertAlertSignal:
    """Tests for VmalertAlertSignal model."""

    def test_is_firing_property(self) -> None:
        """is_firing returns True only for firing state."""
        firing = VmalertAlertSignal(
            alertname="Test",
            state=AlertState.FIRING,
        )
        assert firing.is_firing is True

        pending = VmalertAlertSignal(
            alertname="Test",
            state=AlertState.PENDING,
        )
        assert pending.is_firing is False

    def test_is_pending_property(self) -> None:
        """is_pending returns True only for pending state."""
        pending = VmalertAlertSignal(
            alertname="Test",
            state=AlertState.PENDING,
        )
        assert pending.is_pending is True

        firing = VmalertAlertSignal(
            alertname="Test",
            state=AlertState.FIRING,
        )
        assert firing.is_pending is False

    def test_is_critical_property(self) -> None:
        """is_critical returns True only for severity=critical."""
        critical = VmalertAlertSignal(
            alertname="Test",
            state=AlertState.FIRING,
            severity="critical",
        )
        assert critical.is_critical is True

        warning = VmalertAlertSignal(
            alertname="Test",
            state=AlertState.FIRING,
            severity="warning",
        )
        assert warning.is_critical is False

    def test_is_critical_normalizes_case(self) -> None:
        """is_critical handles case normalization."""
        alert = VmalertAlertSignal(
            alertname="Test",
            state=AlertState.FIRING,
            severity="CRITICAL",  # Upper case
        )
        # After post_init, severity should be lowercase
        assert alert.severity == "critical"
        assert alert.is_critical is True

    def test_labels_dict_property(self) -> None:
        """labels_dict returns labels as dict."""
        alert = VmalertAlertSignal(
            alertname="Test",
            state=AlertState.FIRING,
            labels=(("severity", "warning"), ("cluster", "prod")),
        )
        labels = alert.labels_dict
        assert isinstance(labels, dict)
        assert labels["severity"] == "warning"
        assert labels["cluster"] == "prod"

    def test_to_dict_roundtrip(self) -> None:
        """VmalertAlertSignal survives to_dict/from_dict roundtrip."""
        original = VmalertAlertSignal(
            alertname="TestAlert",
            state=AlertState.FIRING,
            labels=(("severity", "critical"),),
            severity="critical",
            namespace="monitoring",
            workload="myapp",
            summary="Test summary",
            expression="metric > threshold",
            active_at="2024-01-01T00:00:00Z",
        )

        data = original.to_dict()
        restored = VmalertAlertSignal.from_dict(data)

        assert restored.alertname == original.alertname
        assert restored.state == original.state
        assert restored.severity == original.severity
        assert restored.namespace == original.namespace
        assert restored.workload == original.workload

    def test_from_dict_handles_unknown_state(self) -> None:
        """from_dict handles unknown state values gracefully."""
        data = {
            "alertname": "Test",
            "state": "not-a-valid-state",
        }
        alert = VmalertAlertSignal.from_dict(data)
        assert alert.state == AlertState.UNKNOWN

    def test_from_dict_handles_missing_fields(self) -> None:
        """from_dict handles missing fields gracefully."""
        data: dict[str, Any] = {}
        alert = VmalertAlertSignal.from_dict(data)
        assert alert.alertname == "unknown"
        assert alert.state == AlertState.UNKNOWN


# --- VmalertRuleGroup Tests ---


class TestVmalertRuleGroup:
    """Tests for VmalertRuleGroup model."""

    def test_to_dict_roundtrip(self) -> None:
        """VmalertRuleGroup survives to_dict/from_dict roundtrip."""
        original = VmalertRuleGroup(
            name="test-group",
            file="/etc/rules.yaml",
            interval="30s",
            rule_count=5,
            firing_alert_count=2,
            error_count=1,
            source_endpoint="http://test:8080",
        )

        data = original.to_dict()
        restored = VmalertRuleGroup.from_dict(data)

        assert restored.name == original.name
        assert restored.file == original.file
        assert restored.interval == original.interval
        assert restored.rule_count == original.rule_count
        assert restored.firing_alert_count == original.firing_alert_count
        assert restored.error_count == original.error_count

    def test_to_dict_omits_none_fields(self) -> None:
        """to_dict omits None fields for optional attributes."""
        group = VmalertRuleGroup(
            name="test-group",
        )

        data = group.to_dict()
        assert "file" not in data or data.get("file") is None
        assert "interval" not in data or data.get("interval") is None

    def test_from_dict_handles_missing_fields(self) -> None:
        """from_dict handles missing fields with defaults."""
        data: dict[str, Any] = {"name": "minimal-group"}
        group = VmalertRuleGroup.from_dict(data)

        assert group.name == "minimal-group"
        assert group.file is None
        assert group.interval is None
        assert group.rule_count == 0


# --- VmalertRule Tests ---


class TestVmalertRule:
    """Tests for VmalertRule model."""

    def test_to_dict_roundtrip(self) -> None:
        """VmalertRule survives to_dict/from_dict roundtrip."""
        original = VmalertRule(
            name="TestRule",
            type="alerting",
            health="ok",
            last_error="Some error that needs truncation",
            query="very long query expression" * 50,
            source_endpoint="http://test:8080",
            group_name="test-group",
        )

        data = original.to_dict()
        restored = VmalertRule.from_dict(data)

        assert restored.name == original.name
        assert restored.type == original.type
        assert restored.health == original.health
        assert restored.source_endpoint == original.source_endpoint
        assert restored.group_name == original.group_name

    def test_to_dict_truncates_long_fields(self) -> None:
        """to_dict truncates long last_error and query fields."""
        long_error = "x" * 300
        long_query = "y" * 300

        rule = VmalertRule(
            name="Test",
            last_error=long_error,
            query=long_query,
        )

        data = rule.to_dict()

        # Both should be truncated to 200 chars (197 + "...")
        if data.get("last_error"):
            assert len(data["last_error"]) <= 200
        if data.get("query"):
            assert len(data["query"]) <= 200


# --- AlertState Tests ---


class TestAlertState:
    """Tests for AlertState enum."""

    def test_all_expected_values(self) -> None:
        """AlertState has all expected values."""
        assert AlertState.FIRING.value == "firing"
        assert AlertState.PENDING.value == "pending"
        assert AlertState.INACTIVE.value == "inactive"
        assert AlertState.UNKNOWN.value == "unknown"

    def test_valid_state_values(self) -> None:
        """AlertState has expected string values."""
        # Test that StrEnum values match expected strings
        assert str(AlertState.FIRING) == "firing"
        assert str(AlertState.PENDING) == "pending"
        assert str(AlertState.INACTIVE) == "inactive"
        assert str(AlertState.UNKNOWN) == "unknown"

    def test_invalid_value_raises(self) -> None:
        """Invalid AlertState value raises ValueError."""
        with pytest.raises(ValueError):
            AlertState("invalid-state")
