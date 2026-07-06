"""Unit tests for alert signal reader.

Tests cover:
- Reader loads alert-signal artifacts
- Reader ignores raw webhook artifacts
- Reader skips malformed artifacts safely
- Schema version validation
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.incident_alert_signal_reader import (
    get_alert_signals_dir,
    read_alert_signal_by_identity,
    scan_alert_signal_artifacts,
)
from k8s_diag_agent.incident_alert_signal_store import ALERT_SIGNAL_SCHEMA_VERSION


class TestGetAlertSignalsDir:
    """Tests for get_alert_signals_dir function."""

    def test_returns_correct_path(self):
        """Test that function returns the correct alert signals directory."""
        runs_dir = Path("/tmp/test_runs")
        signals_dir = get_alert_signals_dir(runs_dir)
        assert signals_dir == Path("/tmp/test_runs/external-analysis/alert-signals")


class TestScanAlertSignalArtifacts:
    """Tests for scan_alert_signal_artifacts function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.runs_dir = Path(self.temp_dir)
        self.signals_dir = self.runs_dir / "external-analysis" / "alert-signals"
        self.signals_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_signal_artifact(
        self,
        identity: str,
        alertname: str = "TestAlert",
        status: str = "firing",
    ) -> dict:
        """Helper to create a signal artifact."""
        return {
            "schema_version": ALERT_SIGNAL_SCHEMA_VERSION,
            "identity": identity,
            "received_at": datetime.now(UTC).isoformat(),
            "signal": {
                "signal_id": f"sig-{identity}",
                "source_type": "alertmanager",
                "source_instance": "test-instance",
                "status": status,
                "alertname": alertname,
                "external_fingerprint": f"fp-{identity}",
                "group_key": f"key-{identity}",
                "receiver": "test-receiver",
                "severity": "critical",
                "labels": {"alertname": alertname},
                "annotations": {},
                "starts_at": datetime.now(UTC).isoformat(),
                "ends_at": None,
                "received_at": datetime.now(UTC).isoformat(),
                "generator_url": None,
                "external_url": None,
                "raw_payload_artifact_id": None,
                "truncation": None,
            },
            "correlation_hints": {
                "source_instance": "test-instance",
                "alertname": alertname,
                "severity": "critical",
            },
            "raw_payload_artifact_id": None,
        }

    def test_returns_empty_for_missing_directory(self):
        """Test that empty tuple is returned when directory doesn't exist."""
        result = scan_alert_signal_artifacts(Path("/nonexistent"))
        assert result == ()

    def test_loads_alert_signal_artifacts(self):
        """Test that reader loads alert-signal artifacts."""
        # Write a signal artifact
        artifact = self._make_signal_artifact("test-123")
        artifact_path = self.signals_dir / "alert-signal-test-123.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        # Scan
        result = scan_alert_signal_artifacts(self.runs_dir)

        assert len(result) == 1
        assert result[0].identity == "test-123"
        assert result[0].signal is not None
        assert result[0].signal.alertname == "TestAlert"

    def test_ignores_raw_webhook_artifacts(self):
        """Test that reader ignores alertmanager-raw-*.json artifacts."""
        # Write a raw artifact
        raw_path = self.signals_dir / "alertmanager-raw-abc123.json"
        raw_path.write_text(json.dumps({"schema_version": "test", "payload": {}}), encoding="utf-8")

        # Write a signal artifact
        artifact = self._make_signal_artifact("test-456")
        artifact_path = self.signals_dir / "alert-signal-test-456.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        # Scan
        result = scan_alert_signal_artifacts(self.runs_dir)

        assert len(result) == 1
        assert result[0].identity == "test-456"

    def test_skips_malformed_artifacts(self):
        """Test that reader skips malformed artifacts safely."""
        # Write a malformed artifact (invalid JSON)
        malformed_path = self.signals_dir / "alert-signal-malformed.json"
        malformed_path.write_text("not valid json {{{", encoding="utf-8")

        # Write a valid signal artifact
        artifact = self._make_signal_artifact("valid-123")
        artifact_path = self.signals_dir / "alert-signal-valid-123.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        # Scan
        result = scan_alert_signal_artifacts(self.runs_dir)

        # Should only return the valid artifact
        assert len(result) == 1
        assert result[0].identity == "valid-123"

    def test_skips_wrong_schema_version(self):
        """Test that reader skips artifacts with wrong schema version."""
        # Write artifact with wrong schema version
        artifact = self._make_signal_artifact("wrong-schema")
        artifact["schema_version"] = "wrong.version"
        artifact_path = self.signals_dir / "alert-signal-wrong-schema.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        # Write a valid artifact
        valid_artifact = self._make_signal_artifact("valid-123")
        valid_path = self.signals_dir / "alert-signal-valid-123.json"
        valid_path.write_text(json.dumps(valid_artifact), encoding="utf-8")

        # Scan
        result = scan_alert_signal_artifacts(self.runs_dir)

        # Should only return the valid artifact
        assert len(result) == 1
        assert result[0].identity == "valid-123"

    def test_returns_sorted_by_identity(self):
        """Test that results are sorted by identity."""
        # Write multiple artifacts
        for identity in ["zzz-999", "aaa-111", "mmm-555"]:
            artifact = self._make_signal_artifact(identity)
            artifact_path = self.signals_dir / f"alert-signal-{identity}.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        # Scan
        result = scan_alert_signal_artifacts(self.runs_dir)

        # Should be sorted
        identities = [a.identity for a in result]
        assert identities == ["aaa-111", "mmm-555", "zzz-999"]

    def test_respects_max_count(self):
        """Test that scanner respects max_count limit."""
        # Write multiple artifacts
        for i in range(10):
            artifact = self._make_signal_artifact(f"test-{i}")
            artifact_path = self.signals_dir / f"alert-signal-test-{i}.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        # Scan with max_count=3
        result = scan_alert_signal_artifacts(self.runs_dir, max_count=3)

        assert len(result) == 3


