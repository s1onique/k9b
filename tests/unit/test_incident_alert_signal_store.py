"""Unit tests for Alert signal store persistence."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.incident_alert_signal import AlertSignal
from k8s_diag_agent.incident_alert_signal_store import (
    ALERT_SIGNALS_SUBDIR,
    EXTERNAL_ANALYSIS_SUBDIR,
    ALERT_SIGNAL_SCHEMA_VERSION,
    RAW_PAYLOAD_SCHEMA_VERSION,
    AlertSignalArtifact,
    RawPayloadArtifact,
    check_signal_exists,
    read_alert_signal_artifact,
    write_alert_signal_artifact,
    write_raw_payload_artifact,
)


class TestRawPayloadArtifact:
    """Tests for RawPayloadArtifact dataclass."""

    def test_to_dict(self):
        """Test to_dict conversion."""
        received_at = datetime.now(UTC)
        artifact = RawPayloadArtifact(
            schema_version=RAW_PAYLOAD_SCHEMA_VERSION,
            received_at=received_at,
            source_instance="test-instance",
            payload_sha256="abc123",
            payload={"alerts": []},
        )
        result = artifact.to_dict()
        assert result["schema_version"] == RAW_PAYLOAD_SCHEMA_VERSION
        assert result["source_instance"] == "test-instance"
        assert result["payload_sha256"] == "abc123"
        assert result["payload"] == {"alerts": []}

    def test_from_dict(self):
        """Test from_dict conversion."""
        data = {
            "schema_version": RAW_PAYLOAD_SCHEMA_VERSION,
            "received_at": "2024-01-01T00:00:00+00:00",
            "source_instance": "test-instance",
            "payload_sha256": "abc123",
            "payload": {"alerts": [{"labels": {"alertname": "Test"}}]},
        }
        artifact = RawPayloadArtifact.from_dict(data)
        assert artifact.schema_version == RAW_PAYLOAD_SCHEMA_VERSION
        assert artifact.source_instance == "test-instance"
        assert artifact.payload_sha256 == "abc123"
        assert artifact.payload == {"alerts": [{"labels": {"alertname": "Test"}}]}


class TestAlertSignalArtifact:
    """Tests for AlertSignalArtifact dataclass."""

    def test_to_dict(self):
        """Test to_dict conversion."""
        received_at = datetime.now(UTC)
        signal = AlertSignal(
            signal_id="test-signal-id",
            source_type="alertmanager",
            source_instance="test-instance",
            status="firing",
            alertname="TestAlert",
            external_fingerprint="fp123",
            group_key="key123",
            receiver="test-receiver",
            severity="critical",
            labels={"alertname": "TestAlert"},
            annotations={},
            starts_at=received_at,
            ends_at=None,
            received_at=received_at,
            generator_url="http://example.com",
            external_url=None,
            raw_payload_artifact_id=None,
            truncation=None,
        )
        artifact = AlertSignalArtifact(
            schema_version=ALERT_SIGNAL_SCHEMA_VERSION,
            identity="identity-123",
            received_at=received_at,
            signal=signal,
            raw_payload_artifact_id="raw-456",
        )
        result = artifact.to_dict()
        assert result["schema_version"] == ALERT_SIGNAL_SCHEMA_VERSION
        assert result["identity"] == "identity-123"
        assert result["signal"]["alertname"] == "TestAlert"
        assert result["raw_payload_artifact_id"] == "raw-456"

    def test_from_dict(self):
        """Test from_dict conversion."""
        data = {
            "schema_version": ALERT_SIGNAL_SCHEMA_VERSION,
            "identity": "identity-123",
            "received_at": "2024-01-01T00:00:00+00:00",
            "signal": {
                "signal_id": "test-signal-id",
                "source_type": "alertmanager",
                "source_instance": "test-instance",
                "status": "firing",
                "alertname": "TestAlert",
                "external_fingerprint": "fp123",
                "group_key": "key123",
                "receiver": "test-receiver",
                "severity": "critical",
                "labels": {"alertname": "TestAlert"},
                "annotations": {},
                "starts_at": "2024-01-01T00:00:00+00:00",
                "ends_at": None,
                "received_at": "2024-01-01T00:00:00+00:00",
                "generator_url": "http://example.com",
                "external_url": None,
                "raw_payload_artifact_id": None,
                "truncation": None,
            },
            "correlation_hints": {
                "source_instance": "test-instance",
                "alertname": "TestAlert",
                "severity": "critical",
            },
            "raw_payload_artifact_id": "raw-456",
        }
        artifact = AlertSignalArtifact.from_dict(data)
        assert artifact.schema_version == ALERT_SIGNAL_SCHEMA_VERSION
        assert artifact.identity == "identity-123"
        assert artifact.signal is not None
        assert artifact.signal.alertname == "TestAlert"
        assert artifact.correlation_hints is not None
        assert artifact.correlation_hints.alertname == "TestAlert"
        assert artifact.raw_payload_artifact_id == "raw-456"


class TestWriteRawPayloadArtifact:
    """Tests for write_raw_payload_artifact function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_success(self):
        """Test successful write returns result with artifact info."""
        received_at = datetime.now(UTC)
        payload = {"alerts": [{"labels": {"alertname": "Test"}}]}

        result = write_raw_payload_artifact(
            root=self.root,
            payload=payload,
            source_instance="test-instance",
            received_at=received_at,
        )

        assert result.success is True
        assert result.artifact_id is not None
        assert result.artifact_path is not None
        assert result.error is None
        assert result.artifact_path.exists()

    def test_write_stores_payload(self):
        """Test write stores correct payload."""
        payload = {"alerts": [{"labels": {"alertname": "Test"}}]}
        received_at = datetime.now(UTC)

        result = write_raw_payload_artifact(
            root=self.root,
            payload=payload,
            source_instance="test-instance",
            received_at=received_at,
        )

        # Read the artifact
        content = json.loads(result.artifact_path.read_text())
        assert content["payload"] == payload
        assert content["source_instance"] == "test-instance"
        assert content["payload_sha256"]  # Should have a hash

    def test_write_creates_subdirectory(self):
        """Test write creates the subdirectory if needed."""
        payload = {"alerts": []}

        write_result = write_raw_payload_artifact(
            root=self.root,
            payload=payload,
            source_instance="test",
            received_at=datetime.now(UTC),
        )

        assert write_result.success is True
        # Subdirectory should exist
        subdir = self.root / ALERT_SIGNALS_SUBDIR
        assert subdir.exists()
        assert subdir.is_dir()


