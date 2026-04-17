"""Unit tests for Alertmanager integration: config, snapshot, compact summarization, and artifact persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from k8s_diag_agent.external_analysis.adapter import (
    ExternalAnalysisAdapterConfig,
    ExternalAnalysisRequest,
    build_external_analysis_adapters,
)
from k8s_diag_agent.external_analysis.alertmanager_artifact import (
    alertmanager_artifacts_exist,
    read_alertmanager_compact,
    read_alertmanager_snapshot,
    write_alertmanager_artifacts,
    write_alertmanager_compact,
    write_alertmanager_snapshot,
)
from k8s_diag_agent.external_analysis.alertmanager_config import (
    AlertmanagerAuth,
    AlertmanagerConfig,
    parse_alertmanager_config,
)
from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    _compute_deterministic_fingerprint,
    create_error_snapshot,
    normalize_alertmanager_payload,
    snapshot_to_compact,
)
from k8s_diag_agent.external_analysis.config import ExternalAnalysisSettings

# --- Config tests ---

def test_alertmanager_config_defaults() -> None:
    config = AlertmanagerConfig()
    assert config.enabled is True
    assert config.endpoint is None
    assert config.timeout_seconds == 10.0
    assert config.max_alerts_in_snapshot == 200
    assert config.max_alerts_in_compact == 20
    assert config.max_string_length == 200


def test_alertmanager_config_is_configured() -> None:
    config = AlertmanagerConfig()
    assert config.is_configured() is False
    config_with_endpoint = AlertmanagerConfig(endpoint="http://localhost:9093")
    assert config_with_endpoint.is_configured() is True


def test_alertmanager_auth_has_auth() -> None:
    auth = AlertmanagerAuth()
    assert auth.has_auth() is False
    auth_with_bearer = AlertmanagerAuth(bearer_token="secret")
    assert auth_with_bearer.has_auth() is True
    auth_with_user = AlertmanagerAuth(username="user", password="pass")
    assert auth_with_user.has_auth() is True


def test_parse_alertmanager_config_full() -> None:
    raw = {
        "enabled": False,
        "endpoint": "http://am.example.com:9093",
        "timeout_seconds": 30,
        "auth": {"bearer_token": "tok123"},
        "max_alerts_in_snapshot": 100,
        "max_alerts_in_compact": 10,
        "max_string_length": 100,
    }
    config = parse_alertmanager_config(raw)
    assert config.enabled is False
    assert config.endpoint == "http://am.example.com:9093"
    assert config.timeout_seconds == 30.0
    assert config.auth.bearer_token == "tok123"
    assert config.max_alerts_in_snapshot == 100
    assert config.max_alerts_in_compact == 10
    assert config.max_string_length == 100


def test_parse_alertmanager_config_minimal() -> None:
    config = parse_alertmanager_config(None)
    assert config.enabled is True
    assert config.endpoint is None


# --- Snapshot normalization tests ---

def _make_alert(alertname: str, severity: str = "warning", **labels: str) -> dict[str, Any]:
    base_labels = {"alertname": alertname, "severity": severity, "cluster": "prod", "namespace": "default"}
    base_labels.update(labels)
    return {
        "labels": base_labels,
        "annotations": {"summary": f"Alert {alertname} fired"},
        "state": "active",
        "startsAt": "2024-01-01T00:00:00Z",
    }


def test_normalize_active_alerts_success() -> None:
    raw = {
        "data": {
            "alerts": [
                _make_alert("HighCPU", "critical", namespace="monitoring"),
                _make_alert("DiskFull", "warning", namespace="storage"),
            ]
        }
    }
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert snapshot.alert_count == 2
    assert len(snapshot.alerts) == 2
    assert snapshot.errors == ()
    assert snapshot.truncated is False


def test_normalize_top_level_list_format() -> None:
    """Test that direct list format from Alertmanager API v2 is handled."""
    raw = [
        _make_alert("HighCPU", "critical", namespace="monitoring"),
        _make_alert("DiskFull", "warning", namespace="storage"),
    ]
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert snapshot.alert_count == 2
    assert len(snapshot.alerts) == 2


def test_normalize_empty_alert_list() -> None:
    raw: dict[str, object] = {"data": {"alerts": []}}
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.EMPTY
    assert snapshot.alert_count == 0
    assert snapshot.alerts == ()


def test_normalize_null_response() -> None:
    snapshot = normalize_alertmanager_payload(None)
    assert snapshot.status == AlertmanagerStatus.INVALID_RESPONSE
    assert "null/empty" in snapshot.errors[0]


def test_normalize_invalid_json_string() -> None:
    snapshot = normalize_alertmanager_payload("not valid json {{{")
    assert snapshot.status == AlertmanagerStatus.INVALID_RESPONSE


def test_normalize_timeout_path() -> None:
    snapshot = create_error_snapshot(
        AlertmanagerStatus.TIMEOUT,
        "Connection timed out after 10s",
        source="http://am:9093",
    )
    assert snapshot.status == AlertmanagerStatus.TIMEOUT
    assert snapshot.alert_count == 0
    assert "timed out" in snapshot.errors[0]


def test_normalize_auth_error_path() -> None:
    snapshot = create_error_snapshot(
        AlertmanagerStatus.AUTH_ERROR,
        "401 Unauthorized",
    )
    assert snapshot.status == AlertmanagerStatus.AUTH_ERROR
    assert snapshot.alert_count == 0


def test_normalize_invalid_response_non_dict() -> None:
    # A number is not a valid response format
    snapshot = normalize_alertmanager_payload(42)
    assert snapshot.status == AlertmanagerStatus.INVALID_RESPONSE


def test_normalize_truncation() -> None:
    alerts = [_make_alert(f"Alert{i}", namespace=f"ns{i}") for i in range(250)]
    raw = {"data": {"alerts": alerts}}
    snapshot = normalize_alertmanager_payload(raw, config_max_alerts=200)
    assert snapshot.truncated is True
    assert snapshot.alert_count == 250
    assert len(snapshot.alerts) == 200


def test_deterministic_fingerprint() -> None:
    """Test that fingerprints are deterministic across calls."""
    labels = tuple(sorted([("alertname", "Test"), ("severity", "warning")]))
    fp1 = _compute_deterministic_fingerprint(labels)
    fp2 = _compute_deterministic_fingerprint(labels)
    assert fp1 == fp2
    assert len(fp1) == 32  # MD5 hex digest truncated to 32 chars


def test_deterministic_fingerprint_different_inputs() -> None:
    """Test that different labels produce different fingerprints."""
    labels1 = tuple(sorted([("alertname", "Test1"), ("severity", "warning")]))
    labels2 = tuple(sorted([("alertname", "Test2"), ("severity", "warning")]))
    fp1 = _compute_deterministic_fingerprint(labels1)
    fp2 = _compute_deterministic_fingerprint(labels2)
    assert fp1 != fp2


def test_fingerprint_used_when_not_provided() -> None:
    """Test that computed fingerprint is used when labels.fingerprint is missing."""
    alert_without_fp = {
        "labels": {"alertname": "TestAlert", "severity": "warning"},
        "annotations": {"summary": "Test alert"},
        "state": "active",
    }
    raw = {"data": {"alerts": [alert_without_fp]}}
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert len(snapshot.alerts) == 1
    # Fingerprint should be computed from sorted labels
    assert snapshot.alerts[0].fingerprint is not None
    assert len(snapshot.alerts[0].fingerprint) == 32


def test_explicit_fingerprint_preserved() -> None:
    """Test that explicit fingerprint in labels is preserved."""
    explicit_fp = "my-explicit-fingerprint-123"
    alert_with_fp = {
        "labels": {"alertname": "TestAlert", "severity": "warning", "fingerprint": explicit_fp},
        "annotations": {"summary": "Test alert"},
        "state": "active",
    }
    raw = {"data": {"alerts": [alert_with_fp]}}
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert snapshot.alerts[0].fingerprint == explicit_fp


# --- Compact summarization tests ---

def test_snapshot_to_compact_deterministic_ordering() -> None:
    raw = {
        "data": {
            "alerts": [
                _make_alert("AlertC", "critical", namespace="ns-c"),
                _make_alert("AlertA", "warning", namespace="ns-a"),
                _make_alert("AlertB", "warning", namespace="ns-b"),
                _make_alert("AlertA", "warning", namespace="ns-a"),
            ]
        }
    }
    snapshot = normalize_alertmanager_payload(raw)
    compact1 = snapshot_to_compact(snapshot, max_alerts=10)
    compact2 = snapshot_to_compact(snapshot, max_alerts=10)
    # Same input produces same bytes
    assert compact1.to_json_bytes() == compact2.to_json_bytes()
    # Severity counts sorted
    assert compact1.severity_counts == (("critical", 1), ("warning", 3))
    # Top alert names sorted by count desc, then name
    assert compact1.top_alert_names == ("AlertA", "AlertB", "AlertC")
    # Namespaces sorted
    assert compact1.affected_namespaces == ("ns-a", "ns-b", "ns-c")
    # Clusters extracted
    assert compact1.affected_clusters == ("prod",)


def test_snapshot_to_compact_truncation() -> None:
    alerts = [
        _make_alert(f"Alert{i}", namespace=f"namespace{i}")
        for i in range(50)
    ]
    raw = {"data": {"alerts": alerts}}
    snapshot = normalize_alertmanager_payload(raw, config_max_alerts=200)
    compact = snapshot_to_compact(snapshot, max_alerts=10)
    assert compact.truncated is False
    assert len(compact.top_alert_names) == 10
    assert len(compact.affected_namespaces) == 10


def test_compact_json_bytes_stable() -> None:
    """Verify to_json_bytes produces identical output for same input."""
    raw = {
        "data": {
            "alerts": [
                _make_alert("TestAlert", "warning", cluster="test"),
            ]
        }
    }
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    bytes1 = compact.to_json_bytes()
    bytes2 = compact.to_json_bytes()
    assert bytes1 == bytes2
    # Verify it's valid JSON
    parsed = json.loads(bytes1)
    assert parsed["status"] == "ok"
    assert parsed["alert_count"] == 1


def test_compact_to_dict_includes_all_fields() -> None:
    raw = {"data": {"alerts": [_make_alert("X", "info")]}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    d = compact.to_dict()
    assert "status" in d
    assert "alert_count" in d
    assert "severity_counts" in d
    assert "state_counts" in d
    assert "top_alert_names" in d
    assert "affected_namespaces" in d
    assert "affected_clusters" in d
    assert "affected_services" in d
    assert "truncated" in d
    assert "captured_at" in d


# --- Artifact persistence tests ---

def test_write_and_read_snapshot(tmp_path: Path) -> None:
    raw = {"data": {"alerts": [_make_alert("PersistTest", "warning")]}}
    snapshot = normalize_alertmanager_payload(raw)
    run_id = "test-run-123"
    path = write_alertmanager_snapshot(tmp_path, snapshot, run_id)
    assert path.exists()
    assert f"{run_id}-alertmanager-snapshot.json" == path.name
    # Read back
    loaded = read_alertmanager_snapshot(path)
    assert loaded is not None
    assert loaded.status == snapshot.status
    assert loaded.alert_count == snapshot.alert_count
    assert len(loaded.alerts) == len(snapshot.alerts)


def test_write_and_read_compact(tmp_path: Path) -> None:
    raw = {"data": {"alerts": [_make_alert("CompactTest", "critical")]}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    run_id = "test-run-456"
    path = write_alertmanager_compact(tmp_path, compact, run_id)
    assert path.exists()
    assert f"{run_id}-alertmanager-compact.json" == path.name
    # Read back
    loaded = read_alertmanager_compact(path)
    assert loaded is not None
    assert loaded.status == compact.status
    assert loaded.alert_count == compact.alert_count


def test_write_both_artifacts(tmp_path: Path) -> None:
    raw = {"data": {"alerts": [_make_alert("BothTest", "info")]}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    run_id = "test-run-789"
    snap_path, compact_path = write_alertmanager_artifacts(tmp_path, run_id, snapshot, compact)
    assert snap_path.exists()
    assert compact_path.exists()


def test_alertmanager_artifacts_exist(tmp_path: Path) -> None:
    raw: dict[str, object] = {"data": {"alerts": []}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    run_id = "check-exists"
    # Initially don't exist
    snap_exists, compact_exists = alertmanager_artifacts_exist(tmp_path, run_id)
    assert snap_exists is False
    assert compact_exists is False
    # Write them
    write_alertmanager_artifacts(tmp_path, run_id, snapshot, compact)
    # Now they exist
    snap_exists, compact_exists = alertmanager_artifacts_exist(tmp_path, run_id)
    assert snap_exists is True
    assert compact_exists is True


def test_read_nonexistent_snapshot_returns_none(tmp_path: Path) -> None:
    result = read_alertmanager_snapshot(tmp_path / "nonexistent.json")
    assert result is None


def test_read_corrupt_snapshot_returns_none(tmp_path: Path) -> None:
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("not valid json {{{", encoding="utf-8")
    result = read_alertmanager_snapshot(corrupt_file)
    assert result is None


def test_snapshot_roundtrip() -> None:
    """Test full roundtrip: dict -> snapshot -> dict -> snapshot."""
    raw = {"data": {"alerts": [_make_alert("RoundTrip", "error", namespace="test-ns")]}}
    original = normalize_alertmanager_payload(raw)
    serialized = original.to_dict()
    restored = AlertmanagerSnapshot.from_dict(serialized)
    assert restored.status == original.status
    assert restored.alert_count == original.alert_count
    assert len(restored.alerts) == len(original.alerts)
    assert restored.captured_at == original.captured_at


# --- Adapter builder integration test ---

def test_adapter_builder_wires_config() -> None:
    """Test that adapter builder receives and uses AlertmanagerConfig from settings."""
    # Create settings with custom Alertmanager config
    settings = ExternalAnalysisSettings(
        alertmanager=AlertmanagerConfig(
            endpoint="http://custom-alertmanager:9093",
            timeout_seconds=30.0,
            max_alerts_in_snapshot=50,
            max_alerts_in_compact=5,
        )
    )
    
    # Create adapter config that references alertmanager
    adapter_config = ExternalAnalysisAdapterConfig(name="alertmanager", enabled=True)
    
    # Build adapters
    adapters = build_external_analysis_adapters([adapter_config], settings=settings)
    
    # Verify adapter was built
    assert "alertmanager" in adapters
    
    # Verify config was wired (adapter should use settings.alertmanager)
    from k8s_diag_agent.external_analysis.alertmanager_adapter import AlertmanagerAdapter
    adapter = adapters["alertmanager"]
    assert isinstance(adapter, AlertmanagerAdapter)
    assert adapter._config.endpoint == "http://custom-alertmanager:9093"
    assert adapter._config.timeout_seconds == 30.0
    assert adapter._config.max_alerts_in_snapshot == 50
    assert adapter._config.max_alerts_in_compact == 5


def test_adapter_builder_with_disabled_config() -> None:
    """Test that disabled Alertmanager config is respected."""
    settings = ExternalAnalysisSettings(
        alertmanager=AlertmanagerConfig(
            enabled=False,
            endpoint="http://disabled:9093",
        )
    )
    
    adapter_config = ExternalAnalysisAdapterConfig(name="alertmanager", enabled=True)
    adapters = build_external_analysis_adapters([adapter_config], settings=settings)
    
    assert "alertmanager" in adapters
    
    # Create request and run adapter
    request = ExternalAnalysisRequest(
        run_id="test-run",
        cluster_label="test-cluster",
        source_artifact=None,
    )
    artifact = adapters["alertmanager"].run(request)
    
    # Should return skipped status because integration is disabled
    assert artifact.status.value == "skipped"
    assert artifact.summary is not None and "disabled" in artifact.summary.lower()


def test_adapter_run_produces_artifacts() -> None:
    """Test that adapter.run() produces snapshot and compact in payload."""
    settings = ExternalAnalysisSettings(
        alertmanager=AlertmanagerConfig(
            enabled=True,  # Enabled but not configured
        )
    )
    
    adapter_config = ExternalAnalysisAdapterConfig(name="alertmanager", enabled=True)
    adapters = build_external_analysis_adapters([adapter_config], settings=settings)
    
    request = ExternalAnalysisRequest(
        run_id="test-run",
        cluster_label="test-cluster",
        source_artifact=None,
    )
    artifact = adapters["alertmanager"].run(request)
    
    # Should have payload with snapshot and compact
    assert artifact.payload is not None
    assert "snapshot" in artifact.payload
    assert "compact" in artifact.payload
    
    # Snapshot should indicate invalid response (no endpoint configured)
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict) and snapshot_data["status"] == "invalid_response"


# --- Status enum values ---

def test_alertmanager_status_values() -> None:
    """Verify all expected status values exist."""
    expected = {"ok", "empty", "timeout", "auth_error", "upstream_error", "disabled", "invalid_response"}
    actual = {s.value for s in AlertmanagerStatus}
    assert actual == expected


def test_status_from_invalid_string_becomes_invalid_response() -> None:
    """Test that unknown status strings map to INVALID_RESPONSE."""
    raw = {
        "status": "unknown_status_value",
        "captured_at": "2024-01-01T00:00:00Z",
        "alert_count": 0,
        "alerts": [],
    }
    snapshot = AlertmanagerSnapshot.from_dict(raw)
    assert snapshot.status == AlertmanagerStatus.INVALID_RESPONSE
