"""Triage functions for incident snapshot detection.

This module contains functions for detecting mechanical incident symptoms
from Kubernetes evidence (pods, events).
"""

from __future__ import annotations

from .incident_models import EventSummary, IncidentSymptom, PodHealthStatus, PodSummary


def detect_symptoms(
    pods: list[PodSummary],
    events: list[EventSummary],
) -> list[IncidentSymptom]:
    """Detect mechanical incident symptoms from evidence."""
    symptoms: list[IncidentSymptom] = []

    # Pod-based symptoms
    for pod in pods:
        if pod.health_status == PodHealthStatus.CRASH_LOOP:
            symptoms.append(
                IncidentSymptom(
                    symptom_type="crash_loop",
                    pod_name=pod.name,
                    message=f"Pod {pod.name} in CrashLoopBackOff",
                    severity="error",
                )
            )
        elif pod.health_status == PodHealthStatus.IMAGE_PULL_ERROR:
            symptoms.append(
                IncidentSymptom(
                    symptom_type="image_pull_error",
                    pod_name=pod.name,
                    message=f"Pod {pod.name} unable to pull image",
                    severity="error",
                )
            )
        elif pod.health_status == PodHealthStatus.PENDING:
            symptoms.append(
                IncidentSymptom(
                    symptom_type="pending_pod",
                    pod_name=pod.name,
                    message=f"Pod {pod.name} stuck in Pending state",
                    severity="warning",
                )
            )
        elif pod.health_status == PodHealthStatus.FAILED:
            symptoms.append(
                IncidentSymptom(
                    symptom_type="failed_pod",
                    pod_name=pod.name,
                    message=f"Pod {pod.name} failed",
                    severity="error",
                )
            )

    # Event-based symptoms
    for event in events:
        if event.type == "Warning":
            symptoms.append(
                IncidentSymptom(
                    symptom_type="warning_event",
                    pod_name=event.involved_object_name,
                    message=f"Warning: {event.reason} - {event.message[:100]}",
                    severity="warning",
                )
            )

    return symptoms


__all__ = [
    "detect_symptoms",
]