class TestCheckSignalExists:
    """Tests for check_signal_exists function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_not_exists(self):
        """Test check returns False for non-existent signal."""
        signal = AlertSignal(
            signal_id="test-signal-id",
            source_type="alertmanager",
            source_instance="test-instance",
            status="firing",
            alertname="NonExistentAlert",
            external_fingerprint="fp-none",
            group_key="key-none",
            receiver="test-receiver",
            severity="warning",
            labels={"alertname": "NonExistentAlert"},
            annotations={},
            starts_at=datetime.now(UTC),
            ends_at=None,
            received_at=datetime.now(UTC),
            generator_url=None,
            external_url=None,
            raw_payload_artifact_id=None,
            truncation=None,
        )

        assert check_signal_exists(self.root, signal) is False

    def test_exists_after_write(self):
        """Test check returns True after signal is written."""
        received_at = datetime.now(UTC)
        signal = AlertSignal(
            signal_id="test-signal-id",
            source_type="alertmanager",
            source_instance="test-instance",
            status="firing",
            alertname="ExistingAlert",
            external_fingerprint="fp-exists",
            group_key="key-exists",
            receiver="test-receiver",
            severity="critical",
            labels={"alertname": "ExistingAlert"},
            annotations={},
            starts_at=received_at,
            ends_at=None,
            received_at=received_at,
            generator_url=None,
            external_url=None,
            raw_payload_artifact_id=None,
            truncation=None,
        )

        # Write the signal
        write_alert_signal_artifact(
            root=self.root,
            signal=signal,
            received_at=received_at,
        )

        # Now check should return True
        assert check_signal_exists(self.root, signal) is True


class TestWriteAlertSignalArtifact:
    """Tests for write_alert_signal_artifact function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_signal(
        self,
        alertname: str = "TestAlert",
        severity: str = "critical",
    ) -> AlertSignal:
        """Helper to create a test signal."""
        received_at = datetime.now(UTC)
        return AlertSignal(
            signal_id="test-signal-id",
            source_type="alertmanager",
            source_instance="test-instance",
            status="firing",
            alertname=alertname,
            external_fingerprint=f"fp-{alertname}",
            group_key=f"key-{alertname}",
            receiver="test-receiver",
            severity=severity,
            labels={"alertname": alertname, "severity": severity},
            annotations={"summary": f"Test summary for {alertname}"},
            starts_at=received_at,
            ends_at=None,
            received_at=received_at,
            generator_url="http://alertmanager.example.com",
            external_url="http://alertmanager.example.com",
            raw_payload_artifact_id=None,
            truncation=None,
        )

    def test_write_success(self):
        """Test successful write returns success result."""
        received_at = datetime.now(UTC)
        signal = self._make_signal()

        result = write_alert_signal_artifact(
            root=self.root,
            signal=signal,
            received_at=received_at,
        )

        assert result.success is True
        assert result.identity is not None
        assert result.is_duplicate is False
        assert result.artifact_path is not None
        assert result.artifact_path.exists()

    def test_write_stores_signal(self):
        """Test write stores correct signal data."""
        received_at = datetime.now(UTC)
        signal = self._make_signal(alertname="StoredAlert")

        result = write_alert_signal_artifact(
            root=self.root,
            signal=signal,
            received_at=received_at,
        )

        # Read and verify
        content = json.loads(result.artifact_path.read_text())
        assert content["signal"]["alertname"] == "StoredAlert"
        assert content["signal"]["severity"] == "critical"
        assert content["correlation_hints"]["alertname"] == "StoredAlert"

    def test_write_idempotent(self):
        """Test duplicate write returns is_duplicate=True."""
        received_at = datetime.now(UTC)
        signal = self._make_signal(alertname="DuplicateAlert")

        # First write
        result1 = write_alert_signal_artifact(
            root=self.root,
            signal=signal,
            received_at=received_at,
        )
        assert result1.success is True
        assert result1.is_duplicate is False
        original_path = result1.artifact_path

        # Second write (same signal)
        result2 = write_alert_signal_artifact(
            root=self.root,
            signal=signal,
            received_at=received_at,
        )
        assert result2.success is True
        assert result2.is_duplicate is True
        assert result2.artifact_path == original_path

        # Only one file should exist
        files = list((self.root / ALERT_SIGNALS_SUBDIR).glob("*.json"))
        assert len(files) == 1

    def test_different_signals_different_files(self):
        """Test different signals create different files."""
        received_at = datetime.now(UTC)
        signal1 = self._make_signal(alertname="AlertOne", severity="critical")
        signal2 = self._make_signal(alertname="AlertTwo", severity="warning")

        result1 = write_alert_signal_artifact(
            root=self.root,
            signal=signal1,
            received_at=received_at,
        )
        result2 = write_alert_signal_artifact(
            root=self.root,
            signal=signal2,
            received_at=received_at,
        )

        assert result1.artifact_path != result2.artifact_path
        assert result1.artifact_path.exists()
        assert result2.artifact_path.exists()


