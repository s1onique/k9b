"""Tests for vmalert rule state view model."""

from __future__ import annotations

from k8s_diag_agent.ui.model_vmalert_rule_state import (
    _build_vmalert_rule_state_alert_view,
    _build_vmalert_rule_state_fetch_error_view,
    _build_vmalert_rule_state_rule_group_view,
    _build_vmalert_rule_state_view,
)


class TestBuildVmalertRuleStateView:
    """Tests for _build_vmalert_rule_state_view()."""

    def test_missing_raw_returns_none(self) -> None:
        """Missing/raw None returns None."""
        result = _build_vmalert_rule_state_view(None)
        assert result is None

    def test_malformed_non_mapping_returns_none(self) -> None:
        """Malformed non-mapping returns None."""
        result = _build_vmalert_rule_state_view("not a mapping")
        assert result is None

    def test_empty_mapping_returns_none(self) -> None:
        """Empty mapping returns None."""
        result = _build_vmalert_rule_state_view({})
        assert result is not None
        assert result.alert_count == 0
        assert result.firing_alert_count == 0
        assert result.pending_alert_count == 0
        assert result.critical_firing_count == 0

    def test_alerts_are_parsed(self) -> None:
        """Alerts are parsed correctly."""
        raw = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {
                    "alertname": "TestAlert",
                    "state": "firing",
                    "severity": "critical",
                    "namespace": "default",
                },
                {
                    "alertname": "AnotherAlert",
                    "state": "pending",
                    "severity": "warning",
                    "namespace": "kube-system",
                },
            ],
        }
        result = _build_vmalert_rule_state_view(raw)
        assert result is not None
        assert result.alert_count == 2
        assert len(result.alerts) == 2
        assert result.alerts[0].alertname == "TestAlert"
        assert result.alerts[0].state == "firing"
        assert result.alerts[1].state == "pending"

    def test_rule_groups_are_parsed(self) -> None:
        """Rule groups are parsed correctly."""
        raw = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "rule_groups": [
                {
                    "name": "group1",
                    "file": "/path/to/rules.yaml",
                    "interval": "30s",
                    "rule_count": 10,
                    "firing_alert_count": 2,
                    "error_count": 0,
                },
            ],
        }
        result = _build_vmalert_rule_state_view(raw)
        assert result is not None
        assert result.rule_group_count == 1
        assert len(result.rule_groups) == 1
        assert result.rule_groups[0].name == "group1"
        assert result.rule_groups[0].firing_alert_count == 2

    def test_fetch_errors_are_parsed(self) -> None:
        """Fetch errors are parsed correctly."""
        raw = {
            "source_count": 2,
            "fetched_source_count": 1,
            "failed_source_count": 1,
            "captured_at": "2024-01-01T00:00:00Z",
            "fetch_errors": [
                {
                    "source_endpoint": "http://vmalert:8080",
                    "source_id": "vm-1",
                    "status": "500",
                    "error": "internal server error",
                },
            ],
        }
        result = _build_vmalert_rule_state_view(raw)
        assert result is not None
        assert result.fetch_error_count == 1
        assert len(result.fetch_errors) == 1
        assert result.fetch_errors[0].source_endpoint == "http://vmalert:8080"
        assert result.fetch_errors[0].error == "internal server error"

    def test_firing_pending_critical_counts_are_computed(self) -> None:
        """Firing/pending/critical counts are computed correctly."""
        raw = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "Alert1", "state": "firing", "severity": "critical"},
                {"alertname": "Alert2", "state": "firing", "severity": "warning"},
                {"alertname": "Alert3", "state": "firing", "severity": "critical"},
                {"alertname": "Alert4", "state": "pending", "severity": "info"},
                {"alertname": "Alert5", "state": "pending", "severity": "critical"},
            ],
        }
        result = _build_vmalert_rule_state_view(raw)
        assert result is not None
        assert result.alert_count == 5
        assert result.firing_alert_count == 3
        assert result.pending_alert_count == 2
        assert result.critical_firing_count == 2  # Alert1 and Alert3

    def test_top_alertnames_returns_most_common_firing(self) -> None:
        """top_alertnames returns most common firing alertnames."""
        raw = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "PodNotReady", "state": "firing", "severity": "warning"},
                {"alertname": "HighCpu", "state": "firing", "severity": "warning"},
                {"alertname": "PodNotReady", "state": "firing", "severity": "warning"},
                {"alertname": "HighMemory", "state": "firing", "severity": "warning"},
                {"alertname": "PodNotReady", "state": "pending", "severity": "warning"},  # Not firing
                {"alertname": "HighCpu", "state": "firing", "severity": "warning"},
            ],
        }
        result = _build_vmalert_rule_state_view(raw)
        assert result is not None
        # Should return top 5 by firing count
        assert result.top_alertnames == ("PodNotReady", "HighCpu", "HighMemory")

    def test_severity_counts_counts_firing_alerts_only(self) -> None:
        """severity_counts counts only firing alerts."""
        raw = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "Alert1", "state": "firing", "severity": "critical"},
                {"alertname": "Alert2", "state": "firing", "severity": "warning"},
                {"alertname": "Alert3", "state": "pending", "severity": "critical"},  # Not firing
                {"alertname": "Alert4", "state": "firing", "severity": "warning"},
            ],
        }
        result = _build_vmalert_rule_state_view(raw)
        assert result is not None
        severity_counts = dict(result.severity_counts)
        assert severity_counts.get("critical") == 1
        assert severity_counts.get("warning") == 2

    def test_affected_namespaces_includes_firing_alerts_only(self) -> None:
        """affected_namespaces includes only firing alerts."""
        raw = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "Alert1", "state": "firing", "namespace": "default"},
                {"alertname": "Alert2", "state": "pending", "namespace": "kube-system"},  # Not firing
                {"alertname": "Alert3", "state": "firing", "namespace": "default"},  # Duplicate
                {"alertname": "Alert4", "state": "firing", "namespace": "monitoring"},
            ],
        }
        result = _build_vmalert_rule_state_view(raw)
        assert result is not None
        assert "default" in result.affected_namespaces
        assert "kube-system" not in result.affected_namespaces
        assert "monitoring" in result.affected_namespaces
        # Duplicates removed
        assert result.affected_namespaces.count("default") == 1

    def test_affected_workloads_includes_firing_alerts_only(self) -> None:
        """affected_workloads includes only firing alerts."""
        raw = {
            "source_count": 1,
            "fetched_source_count": 1,
            "failed_source_count": 0,
            "captured_at": "2024-01-01T00:00:00Z",
            "alerts": [
                {"alertname": "Alert1", "state": "firing", "workload": "deployment/app1"},
                {"alertname": "Alert2", "state": "pending", "workload": "deployment/app2"},  # Not firing
                {"alertname": "Alert3", "state": "firing", "workload": "statefulset/db"},
            ],
        }
        result = _build_vmalert_rule_state_view(raw)
        assert result is not None
        assert "deployment/app1" in result.affected_workloads
        assert "deployment/app2" not in result.affected_workloads
        assert "statefulset/db" in result.affected_workloads


