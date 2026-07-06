"""Grouped alert fixtures for Alertmanager webhook payloads.

Fixtures:
- Grouped firing alerts
- Mixed firing/resolved group
"""

from __future__ import annotations

from typing import Any


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