class TestReadAlertSignalArtifact:
    """Tests for read_alert_signal_artifact function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_signal(self, alertname: str = "TestAlert") -> AlertSignal:
        """Helper to create a test signal."""
        received_at = datetime.now(UTC)
        return AlertSignal(
            signal_id="test-signal-id",
            source_type="alertmanager",
            source_instance="test-instance",
            status="firing",
            alertname=alertname,
            external_fingerprint=f"fp-{alertname}",
            group_key=f"key-{alertname}",
            receiver="test-receiver",
            severity="critical",
            labels={"alertname": alertname},
            annotations={},
            starts_at=received_at,
            ends_at=None,
            received_at=received_at,
            generator_url=None,
            external_url=None,
            raw_payload_artifact_id=None,
            truncation=None,
        )

    def test_read_existing(self):
        """Test reading an existing artifact returns correct data."""
        received_at = datetime.now(UTC)
        signal = self._make_signal(alertname="ReadAlert")

        # Write first
        write_alert_signal_artifact(
            root=self.root,
            signal=signal,
            received_at=received_at,
        )

        # Read back
        identity = "test-identity"  # We need to compute the actual identity
        artifact = read_alert_signal_artifact(self.root, identity)

        # The artifact doesn't exist with wrong identity
        assert artifact is None

        # Write and read with known identity
        result = write_alert_signal_artifact(
            root=self.root,
            signal=signal,
            received_at=received_at,
        )
        artifact = read_alert_signal_artifact(self.root, result.identity)

        assert artifact is not None
        assert artifact.signal is not None
        assert artifact.signal.alertname == "ReadAlert"

    def test_read_nonexistent(self):
        """Test reading non-existent artifact returns None."""
        artifact = read_alert_signal_artifact(self.root, "nonexistent-identity")
        assert artifact is None
