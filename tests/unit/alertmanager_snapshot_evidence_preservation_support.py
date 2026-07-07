"""Shared fixtures, builders, and helpers for alertmanager_snapshot_evidence_preservation tests.

This module provides:
- Test alert builders
- Test snapshot builders
- Shared assertion helpers
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from k8s_diag_agent.external_analysis.alertmanager_snapshot import (
    AlertmanagerSnapshot,
    AlertmanagerStatus,
    NormalizedAlert,
)


def make_normalized_alert(
    fingerprint: str = "fp123",
    alertname: str = "TestAlert",
    state: str = "active",
    severity: str = "warning",
    namespace: str = "default",
    labels: list[tuple[str, str]] | None = None,
    summary: str | None = None,
    annotations: tuple[tuple[str, str], ...] | None = None,
    generator_url: str | None = None,
    ends_at: str | None = None,
    updated_at: str | None = None,
    receiver: str | None = None,
) -> NormalizedAlert:
    """Helper to create test normalized alerts with ACT-R1 fields."""
    if labels is None:
        labels = [
            ("alertname", alertname),
            ("severity", severity),
        ]
        if namespace:
            labels.append(("namespace", namespace))
    if annotations is None:
        annotations = ()
    return NormalizedAlert(
        fingerprint=fingerprint,
        alertname=alertname,
        state=state,
        severity=severity,
        namespace=namespace,
        labels=tuple(labels),
        summary=summary,
        annotations=annotations,
        generator_url=generator_url,
        ends_at=ends_at,
        updated_at=updated_at,
        receiver=receiver,
    )


def make_snapshot(
    alerts: list[NormalizedAlert] | None = None,
    status: AlertmanagerStatus = AlertmanagerStatus.OK,
    captured_at: str | None = None,
    source: str = "http://alertmanager:9093",
    artifact_id: str = "test-snapshot-id",
) -> AlertmanagerSnapshot:
    """Helper to create test snapshots."""
    if alerts is None:
        alerts = []
    return AlertmanagerSnapshot(
        status=status,
        captured_at=captured_at or datetime.now(UTC).isoformat(),
        source=source,
        alert_count=len(alerts),
        alerts=tuple(alerts),
        errors=(),
        truncated=False,
        artifact_id=artifact_id,
    )


def make_alert_with_annotations(
    annotations_dict: dict[str, str],
    **overrides: Any,
) -> NormalizedAlert:
    """Helper to create alert with specific annotations."""
    annotations = tuple(sorted(annotations_dict.items()))
    return make_normalized_alert(annotations=annotations, **overrides)


def make_raw_alert_payload(
    labels: dict[str, str] | None = None,
    annotations: dict[str, str] | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    """Helper to create raw alert payload for normalize_alertmanager_payload."""
    if labels is None:
        labels = {"alertname": "TestAlert"}
    payload: dict[str, Any] = {"labels": labels}
    if annotations is not None:
        payload["annotations"] = annotations
    payload.update(extra_fields)
    return payload


def assert_alert_has_annotations(
    alert: NormalizedAlert,
    expected: dict[str, str],
) -> None:
    """Assert alert has expected annotations."""
    ann_dict = dict(alert.annotations)
    for key, value in expected.items():
        assert key in ann_dict, f"Missing annotation key: {key}"
        assert ann_dict[key] == value, f"Annotation {key}: expected {value!r}, got {ann_dict[key]!r}"


def assert_alert_field_equals(
    alert: NormalizedAlert,
    field_name: str,
    expected: str | None,
) -> None:
    """Assert alert field equals expected value."""
    actual = getattr(alert, field_name)
    assert actual == expected, f"Alert.{field_name}: expected {expected!r}, got {actual!r}"
