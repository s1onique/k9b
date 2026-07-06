"""Alertmanager webhook payload fixtures for testing.

This module provides fixtures for testing alert signal normalization.
It includes payloads for various alert scenarios.

Fixtures:
- Single firing alert
- Single resolved alert
- Grouped firing alerts
- Mixed firing/resolved group
- Missing optional fields
- Large labels/annotations requiring bounds
- Invalid payload
"""

from __future__ import annotations

from typing import Any

# =============================================================================
# Single Alert Fixtures
# =============================================================================

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


# =============================================================================
# Grouped Alert Fixtures
# =============================================================================

def grouped_firing_alerts_payload(
    *,
    alertname: str = "KubePodNotReady",
    namespace: str = "production",
    pod_names: tuple[str, ...] = ("pod-1", "pod-2", "pod-3"),
    severity: str = "critical",
    starts_at: str = "2024-01-15T10:00:00.000Z",
) -> dict[str, Any]:
    """Grouped firing alerts payload.

    Args:
        alertname: Alert name
        namespace: Kubernetes namespace
        pod_names: Tuple of pod names
        severity: Alert severity
        starts_at: Alert start time (RFC3339)

    Returns:
        Alertmanager webhook payload dict
    """
    common_labels = {
        "alertname": alertname,
        "severity": severity,
        "namespace": namespace,
        "cluster": "prod-cluster",
    }

    alerts = []
    for pod in pod_names:
        alerts.append({
            "status": "firing",
            "labels": {
                **common_labels,
                "pod": pod,
                "instance": f"kube-system/{pod}",
            },
            "annotations": {
                "summary": f"Pod {pod} is not ready",
                "description": f"Pod {pod} has been not ready for more than 5 minutes",
            },
            "startsAt": starts_at,
            "generatorURL": f"http://prometheus/alerts/{pod}",
            "fingerprint": f"fp-{pod}",
        })

    return {
        "version": "4",
        "groupKey": "{namespace=" + namespace + ",alertname=" + alertname + "}",
        "status": "firing",
        "receiver": "k9b-receiver",
        "groupLabels": {
            "alertname": alertname,
            "namespace": namespace,
        },
        "commonLabels": common_labels,
        "commonAnnotations": {
            "summary": f"Multiple pods not ready in {namespace}",
        },
        "externalURL": "http://alertmanager:9093",
        "alerts": alerts,
    }


def mixed_firing_resolved_group_payload(
    *,
    alertname: str = "EndpointDown",
    namespace: str = "monitoring",
    endpoints: tuple[str, ...] = ("ep-1", "ep-2", "ep-3"),
    firing_endpoints: tuple[str, ...] = ("ep-1", "ep-2"),
    resolved_endpoint: str = "ep-3",
    severity: str = "critical",
    starts_at: str = "2024-01-15T10:00:00.000Z",
    resolved_at: str = "2024-01-15T10:15:00.000Z",
) -> dict[str, Any]:
    """Mixed firing/resolved group payload.

    Args:
        alertname: Alert name
        namespace: Kubernetes namespace
        endpoints: All endpoint names
        firing_endpoints: Endpoints that are still firing
        resolved_endpoint: Endpoint that resolved
        severity: Alert severity
        starts_at: Alert start time (RFC3339)
        resolved_at: When the resolved endpoint came back up

    Returns:
        Alertmanager webhook payload dict
    """
    common_labels = {
        "alertname": alertname,
        "severity": severity,
        "namespace": namespace,
        "cluster": "prod-cluster",
    }

    alerts = []

    # Add firing alerts
    for ep in firing_endpoints:
        alerts.append({
            "status": "firing",
            "labels": {
                **common_labels,
                "endpoint": ep,
                "service": f"service-{ep}",
            },
            "annotations": {
                "summary": f"Endpoint {ep} is down",
                "description": f"Endpoint {ep} is not reachable",
            },
            "startsAt": starts_at,
            "generatorURL": f"http://prometheus/alerts/{ep}",
            "fingerprint": f"fp-{ep}",
        })

    # Add resolved alert
    alerts.append({
        "status": "resolved",
        "labels": {
            **common_labels,
            "endpoint": resolved_endpoint,
            "service": f"service-{resolved_endpoint}",
        },
        "annotations": {
            "summary": f"Endpoint {resolved_endpoint} is down",
            "description": f"Endpoint {resolved_endpoint} is not reachable",
        },
        "startsAt": starts_at,
        "endsAt": resolved_at,
        "generatorURL": f"http://prometheus/alerts/{resolved_endpoint}",
        "fingerprint": f"fp-{resolved_endpoint}",
    })

    return {
        "version": "4",
        "groupKey": "{namespace=" + namespace + ",alertname=" + alertname + "}",
        "status": "firing",
        "receiver": "k9b-receiver",
        "groupLabels": {
            "alertname": alertname,
            "namespace": namespace,
        },
        "commonLabels": common_labels,
        "commonAnnotations": {
            "summary": f"Endpoints down in {namespace}",
        },
        "externalURL": "http://alertmanager:9093",
        "alerts": alerts,
    }


