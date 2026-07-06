"""Invalid/malformed payload fixtures for Alertmanager webhook payloads.

Fixtures:
- Minimal payload with only required fields
- Missing alertname label
- Missing alerts field
- Invalid alerts field type
- Invalid alert status
- Non-string label values
"""

from __future__ import annotations

from typing import Any


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