class TestReadAlertSignalByIdentity:
    """Tests for read_alert_signal_by_identity function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.runs_dir = Path(self.temp_dir)
        self.signals_dir = self.runs_dir / "external-analysis" / "alert-signals"
        self.signals_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_signal_artifact(self, identity: str) -> dict:
        """Helper to create a signal artifact."""
        return {
            "schema_version": ALERT_SIGNAL_SCHEMA_VERSION,
            "identity": identity,
            "received_at": datetime.now(UTC).isoformat(),
            "signal": {
                "signal_id": f"sig-{identity}",
                "source_type": "alertmanager",
                "source_instance": "test-instance",
                "status": "firing",
                "alertname": f"Alert-{identity}",
                "external_fingerprint": f"fp-{identity}",
                "group_key": f"key-{identity}",
                "receiver": "test-receiver",
                "severity": "critical",
                "labels": {"alertname": f"Alert-{identity}"},
                "annotations": {},
                "starts_at": datetime.now(UTC).isoformat(),
                "ends_at": None,
                "received_at": datetime.now(UTC).isoformat(),
                "generator_url": None,
                "external_url": None,
                "raw_payload_artifact_id": None,
                "truncation": None,
            },
            "correlation_hints": None,
            "raw_payload_artifact_id": None,
        }

    def test_read_existing_artifact(self):
        """Test reading an existing artifact by identity."""
        identity = "test-123"
        artifact = self._make_signal_artifact(identity)
        artifact_path = self.signals_dir / f"alert-signal-{identity}.json"
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

        result = read_alert_signal_by_identity(self.runs_dir, identity)

        assert result is not None
        assert result.identity == identity
        assert result.signal is not None
        assert result.signal.alertname == f"Alert-{identity}"

    def test_read_nonexistent_artifact(self):
        """Test reading a non-existent artifact returns None."""
        result = read_alert_signal_by_identity(self.runs_dir, "nonexistent-identity")
        assert result is None
