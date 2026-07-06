"""Bounds and edge case fixtures for Alertmanager webhook payloads.

Fixtures:
- Large number of labels
- Large label/annotation values
- Empty label values
- Special characters in labels/annotations
"""

from __future__ import annotations

from typing import Any


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
