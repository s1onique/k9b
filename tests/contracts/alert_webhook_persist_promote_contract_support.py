"""Support module for alert webhook persist/promote contract tests.

Shared builders, helpers, and assertion utilities extracted from
test_alert_webhook_persist_promote_contract.py to reduce file sizes.

This module is NOT a test file (does not start with test_).
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from k8s_diag_agent.collect.incident_lifecycle import IncidentStatus
from k8s_diag_agent.collect.incident_store import IncidentStore
from k8s_diag_agent.incident_alert_signal_store import (
    ALERT_SIGNAL_SCHEMA_VERSION,
    ALERT_SIGNALS_SUBDIR,
    EXTERNAL_ANALYSIS_SUBDIR,
)
from k8s_diag_agent.incident_alertmanager_webhook_config import (
    AlertmanagerWebhookConfig,
)

# =============================================================================
# Directory helpers
# =============================================================================


def get_signals_dir(root: Path) -> Path:
    """Get the alert signals directory path."""
    result: Path = root / EXTERNAL_ANALYSIS_SUBDIR / ALERT_SIGNALS_SUBDIR
    return result


# =============================================================================
# Artifact helpers
# =============================================================================


def assert_any_alert_signal_artifact_exists(root: Path) -> Path:
    """Assert any alert-signal artifact exists and return its path."""
    signals_dir = get_signals_dir(root)
    artifacts = list(signals_dir.glob("alert-signal-*.json"))
    assert len(artifacts) >= 1, f"Expected at least 1 artifact in {signals_dir}"
    return artifacts[0]


def read_artifact(artifact_path: Path) -> dict[str, object]:
    """Read and parse a JSON artifact."""
    text = artifact_path.read_text(encoding="utf-8")
    result: dict[str, object] = json.loads(text)
    return result


# =============================================================================
# Payload builders
# =============================================================================


def make_alertmanager_payload(
    status: str,
    labels: dict[str, str],
    annotations: dict[str, str] | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> bytes:
    """Build an Alertmanager webhook payload as bytes."""
    alert: dict[str, object] = {
        "status": status,
        "labels": labels,
        "startsAt": (starts_at or datetime.now(UTC)).isoformat(),
    }
    if annotations:
        alert["annotations"] = annotations
    if ends_at:
        alert["endsAt"] = ends_at.isoformat()
    return json.dumps({"alerts": [alert]}).encode("utf-8")


def make_firing_payload(
    alertname: str = "TestAlert",
    namespace: str = "prod",
    pod: str = "test-pod-xyz",
    severity: str = "critical",
    summary: str | None = None,
    description: str | None = None,
) -> bytes:
    """Build a firing Alertmanager webhook payload."""
    labels = {
        "alertname": alertname,
        "namespace": namespace,
        "pod": pod,
        "severity": severity,
    }
    annotations = {}
    if summary:
        annotations["summary"] = summary
    if description:
        annotations["description"] = description
    return make_alertmanager_payload(
        status="firing",
        labels=labels,
        annotations=annotations or None,
    )


def make_resolved_payload(
    alertname: str = "TestAlert",
    namespace: str = "prod",
    pod: str = "test-pod-xyz",
    severity: str = "critical",
    resolved_at: datetime | None = None,
) -> bytes:
    """Build a resolved Alertmanager webhook payload."""
    labels = {
        "alertname": alertname,
        "namespace": namespace,
        "pod": pod,
        "severity": severity,
    }
    return make_alertmanager_payload(
        status="resolved",
        labels=labels,
        ends_at=resolved_at or datetime.now(UTC),
    )


# =============================================================================
# Config builders
# =============================================================================


def make_webhook_config(
    enabled: bool = True,
    auto_promote: bool = True,
    bearer_token: str = "test-token",
    source_instance: str = "http://alertmanager:9093",
) -> AlertmanagerWebhookConfig:
    """Build a standard webhook config for testing."""
    return AlertmanagerWebhookConfig(
        enabled=enabled,
        auto_promote=auto_promote,
        bearer_token=bearer_token,
        source_instance=source_instance,
    )


# =============================================================================
# Incident store helpers
# =============================================================================


def make_incident_store() -> IncidentStore:
    """Create a fresh incident store for testing."""
    return IncidentStore()


# =============================================================================
# Assertion helpers
# =============================================================================


def assert_promotion_summary(
    response: object,
    *,
    enabled: bool | None = None,
    opened_incident_count: int | None = None,
    updated_incident_count: int | None = None,
    skipped_duplicate_count: int | None = None,
    resolved_signal_count: int | None = None,
    skipped_resolved_without_open_incident_count: int | None = None,
    firing_signal_count: int | None = None,
    scanned_signal_count: int | None = None,
) -> None:
    """Assert promotion summary fields have expected values."""
    promotion = getattr(response, "promotion", None)
    assert promotion is not None, "Promotion summary should be present"

    if enabled is not None:
        assert promotion.enabled == enabled, \
            f"Promotion.enabled: expected {enabled}, got {promotion.enabled}"
    if opened_incident_count is not None:
        assert promotion.opened_incident_count == opened_incident_count, \
            f"opened_incident_count: expected {opened_incident_count}, got {promotion.opened_incident_count}"
    if updated_incident_count is not None:
        assert promotion.updated_incident_count == updated_incident_count, \
            f"updated_incident_count: expected {updated_incident_count}, got {promotion.updated_incident_count}"
    if skipped_duplicate_count is not None:
        assert promotion.skipped_duplicate_count == skipped_duplicate_count, \
            f"skipped_duplicate_count: expected {skipped_duplicate_count}, got {promotion.skipped_duplicate_count}"
    if resolved_signal_count is not None:
        assert promotion.resolved_signal_count == resolved_signal_count, \
            f"resolved_signal_count: expected {resolved_signal_count}, got {promotion.resolved_signal_count}"
    if skipped_resolved_without_open_incident_count is not None:
        assert promotion.skipped_resolved_without_open_incident_count == skipped_resolved_without_open_incident_count, \
            f"skipped_resolved_without_open_incident_count: expected {skipped_resolved_without_open_incident_count}, got {promotion.skipped_resolved_without_open_incident_count}"
    if firing_signal_count is not None:
        assert promotion.firing_signal_count == firing_signal_count, \
            f"firing_signal_count: expected {firing_signal_count}, got {promotion.firing_signal_count}"
    if scanned_signal_count is not None:
        assert promotion.scanned_signal_count == scanned_signal_count, \
            f"scanned_signal_count: expected {scanned_signal_count}, got {promotion.scanned_signal_count}"


def assert_stored_signal_count(response: object, expected: int) -> None:
    """Assert the stored signal count."""
    assert response.stored_signal_count == expected, \
        f"stored_signal_count: expected {expected}, got {response.stored_signal_count}"


def assert_incident_count(store: IncidentStore, expected: int) -> None:
    """Assert the number of incidents in the store."""
    incidents = store.list_incidents()
    assert len(incidents) == expected, \
        f"Expected {expected} incidents, got {len(incidents)}"


def assert_incident_open(store: IncidentStore) -> IncidentStatus:
    """Assert exactly one incident exists and is OPEN, return it."""
    incidents = store.list_incidents()
    assert len(incidents) == 1, f"Expected 1 incident, got {len(incidents)}"
    assert incidents[0].status == IncidentStatus.OPEN, "Incident should be OPEN"
    return incidents[0]


# =============================================================================
# Stale artifact helpers
# =============================================================================


def write_stale_artifact(
    signals_dir: Path,
    identity: str,
    alertname: str,
    received_at: datetime,
    status: str = "firing",
    namespace: str = "old-ns",
) -> None:
    """Write a stale alert-signal artifact to the signals directory."""
    # Ensure parent directory exists (stale artifact tests pre-create it)
    signals_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "schema_version": ALERT_SIGNAL_SCHEMA_VERSION,
        "identity": identity,
        "received_at": received_at.isoformat(),
        "signal": {
            "signal_id": f"stale-signal-{identity}",
            "source_type": "alertmanager",
            "source_instance": "http://old-alertmanager:9093",
            "status": status,
            "alertname": alertname,
            "severity": "warning",
            "labels": {"alertname": alertname, "namespace": namespace},
            "annotations": {},
            "received_at": received_at.isoformat(),
        },
        "correlation_hints": None,
        "raw_payload_artifact_id": None,
    }
    artifact_path = signals_dir / f"alert-signal-{identity}.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")


# =============================================================================
# Test fixture class for shared setup/teardown
# =============================================================================


class AlertWebhookContractTest:
    """Shared setup/teardown for alert webhook contract tests.

    Provides temp directory with signals_dir, properly cleaned up.
    Subclasses define the test methods.
    """

    def setup_method(self) -> None:
        """Set up empty signals directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.signals_dir = get_signals_dir(self.root)
        assert not self.signals_dir.exists()  # Verify empty start

    def teardown_method(self) -> None:
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
