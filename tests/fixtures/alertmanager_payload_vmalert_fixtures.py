"""vmalert-specific fixtures for Alertmanager webhook payloads.

Fixtures:
- vmalert firing alert
- vmalert resolved alert

vmalert flows through Alertmanager, so these are Alertmanager-format
payloads with explicit vmalert identification via k9b.dev/source_type label.
"""

from __future__ import annotations

from typing import Any


def vmalert_firing_payload(
    *,
    alertname: str = "HighMemoryUsage",
    group_name: str = "vmagent",
    rule_name: str = "HighMemory",
    severity: str = "warning",
    entity_type: str = "host",
    entity_name: str = "server-1",
    fingerprint: str | None = "vmalert-fp-123",
    starts_at: str = "2024-01-15T10:00:00.000Z",
) -> dict[str, Any]:
    """vmalert firing alert payload.

    vmalert flows through Alertmanager, so this is an Alertmanager-format
    payload with explicit vmalert identification via k9b.dev/source_type label.

    Args:
        alertname: Alert name
        group_name: vmalert group name
        rule_name: vmalert rule name
        severity: Alert severity
        entity_type: Type of entity being monitored
        entity_name: Name of the entity
        fingerprint: Alert fingerprint
        starts_at: Alert start time

    Returns:
        Alertmanager webhook payload dict for vmalert
    """
    return {
        "version": "4",
        "groupKey": "{group=" + group_name + "}",
        "status": "firing",
        "receiver": "k9b-receiver",
        "groupLabels": {
            "alertname": alertname,
            "group": group_name,
        },
        "commonLabels": {
            "alertname": alertname,
            "severity": severity,
            "group": group_name,
            "rule": rule_name,
            "entity_type": entity_type,
            "entity": entity_name,
            "cluster": "prod-cluster",
            "k9b.dev/source_type": "vmalert",  # Explicit vmalert indicator
        },
        "commonAnnotations": {
            "summary": f"High memory usage on {entity_name}",
            "description": f"Memory usage above threshold for {entity_name}",
        },
        "externalURL": "http://alertmanager:9093",
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": alertname,
                "severity": severity,
                "group": group_name,
                "rule": rule_name,
                "entity_type": entity_type,
                "entity": entity_name,
                "cluster": "prod-cluster",
                "k9b.dev/source_type": "vmalert",
            },
            "annotations": {
                "summary": f"High memory usage on {entity_name}",
                "description": f"Memory usage above threshold for {entity_name}",
            },
            "startsAt": starts_at,
            "generatorURL": f"http://vmalert:8880/rule/{group_name}/{rule_name}",
            "fingerprint": fingerprint,
        }],
    }


def vmalert_resolved_payload(
    *,
    alertname: str = "HighMemoryUsage",
    group_name: str = "vmagent",
    severity: str = "warning",
    entity_name: str = "server-1",
    starts_at: str = "2024-01-15T10:00:00.000Z",
    ends_at: str = "2024-01-15T10:30:00.000Z",
) -> dict[str, Any]:
    """vmalert resolved alert payload.

    Args:
        alertname: Alert name
        group_name: vmalert group name
        severity: Alert severity
        entity_name: Name of the entity
        starts_at: Alert start time
        ends_at: Alert end time

    Returns:
        Alertmanager webhook payload dict for vmalert
    """
    return {
        "version": "4",
        "groupKey": "{group=" + group_name + "}",
        "status": "resolved",
        "receiver": "k9b-receiver",
        "groupLabels": {
            "alertname": alertname,
            "group": group_name,
        },
        "commonLabels": {
            "alertname": alertname,
            "severity": severity,
            "group": group_name,
            "entity": entity_name,
            "cluster": "prod-cluster",
            "k9b.dev/source_type": "vmalert",
        },
        "commonAnnotations": {
            "summary": f"High memory usage on {entity_name}",
        },
        "externalURL": "http://alertmanager:9093",
        "alerts": [{
            "status": "resolved",
            "labels": {
                "alertname": alertname,
                "severity": severity,
                "group": group_name,
                "entity": entity_name,
                "cluster": "prod-cluster",
                "k9b.dev/source_type": "vmalert",
            },
            "annotations": {
                "summary": f"High memory usage on {entity_name}",
            },
            "startsAt": starts_at,
            "endsAt": ends_at,
            "generatorURL": f"http://vmalert:8880/rule/{group_name}/{alertname}",
            "fingerprint": f"vmalert-fp-{entity_name}",
        }],
    }