# =============================================================================
# Missing Fields Fixtures
# =============================================================================

def minimal_alert_payload(
    *,
    alertname: str = "TestAlert",
) -> dict[str, Any]:
    """Minimal alert payload with only required fields.

    Args:
        alertname: Alert name

    Returns:
        Minimal Alertmanager webhook payload dict
    """
    return {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": alertname,
            },
        }],
    }


def missing_alertname_payload() -> dict[str, Any]:
    """Payload with missing alertname label.

    Returns:
        Alertmanager webhook payload dict with missing alertname
    """
    return {
        "alerts": [{
            "status": "firing",
            "labels": {
                "severity": "warning",
                "namespace": "test",
            },
        }],
    }


def missing_alerts_field_payload() -> dict[str, Any]:
    """Payload with missing alerts field.

    Returns:
        Alertmanager webhook payload dict missing alerts
    """
    return {
        "version": "4",
        "status": "firing",
        "receiver": "k9b-receiver",
    }


def invalid_alerts_field_payload() -> dict[str, Any]:
    """Payload with invalid alerts field (not an array).

    Returns:
        Alertmanager webhook payload dict with invalid alerts
    """
    return {
        "version": "4",
        "status": "firing",
        "receiver": "k9b-receiver",
        "alerts": {"status": "firing"},  # Should be array
    }


# =============================================================================
# Large Labels/Annotations Fixtures
# =============================================================================

def large_labels_payload(
    *,
    label_count: int = 150,
    key_prefix: str = "label_",
    value_length: int = 1000,
) -> dict[str, Any]:
    """Payload with large number of labels.

    Args:
        label_count: Number of labels to generate
        key_prefix: Prefix for label keys
        value_length: Length of each label value

    Returns:
        Alertmanager webhook payload dict with many labels
    """
    labels = {}
    for i in range(label_count):
        labels[f"{key_prefix}{i}"] = "x" * value_length

    labels["alertname"] = "LargeLabelsAlert"

    return {
        "alerts": [{
            "status": "firing",
            "labels": labels,
            "annotations": {
                "summary": "Alert with many labels",
            },
        }],
    }


def large_value_payload(
    *,
    key: str = "description",
    value_length: int = 10000,
) -> dict[str, Any]:
    """Payload with very large label/annotation values.

    Args:
        key: Key for the large value
        value_length: Length of the value

    Returns:
        Alertmanager webhook payload dict with large values
    """
    return {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": "LargeValueAlert",
                "namespace": "test",
            },
            "annotations": {
                "summary": "Alert with large annotation value",
                key: "x" * value_length,
            },
        }],
    }


# =============================================================================
# VMAlert Fixtures
# =============================================================================

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


# =============================================================================
# Edge Case Fixtures
# =============================================================================

def empty_labels_payload(
    *,
    alertname: str = "EmptyLabelsAlert",
) -> dict[str, Any]:
    """Payload with empty label values.

    Args:
        alertname: Alert name

    Returns:
        Alertmanager webhook payload dict with empty labels
    """
    return {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": alertname,
                "empty_label": "",
                "nil_label": None,
            },
            "annotations": {
                "empty_annotation": "",
            },
        }],
    }


def special_characters_payload(
    *,
    alertname: str = "SpecialCharsAlert",
    namespace: str = "default",
) -> dict[str, Any]:
    """Payload with special characters in labels/annotations.

    Args:
        alertname: Alert name
        namespace: Namespace with special characters

    Returns:
        Alertmanager webhook payload dict with special characters
    """
    return {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": alertname,
                "namespace": namespace,
                "special_key": "value with <html> & \"quotes\"",
            },
            "annotations": {
                "summary": "Alert with special characters",
                "description": "Description with unicode: émoji 🎉 and 'quotes' and <html>",
            },
        }],
    }


def invalid_status_payload(
    *,
    alertname: str = "InvalidStatusAlert",
) -> dict[str, Any]:
    """Payload with invalid alert status.

    Args:
        alertname: Alert name

    Returns:
        Alertmanager webhook payload dict with invalid status
    """
    return {
        "alerts": [{
            "status": "invalid_status",
            "labels": {
                "alertname": alertname,
            },
        }],
    }


def non_string_labels_payload(
    *,
    alertname: str = "NonStringLabelsAlert",
) -> dict[str, Any]:
    """Payload with non-string label values.

    Args:
        alertname: Alert name

    Returns:
        Alertmanager webhook payload dict with non-string labels
    """
    return {
        "alerts": [{
            "status": "firing",
            "labels": {
                "alertname": alertname,
                "int_value": 123,
                "float_value": 45.67,
                "bool_value": True,
                "list_value": ["a", "b", "c"],
                "dict_value": {"nested": "value"},
            },
        }],
    }
