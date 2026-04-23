"""Unit tests for Alertmanager integration: config, snapshot, compact summarization, and artifact persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from k8s_diag_agent.external_analysis.adapter import (
    AuthError,
    ExternalAnalysisAdapterConfig,
    ExternalAnalysisRequest,
    InvalidResponseError,
    TimeoutError,
    UpstreamError,
    build_external_analysis_adapters,
)
from k8s_diag_agent.external_analysis.alertmanager_adapter import AlertmanagerAdapter
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
from k8s_diag_agent.external_analysis.artifact import ExternalAnalysisStatus
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


# --- State extraction precedence tests ---

def _make_alert_with_state(alert_raw_state: str | None = None, status_mapping: dict | str | None = None, labels_state: str | None = None) -> dict[str, Any]:
    """Create a test alert with specific state sources.
    
    Args:
        alert_raw_state: Value for top-level "state" field
        status_mapping: Value for "status" field (can be dict with "state" key, or string)
        labels_state: Value for labels["state"] field
    """
    alert: dict[str, Any] = {
        "labels": {
            "alertname": "TestState",
            "severity": "warning",
        },
        "annotations": {"summary": "Test alert"},
    }
    if labels_state is not None:
        alert["labels"]["state"] = labels_state
    if alert_raw_state is not None:
        alert["state"] = alert_raw_state
    if status_mapping is not None:
        alert["status"] = status_mapping
    return alert


def test_state_extraction_precedence_nested_status_state() -> None:
    """Precedence 1: alert_raw['status']['state'] if status is a mapping."""
    alert = _make_alert_with_state(
        alert_raw_state="top-level-state",
        status_mapping={"state": "nested-state", "silencedBy": "abc"},
        labels_state="labels-state",
    )
    raw = {"data": {"alerts": [alert]}}
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert len(snapshot.alerts) == 1
    # Nested status.state should win
    assert snapshot.alerts[0].state == "nested-state"


def test_state_extraction_precedence_string_status() -> None:
    """Precedence 2: alert_raw['status'] if it is a string."""
    alert = _make_alert_with_state(
        alert_raw_state="top-level-state",
        status_mapping="string-status-value",
        labels_state="labels-state",
    )
    raw = {"data": {"alerts": [alert]}}
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert len(snapshot.alerts) == 1
    # String status should win over top-level state
    assert snapshot.alerts[0].state == "string-status-value"


def test_state_extraction_precedence_top_level_state() -> None:
    """Precedence 3: alert_raw['state'] if present."""
    alert = _make_alert_with_state(
        alert_raw_state="top-level-state",
        labels_state="labels-state",
    )
    # No status field
    alert.pop("status", None)
    raw = {"data": {"alerts": [alert]}}
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert len(snapshot.alerts) == 1
    # Top-level state should win over labels state
    assert snapshot.alerts[0].state == "top-level-state"


def test_state_extraction_precedence_labels_state() -> None:
    """Precedence 4: labels_raw['state'] as fallback."""
    alert = _make_alert_with_state(labels_state="labels-state")
    # No status, no top-level state
    alert.pop("status", None)
    alert.pop("state", None)
    raw = {"data": {"alerts": [alert]}}
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert len(snapshot.alerts) == 1
    # Labels state should be used
    assert snapshot.alerts[0].state == "labels-state"


def test_state_extraction_precedence_default_inactive() -> None:
    """Precedence 5: 'inactive' as deterministic default when no state found."""
    # Alert with no state fields at all
    alert = {
        "labels": {
            "alertname": "NoState",
            "severity": "info",
        },
        "annotations": {"summary": "No state here"},
    }
    raw = {"data": {"alerts": [alert]}}
    snapshot = normalize_alertmanager_payload(raw)
    assert snapshot.status == AlertmanagerStatus.OK
    assert len(snapshot.alerts) == 1
    # Default to "inactive"
    assert snapshot.alerts[0].state == "inactive"


def test_state_extraction_precedence_with_truncation() -> None:
    """Test that long state values are truncated properly."""
    long_state = "active" * 100  # Very long string
    alert = _make_alert_with_state(alert_raw_state=long_state)
    raw = {"data": {"alerts": [alert]}}
    snapshot = normalize_alertmanager_payload(raw, config_max_string_length=50)
    assert snapshot.status == AlertmanagerStatus.OK
    assert len(snapshot.alerts) == 1
    # State should be truncated
    state = snapshot.alerts[0].state
    assert len(state) == 50
    assert state.endswith("...")


# --- Error snapshot status mapping tests ---

def test_error_snapshot_timeout_status() -> None:
    """Test that timeout errors create TIMEOUT status."""
    snapshot = create_error_snapshot(
        AlertmanagerStatus.TIMEOUT,
        "Connection timed out after 30s",
        source="http://alertmanager:9093",
    )
    assert snapshot.status == AlertmanagerStatus.TIMEOUT
    assert snapshot.alert_count == 0
    assert snapshot.errors == ("Connection timed out after 30s",)
    assert snapshot.source == "http://alertmanager:9093"
    assert snapshot.truncated is False


def test_error_snapshot_auth_error_status() -> None:
    """Test that auth errors create AUTH_ERROR status."""
    snapshot = create_error_snapshot(
        AlertmanagerStatus.AUTH_ERROR,
        "401 Unauthorized: Invalid bearer token",
    )
    assert snapshot.status == AlertmanagerStatus.AUTH_ERROR
    assert snapshot.alert_count == 0
    assert "Unauthorized" in snapshot.errors[0]


def test_error_snapshot_upstream_error_status() -> None:
    """Test that upstream errors create UPSTREAM_ERROR status."""
    snapshot = create_error_snapshot(
        AlertmanagerStatus.UPSTREAM_ERROR,
        "Alertmanager returned 503 Service Unavailable",
    )
    assert snapshot.status == AlertmanagerStatus.UPSTREAM_ERROR
    assert snapshot.alert_count == 0


def test_error_snapshot_invalid_response_status() -> None:
    """Test that invalid response errors create INVALID_RESPONSE status."""
    snapshot = create_error_snapshot(
        AlertmanagerStatus.INVALID_RESPONSE,
        "Failed to parse JSON response",
    )
    assert snapshot.status == AlertmanagerStatus.INVALID_RESPONSE
    assert snapshot.alert_count == 0


def test_error_snapshot_disabled_status() -> None:
    """Test that disabled integration creates DISABLED status."""
    snapshot = create_error_snapshot(
        AlertmanagerStatus.DISABLED,
        "Alertmanager integration is disabled in config",
    )
    assert snapshot.status == AlertmanagerStatus.DISABLED
    assert snapshot.alert_count == 0
    assert "disabled" in snapshot.errors[0].lower()


def test_error_snapshot_status_roundtrip() -> None:
    """Test that error snapshots serialize/deserialize correctly."""
    original = create_error_snapshot(
        AlertmanagerStatus.TIMEOUT,
        "Test timeout error",
        source="http://test:9093",
    )
    serialized = original.to_dict()
    restored = AlertmanagerSnapshot.from_dict(serialized)
    assert restored.status == original.status
    assert restored.errors == original.errors
    assert restored.source == original.source
    assert restored.alert_count == original.alert_count


# --- Status enum coverage ---

def test_all_error_statuses_have_corresponding_error_snapshots() -> None:
    """Verify each error status can create an error snapshot."""
    error_statuses = [
        AlertmanagerStatus.TIMEOUT,
        AlertmanagerStatus.AUTH_ERROR,
        AlertmanagerStatus.UPSTREAM_ERROR,
        AlertmanagerStatus.INVALID_RESPONSE,
        AlertmanagerStatus.DISABLED,
    ]
    for status in error_statuses:
        snapshot = create_error_snapshot(status, f"Test error for {status.value}")
        assert snapshot.status == status
        assert len(snapshot.errors) == 1
        assert snapshot.alert_count == 0


# --- Adapter-level exception/status mapping tests ---


def _make_request() -> ExternalAnalysisRequest:
    return ExternalAnalysisRequest(
        run_id="test-run",
        cluster_label="test-cluster",
        source_artifact=None,
    )


def test_adapter_maps_timeout_exception_to_timeout_status() -> None:
    """Test that TimeoutError from _fetch_alerts maps to TIMEOUT status."""
    config = AlertmanagerConfig(
        enabled=True,
        endpoint="http://localhost:9093",
    )
    adapter = AlertmanagerAdapter(config=config)
    
    with patch.object(adapter, "_fetch_alerts", side_effect=TimeoutError("Connection timed out")):
        artifact = adapter.run(_make_request())
    
    assert artifact.status == ExternalAnalysisStatus.FAILED
    assert artifact.payload is not None
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict) and snapshot_data["status"] == "timeout"
    assert artifact.error_summary is not None and "timed out" in artifact.error_summary.lower()


def test_adapter_maps_auth_error_exception_to_auth_error_status() -> None:
    """Test that AuthError from _fetch_alerts maps to AUTH_ERROR status."""
    config = AlertmanagerConfig(
        enabled=True,
        endpoint="http://localhost:9093",
    )
    adapter = AlertmanagerAdapter(config=config)
    
    with patch.object(adapter, "_fetch_alerts", side_effect=AuthError("401 Unauthorized")):
        artifact = adapter.run(_make_request())
    
    assert artifact.status == ExternalAnalysisStatus.FAILED
    assert artifact.payload is not None
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict) and snapshot_data["status"] == "auth_error"
    assert artifact.error_summary is not None and "auth" in artifact.error_summary.lower()


def test_adapter_maps_upstream_error_exception_to_upstream_error_status() -> None:
    """Test that UpstreamError from _fetch_alerts maps to UPSTREAM_ERROR status."""
    config = AlertmanagerConfig(
        enabled=True,
        endpoint="http://localhost:9093",
    )
    adapter = AlertmanagerAdapter(config=config)
    
    with patch.object(adapter, "_fetch_alerts", side_effect=UpstreamError("503 Service Unavailable")):
        artifact = adapter.run(_make_request())
    
    assert artifact.status == ExternalAnalysisStatus.FAILED
    assert artifact.payload is not None
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict) and snapshot_data["status"] == "upstream_error"
    assert artifact.error_summary is not None and "503" in artifact.error_summary


def test_adapter_maps_url_error_to_upstream_error() -> None:
    """Test that URLError (connection refused) maps to UPSTREAM_ERROR, not INVALID_RESPONSE."""
    config = AlertmanagerConfig(
        enabled=True,
        endpoint="http://localhost:9093",
    )
    adapter = AlertmanagerAdapter(config=config)
    
    with patch.object(adapter, "_fetch_alerts", side_effect=UpstreamError("Alertmanager unreachable: Connection refused")):
        artifact = adapter.run(_make_request())
    
    assert artifact.status == ExternalAnalysisStatus.FAILED
    assert artifact.payload is not None
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict) and snapshot_data["status"] == "upstream_error"
    # Ensure it's NOT mapped as invalid_response
    assert artifact.error_summary is not None and "invalid" not in artifact.error_summary.lower()


def test_adapter_maps_invalid_response_error_to_invalid_response_status() -> None:
    """Test that InvalidResponseError from _fetch_alerts maps to INVALID_RESPONSE status."""
    config = AlertmanagerConfig(
        enabled=True,
        endpoint="http://localhost:9093",
    )
    adapter = AlertmanagerAdapter(config=config)
    
    with patch.object(adapter, "_fetch_alerts", side_effect=InvalidResponseError("Malformed JSON")):
        artifact = adapter.run(_make_request())
    
    assert artifact.status == ExternalAnalysisStatus.FAILED
    assert artifact.payload is not None
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict) and snapshot_data["status"] == "invalid_response"


def test_adapter_maps_disabled_to_skipped() -> None:
    """Test that disabled adapter produces SKIPPED status."""
    config = AlertmanagerConfig(
        enabled=False,
        endpoint="http://localhost:9093",
    )
    adapter = AlertmanagerAdapter(config=config)
    
    artifact = adapter.run(_make_request())
    
    assert artifact.status == ExternalAnalysisStatus.SKIPPED
    assert artifact.payload is not None
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict) and snapshot_data["status"] == "disabled"


def test_adapter_maps_success_to_success() -> None:
    """Test that successful fetch produces SUCCESS status."""
    config = AlertmanagerConfig(
        enabled=True,
        endpoint="http://localhost:9093",
    )
    adapter = AlertmanagerAdapter(config=config)
    
    mock_response = [{"labels": {"alertname": "Test", "severity": "warning"}, "state": "active"}]
    with patch.object(adapter, "_fetch_alerts", return_value=mock_response):
        artifact = adapter.run(_make_request())
    
    assert artifact.status == ExternalAnalysisStatus.SUCCESS
    assert artifact.payload is not None
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict)
    assert snapshot_data["status"] == "ok"
    assert snapshot_data["alert_count"] == 1


def test_adapter_maps_empty_response_to_success() -> None:
    """Test that empty alert list produces SUCCESS status (empty is not an error)."""
    config = AlertmanagerConfig(
        enabled=True,
        endpoint="http://localhost:9093",
    )
    adapter = AlertmanagerAdapter(config=config)
    
    with patch.object(adapter, "_fetch_alerts", return_value=[]):
        artifact = adapter.run(_make_request())
    
    assert artifact.status == ExternalAnalysisStatus.SUCCESS
    assert artifact.payload is not None
    snapshot_data = artifact.payload["snapshot"]
    assert isinstance(snapshot_data, dict) and snapshot_data["status"] == "empty"


# --- Real persistence seam test ---

def test_real_run_scoped_artifact_persistence_path(tmp_path: Path) -> None:
    """Test that adapter produces artifacts that can be written and read via real persistence functions.
    
    This is an integration-style test that exercises the actual persistence seam:
    1. Adapter produces snapshot + compact
    2. Snapshot and compact are written to disk via alertmanager_artifact functions
    3. Artifacts are read back and verified
    """
    from k8s_diag_agent.external_analysis.alertmanager_adapter import create_alertmanager_artifact
    from k8s_diag_agent.external_analysis.alertmanager_snapshot import normalize_alertmanager_payload, snapshot_to_compact
    
    # Step 1: Create a realistic snapshot via normalization
    raw_alerts = {
        "data": {
            "alerts": [
                {
                    "labels": {
                        "alertname": "HighCPU",
                        "severity": "critical",
                        "cluster": "prod",
                        "namespace": "monitoring",
                    },
                    "annotations": {"summary": "High CPU usage"},
                    "state": "active",
                    "startsAt": "2024-01-01T00:00:00Z",
                },
                {
                    "labels": {
                        "alertname": "DiskFull",
                        "severity": "warning",
                        "cluster": "prod",
                        "namespace": "storage",
                    },
                    "annotations": {"summary": "Disk is filling up"},
                    "state": "suppressed",
                    "startsAt": "2024-01-02T00:00:00Z",
                },
            ]
        }
    }
    snapshot = normalize_alertmanager_payload(raw_alerts)
    compact = snapshot_to_compact(snapshot, max_alerts=20)
    
    # Step 2: Create artifact via adapter
    request = ExternalAnalysisRequest(
        run_id="persistence-test-run",
        cluster_label="prod-cluster",
        source_artifact=None,
    )
    artifact = create_alertmanager_artifact(request, snapshot, compact)
    
    # Verify artifact structure
    assert artifact.run_id == "persistence-test-run"
    assert artifact.cluster_label == "prod-cluster"
    assert artifact.provider == "alertmanager"
    assert artifact.payload is not None
    assert "snapshot" in artifact.payload
    assert "compact" in artifact.payload
    
    # Step 3: Write snapshot and compact to disk
    run_id = artifact.run_id
    snap_path = write_alertmanager_snapshot(tmp_path, snapshot, run_id)
    compact_path = write_alertmanager_compact(tmp_path, compact, run_id)
    
    assert snap_path.exists(), f"Snapshot not written to {snap_path}"
    assert compact_path.exists(), f"Compact not written to {compact_path}"
    
    # Step 4: Read back and verify
    loaded_snapshot = read_alertmanager_snapshot(snap_path)
    loaded_compact = read_alertmanager_compact(compact_path)
    
    assert loaded_snapshot is not None
    assert loaded_compact is not None
    
    # Verify snapshot contents
    assert loaded_snapshot.status == snapshot.status
    assert loaded_snapshot.alert_count == snapshot.alert_count
    assert len(loaded_snapshot.alerts) == len(snapshot.alerts)
    
    # Verify compact contents
    assert loaded_compact.status == compact.status
    assert loaded_compact.alert_count == compact.alert_count
    assert loaded_compact.severity_counts == compact.severity_counts
    assert loaded_compact.state_counts == compact.state_counts
    
    # Step 5: Verify the artifact existence check works
    snap_exists, compact_exists = alertmanager_artifacts_exist(tmp_path, run_id)
    assert snap_exists is True
    assert compact_exists is True


def test_error_snapshot_persistence_and_roundtrip(tmp_path: Path) -> None:
    """Test that error snapshots can be written and read via real persistence functions."""
    from k8s_diag_agent.external_analysis.alertmanager_adapter import create_alertmanager_artifact
    from k8s_diag_agent.external_analysis.alertmanager_snapshot import create_error_snapshot
    
    # Create an upstream error snapshot
    snapshot = create_error_snapshot(
        AlertmanagerStatus.UPSTREAM_ERROR,
        "Alertmanager returned 503: Service Unavailable",
        source="http://alertmanager:9093",
    )
    compact = snapshot_to_compact(snapshot, max_alerts=20)
    
    request = ExternalAnalysisRequest(
        run_id="error-test-run",
        cluster_label="prod-cluster",
        source_artifact=None,
    )
    artifact = create_alertmanager_artifact(request, snapshot, compact)
    
    # Write and read back
    run_id = artifact.run_id
    snap_path = write_alertmanager_snapshot(tmp_path, snapshot, run_id)
    loaded = read_alertmanager_snapshot(snap_path)
    
    assert loaded is not None
    assert loaded.status == AlertmanagerStatus.UPSTREAM_ERROR
    assert len(loaded.alerts) == 0
    assert loaded.alert_count == 0
    assert "503" in loaded.errors[0]


# --- Alertmanager artifact immutability tests ---

def test_alertmanager_snapshot_write_succeeds_normally(tmp_path: Path) -> None:
    """Writing an Alertmanager snapshot artifact to a new path succeeds."""
    raw = {"data": {"alerts": [_make_alert("ImmutTest", "warning")]}}
    snapshot = normalize_alertmanager_payload(raw)
    run_id = "immut-snapshot-test"

    path = write_alertmanager_snapshot(tmp_path, snapshot, run_id)

    assert path.exists()
    assert f"{run_id}-alertmanager-snapshot.json" == path.name


def test_alertmanager_snapshot_immutability_rejects_overwrite(tmp_path: Path) -> None:
    """Attempting to write the same immutable Alertmanager snapshot path again raises FileExistsError.
    
    Alertmanager snapshot artifacts are immutable and cannot be overwritten.
    This test demonstrates the immutability contract enforced by write_alertmanager_snapshot().
    """
    raw = {"data": {"alerts": [_make_alert("OverwriteTest", "warning")]}}
    snapshot = normalize_alertmanager_payload(raw)
    run_id = "immut-snapshot-overwrite-test"

    # First write succeeds
    path1 = write_alertmanager_snapshot(tmp_path, snapshot, run_id)
    assert path1.exists()

    # Second write to same path raises FileExistsError
    with pytest.raises(FileExistsError) as exc_info:
        write_alertmanager_snapshot(tmp_path, snapshot, run_id)
    
    assert "immutability contract violated" in str(exc_info.value)
    assert "alertmanager-snapshot" in str(exc_info.value)


def test_alertmanager_compact_write_succeeds_normally(tmp_path: Path) -> None:
    """Writing an Alertmanager compact artifact to a new path succeeds."""
    raw = {"data": {"alerts": [_make_alert("CompactImmutTest", "info")]}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    run_id = "immut-compact-test"

    path = write_alertmanager_compact(tmp_path, compact, run_id)

    assert path.exists()
    assert f"{run_id}-alertmanager-compact.json" == path.name


def test_alertmanager_compact_immutability_rejects_overwrite(tmp_path: Path) -> None:
    """Attempting to write the same immutable Alertmanager compact path again raises FileExistsError.
    
    Alertmanager compact artifacts are immutable and cannot be overwritten.
    This test demonstrates the immutability contract enforced by write_alertmanager_compact().
    """
    raw = {"data": {"alerts": [_make_alert("CompactOverwriteTest", "info")]}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    run_id = "immut-compact-overwrite-test"

    # First write succeeds
    path1 = write_alertmanager_compact(tmp_path, compact, run_id)
    assert path1.exists()

    # Second write to same path raises FileExistsError
    with pytest.raises(FileExistsError) as exc_info:
        write_alertmanager_compact(tmp_path, compact, run_id)
    
    assert "immutability contract violated" in str(exc_info.value)
    assert "alertmanager-compact" in str(exc_info.value)


def test_alertmanager_artifacts_both_immutable(tmp_path: Path) -> None:
    """Both snapshot and compact artifacts are immutable within the same run."""
    raw = {"data": {"alerts": [_make_alert("BothImmut", "critical")]}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    run_id = "immut-both-test"

    # Write both artifacts
    snap_path, compact_path = write_alertmanager_artifacts(tmp_path, run_id, snapshot, compact)
    assert snap_path.exists()
    assert compact_path.exists()

    # Attempting to overwrite snapshot raises FileExistsError
    with pytest.raises(FileExistsError):
        write_alertmanager_snapshot(tmp_path, snapshot, run_id)

    # Attempting to overwrite compact raises FileExistsError
    with pytest.raises(FileExistsError):
        write_alertmanager_compact(tmp_path, compact, run_id)


def test_alertmanager_distinct_run_ids_write_successfully(tmp_path: Path) -> None:
    """Distinct Alertmanager artifacts with different run_ids write successfully.
    
    Immutability doesn't block normal operation - different artifacts with different
    run_ids should write without conflict.
    """
    raw = {"data": {"alerts": [_make_alert("DistinctRun", "warning")]}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)

    run_id_1 = "immut-distinct-run-1"
    run_id_2 = "immut-distinct-run-2"

    # Write artifacts for first run
    snap_path1, compact_path1 = write_alertmanager_artifacts(
        tmp_path, run_id_1, snapshot, compact
    )
    assert snap_path1.exists()
    assert compact_path1.exists()

    # Write artifacts for second run (different paths)
    snap_path2, compact_path2 = write_alertmanager_artifacts(
        tmp_path, run_id_2, snapshot, compact
    )
    assert snap_path2.exists()
    assert compact_path2.exists()

    # Paths should be different
    assert snap_path1 != snap_path2
    assert compact_path1 != compact_path2


def test_alertmanager_artifacts_backward_compatible_flow(tmp_path: Path) -> None:
    """Normal Alertmanager flows remain backward compatible.
    
    This test verifies that the immutability guard doesn't break
    the standard Alertmanager artifact writing pattern where each run
    produces unique snapshot and compact artifacts.
    """
    raw = {"data": {"alerts": [_make_alert("BackwardCompat", "error")]}}
    snapshot = normalize_alertmanager_payload(raw)
    compact = snapshot_to_compact(snapshot)
    
    run_id = "backward-compat-run"
    
    # Write the standard pair of artifacts
    snap_path, compact_path = write_alertmanager_artifacts(
        tmp_path, run_id, snapshot, compact
    )
    
    assert snap_path.exists()
    assert compact_path.exists()
    
    # Read back and verify contents
    loaded_snap = read_alertmanager_snapshot(snap_path)
    loaded_compact = read_alertmanager_compact(compact_path)
    
    assert loaded_snap is not None
    assert loaded_compact is not None
    assert loaded_snap.status == snapshot.status
    assert loaded_compact.status == compact.status
