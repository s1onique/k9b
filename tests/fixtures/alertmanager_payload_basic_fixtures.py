"""Basic single alert fixtures for Alertmanager webhook payloads.

Fixtures:
- Single firing alert
- Single resolved alert
"""

from __future__ import annotations

from typing import Any


def single_firing_alert_payload(
    *,
    alertname: str = "HighCPUUsage",
    severity: str = "warning",
    namespace: str = "production",
    instance: str = "node-1",
    fingerprint: str | None = "abc123def456",
    starts_at: str = "2024-01-15T10:00:00.000Z",
    ends_at: str | None = None,
    generator_url: str = "http://prometheus/alerts/123",
    **extra_labels: Any,
) -> dict[str, Any]:
    """Single firing alert payload.

    Args:
        alertname: Alert name
        severity: Alert severity
        namespace: Kubernetes namespace
        instance: Instance identifier
        fingerprint: Alertmanager fingerprint
        starts_at: Alert start time (RFC3339)
        ends_at: Alert end time (RFC3339), None for firing
        generator_url: Prometheus generator URL
        **extra_labels: Additional labels to include

    Returns:
        Alertmanager webhook payload dict
    """
    labels = {
        "alertname": alertname,
        "severity": severity,
        "namespace": namespace,
        "instance": instance,
        "cluster": "prod-cluster",
        **extra_labels,
    }

    alert = {
        "status": "firing",
        "labels": labels,
        "annotations": {
            "summary": f"High CPU usage on {instance}",
            "description": f"CPU usage above 90% for 5 minutes on {instance}",
        },
        "startsAt": starts_at,
        "generatorURL": generator_url,
        "fingerprint": fingerprint,
    }

    if ends_at:
        alert["endsAt"] = ends_at

    return {
        "version": "4",
        "groupKey": "{namespace=" + namespace + "}",
        "status": "firing",
        "receiver": "k9b-receiver",
        "groupLabels": {
            "alertname": alertname,
            "namespace": namespace,
        },
        "commonLabels": labels,
        "commonAnnotations": {
            "summary": f"High CPU usage on {instance}",
            "description": f"CPU usage above 90% for 5 minutes on {instance}",
        },
        "externalURL": "http://alertmanager:9093",
        "alerts": [alert],
    }


def single_resolved_alert_payload(
    *,
    alertname: str = "HighCPUUsage",
    severity: str = "warning",
    namespace: str = "production",
    instance: str = "node-1",
    fingerprint: str | None = "abc123def456",
    starts_at: str = "2024-01-15T10:00:00.000Z",
    ends_at: str = "2024-01-15T10:15:00.000Z",
    generator_url: str = "http://prometheus/alerts/123",
    **extra_labels: Any,
) -> dict[str, Any]:
    """Single resolved alert payload.

    Args:
        alertname: Alert name
        severity: Alert severity
        namespace: Kubernetes namespace
        instance: Instance identifier
        fingerprint: Alertmanager fingerprint
        starts_at: Alert start time (RFC3339)
        ends_at: Alert end time (RFC3339)
        generator_url: Prometheus generator URL
        **extra_labels: Additional labels to include

    Returns:
        Alertmanager webhook payload dict
    """
    labels = {
        "alertname": alertname,
        "severity": severity,
        "namespace": namespace,
        "instance": instance,
        "cluster": "prod-cluster",
        **extra_labels,
    }

    return {
        "version": "4",
        "groupKey": "{namespace=" + namespace + "}",
        "status": "resolved",
        "receiver": "k9b-receiver",
        "groupLabels": {
            "alertname": alertname,
            "namespace": namespace,
        },
        "commonLabels": labels,
        "commonAnnotations": {
            "summary": f"High CPU usage on {instance}",
            "description": f"CPU usage above 90% for 5 minutes on {instance}",
        },
        "externalURL": "http://alertmanager:9093",
        "alerts": [{
            "status": "resolved",
            "labels": labels,
            "annotations": {
                "summary": f"High CPU usage on {instance}",
                "description": f"CPU usage above 90% for 5 minutes on {instance}",
            },
            "startsAt": starts_at,
            "endsAt": ends_at,
            "generatorURL": generator_url,
            "fingerprint": fingerprint,
        }],
    }