class TestBuildVmalertRuleStateAlertView:
    """Tests for _build_vmalert_rule_state_alert_view()."""

    def test_alert_fields_are_parsed(self) -> None:
        """All alert fields are parsed correctly."""
        raw = {
            "alertname": "TestAlert",
            "state": "firing",
            "severity": "critical",
            "cluster_label": "prod-cluster",
            "namespace": "default",
            "workload": "deployment/app",
            "pod": "app-pod-xyz",
            "instance": "10.0.0.1:9100",
            "summary": "Test summary",
            "description": "Test description",
            "active_at": "2024-01-01T00:00:00Z",
            "starts_at": "2023-12-31T00:00:00Z",
            "source_endpoint": "http://vmalert:8080",
            "group_name": "test-group",
            "rule_name": "test-rule",
        }
        result = _build_vmalert_rule_state_alert_view(raw)
        assert result.alertname == "TestAlert"
        assert result.state == "firing"
        assert result.severity == "critical"
        assert result.cluster_label == "prod-cluster"
        assert result.namespace == "default"
        assert result.workload == "deployment/app"
        assert result.pod == "app-pod-xyz"
        assert result.instance == "10.0.0.1:9100"
        assert result.summary == "Test summary"
        assert result.description == "Test description"
        assert result.active_at == "2024-01-01T00:00:00Z"
        assert result.starts_at == "2023-12-31T00:00:00Z"
        assert result.source_endpoint == "http://vmalert:8080"
        assert result.group_name == "test-group"
        assert result.rule_name == "test-rule"

    def test_missing_fields_default_to_none(self) -> None:
        """Missing fields default to None."""
        raw: dict[str, object] = {}
        result = _build_vmalert_rule_state_alert_view(raw)
        assert result.alertname == "unknown"
        assert result.state == "unknown"
        assert result.severity is None
        assert result.namespace is None


class TestBuildVmalertRuleStateRuleGroupView:
    """Tests for _build_vmalert_rule_state_rule_group_view()."""

    def test_rule_group_fields_are_parsed(self) -> None:
        """All rule group fields are parsed correctly."""
        raw = {
            "name": "test-group",
            "file": "/path/to/rules.yaml",
            "interval": "30s",
            "rule_count": 10,
            "firing_alert_count": 2,
            "error_count": 1,
        }
        result = _build_vmalert_rule_state_rule_group_view(raw)
        assert result.name == "test-group"
        assert result.file == "/path/to/rules.yaml"
        assert result.interval == "30s"
        assert result.rule_count == 10
        assert result.firing_alert_count == 2
        assert result.error_count == 1


class TestBuildVmalertRuleStateFetchErrorView:
    """Tests for _build_vmalert_rule_state_fetch_error_view()."""

    def test_fetch_error_fields_are_parsed(self) -> None:
        """All fetch error fields are parsed correctly."""
        raw = {
            "source_endpoint": "http://vmalert:8080",
            "source_id": "vm-1",
            "status": "500",
            "error": "internal server error",
        }
        result = _build_vmalert_rule_state_fetch_error_view(raw)
        assert result.source_endpoint == "http://vmalert:8080"
        assert result.source_id == "vm-1"
        assert result.status == "500"
        assert result.error == "internal server error"

    def test_missing_error_field_defaults_to_empty(self) -> None:
        """Missing error field defaults to empty string."""
        raw = {
            "source_endpoint": "http://vmalert:8080",
            "status": "500",
        }
        result = _build_vmalert_rule_state_fetch_error_view(raw)
        assert result.error == ""
