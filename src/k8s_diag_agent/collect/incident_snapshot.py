"""Incident snapshot collection for bounded, sanitized evidence capture.

This module provides read-only Kubernetes incident evidence collection for
LLM/Cline review. It captures namespace-scoped evidence into a deterministic
bundle without mutating the cluster.

Key constraints:
- Read-only: no mutation, no remediation
- Sanitized: secrets, tokens, auth headers redacted
- Bounded: namespace + time-scoped evidence
- Deterministic: consistent bundle layout
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..datetime_utils import now_utc
from ..security.sanitizer import sanitize_payload
from .live_snapshot_helpers import _extract_items, _int_or_zero

_logger = logging.getLogger(__name__)

# Subprocess timeout for kubectl commands
KUBECTL_COMMAND_TIMEOUT_SECONDS = 60

# Default lookback for events
DEFAULT_SINCE_HOURS = 2


class PodHealthStatus(StrEnum):
    """Pod health classification for incident triage."""

    RUNNING = "running"
    PENDING = "pending"
    FAILED = "failed"
    CRASH_LOOP = "crash_loop"
    IMAGE_PULL_ERROR = "image_pull_error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PodSummary:
    """Minimal pod evidence for incident bundle."""

    name: str
    namespace: str
    phase: str
    health_status: PodHealthStatus
    restart_count: int
    node: str | None
    image_refs: tuple[str, ...]
    reason: str | None
    message: str | None
    is_failing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "phase": self.phase,
            "health_status": self.health_status.value,
            "restart_count": self.restart_count,
            "node": self.node,
            "image_refs": list(self.image_refs),
            "reason": self.reason,
            "message": self.message,
            "is_failing": self.is_failing,
        }


@dataclass(frozen=True)
class EventSummary:
    """Minimal event evidence for incident bundle."""

    namespace: str
    name: str
    type: str
    reason: str
    message: str
    involved_object_kind: str | None
    involved_object_name: str | None
    count: int
    last_timestamp: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "type": self.type,
            "reason": self.reason,
            "message": self.message,
            "involved_object_kind": self.involved_object_kind,
            "involved_object_name": self.involved_object_name,
            "count": self.count,
            "last_timestamp": self.last_timestamp,
        }


@dataclass(frozen=True)
class DeploymentSummary:
    """Minimal deployment evidence for incident bundle."""

    name: str
    namespace: str
    replicas: int
    available_replicas: int
    ready_replicas: int
    updated_replicas: int
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "replicas": self.replicas,
            "available_replicas": self.available_replicas,
            "ready_replicas": self.ready_replicas,
            "updated_replicas": self.updated_replicas,
            "available": self.available,
        }


@dataclass(frozen=True)
class IncidentSymptom:
    """Detected incident symptom for triage."""

    symptom_type: str
    pod_name: str | None
    message: str
    severity: str  # warning, error

    def to_dict(self) -> dict[str, Any]:
        return {
            "symptom_type": self.symptom_type,
            "pod_name": self.pod_name,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class IncidentBundleMetadata:
    """Metadata for the incident evidence bundle."""

    bundle_id: str
    captured_at: datetime
    namespace: str
    since_hours: int
    context: str | None
    total_pods: int
    total_events: int
    total_deployments: int
    failing_pods_count: int
    symptoms_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "captured_at": self.captured_at.isoformat(),
            "namespace": self.namespace,
            "since_hours": self.since_hours,
            "context": self.context,
            "total_pods": self.total_pods,
            "total_events": self.total_events,
            "total_deployments": self.total_deployments,
            "failing_pods_count": self.failing_pods_count,
            "symptoms_count": self.symptoms_count,
        }


@dataclass
class IncidentEvidenceBundle:
    """Complete incident evidence bundle."""

    metadata: IncidentBundleMetadata
    pods: list[PodSummary]
    events: list[EventSummary]
    deployments: list[DeploymentSummary]
    symptoms: list[IncidentSymptom]
    collection_errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "pods": [p.to_dict() for p in self.pods],
            "events": [e.to_dict() for e in self.events],
            "deployments": [d.to_dict() for d in self.deployments],
            "symptoms": [s.to_dict() for s in self.symptoms],
            "collection_errors": list(self.collection_errors),
        }


def collect_incident_snapshot(
    namespace: str,
    context: str | None = None,
    since_hours: int = DEFAULT_SINCE_HOURS,
) -> IncidentEvidenceBundle:
    """Collect incident evidence for a namespace.

    Args:
        namespace: Kubernetes namespace to capture
        context: Kubernetes context (None for in-cluster)
        since_hours: Lookback window for events

    Returns:
        IncidentEvidenceBundle with sanitized evidence
    """
    errors: list[str] = []
    now = now_utc()

    # Generate deterministic bundle ID
    bundle_id = f"{namespace}-{now.strftime('%Y%m%d-%H%M%S')}"

    # Collect pods
    pods, pod_errors = _collect_pods(namespace, context)
    errors.extend(pod_errors)

    # Collect deployments
    deployments, deploy_errors = _collect_deployments(namespace, context)
    errors.extend(deploy_errors)

    # Collect events
    events, event_errors = _collect_events(namespace, context, since_hours)
    errors.extend(event_errors)

    # Identify failing pods
    failing_pods = [p for p in pods if p.is_failing]

    # Detect symptoms
    symptoms = _detect_symptoms(pods, events)

    metadata = IncidentBundleMetadata(
        bundle_id=bundle_id,
        captured_at=now,
        namespace=namespace,
        since_hours=since_hours,
        context=context,
        total_pods=len(pods),
        total_events=len(events),
        total_deployments=len(deployments),
        failing_pods_count=len(failing_pods),
        symptoms_count=len(symptoms),
    )

    return IncidentEvidenceBundle(
        metadata=metadata,
        pods=pods,
        events=events,
        deployments=deployments,
        symptoms=symptoms,
        collection_errors=tuple(errors),
    )


def _collect_pods(
    namespace: str,
    context: str | None,
) -> tuple[list[PodSummary], list[str]]:
    """Collect pod evidence for namespace."""
    errors: list[str] = []
    try:
        output = _kubectl(context, "get", "pods", "-n", namespace, "-o", "json")
    except RuntimeError as exc:
        errors.append(f"pods_collection: {exc}")
        return [], errors

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"pods_parse: {exc}")
        return [], errors

    items = _extract_items(payload)
    pods: list[PodSummary] = []

    for item in items:
        pod_summary = _parse_pod_summary(item)
        pods.append(pod_summary)

    return pods, errors


def _parse_pod_summary(pod: Mapping[str, Any]) -> PodSummary:
    """Parse a pod into a minimal PodSummary."""
    metadata = pod.get("metadata") or {}
    status = pod.get("status") or {}

    name = str(metadata.get("name") or "")
    ns = str(metadata.get("namespace") or "")

    phase = str(status.get("phase") or "Unknown").lower()

    # Get container status for detailed health info
    container_statuses = status.get("containerStatuses") or []
    restart_count = 0
    health_status = PodHealthStatus.UNKNOWN
    reason = None
    message = None
    is_failing = False

    for container in container_statuses:
        restart_count += _int_or_zero(container.get("restartCount"))
        # Check waiting state
        for attr in ("state", "lastState"):
            state_section = container.get(attr) or {}
            if not isinstance(state_section, dict):
                continue
            waiting = state_section.get("waiting")
            if not isinstance(waiting, dict):
                continue
            waiting_reason = str(waiting.get("reason") or "")
            if waiting_reason == "CrashLoopBackOff":
                health_status = PodHealthStatus.CRASH_LOOP
                reason = waiting_reason
                message = str(waiting.get("message") or "")
                is_failing = True
            elif waiting_reason == "ImagePullBackOff":
                health_status = PodHealthStatus.IMAGE_PULL_ERROR
                reason = waiting_reason
                message = str(waiting.get("message") or "")
                is_failing = True

    # Set phase-based status if not already set
    if health_status == PodHealthStatus.UNKNOWN:
        if phase == "running":
            health_status = PodHealthStatus.RUNNING
        elif phase == "pending":
            health_status = PodHealthStatus.PENDING
            is_failing = True
        elif phase in ("failed", "succeeded"):
            health_status = PodHealthStatus.FAILED
            is_failing = phase == "failed"

    # Extract image refs
    spec = pod.get("spec") or {}
    containers = spec.get("containers") or []
    image_refs: list[str] = []
    for container in containers:
        image = container.get("image")
        if image:
            image_refs.append(str(image))

    # Get node
    node = spec.get("nodeName")

    # Get reason/message from pod status conditions
    conditions = status.get("conditions") or []
    for cond in conditions:
        if str(cond.get("type") or "") == "Ready":
            if cond.get("status") != "True":
                if not is_failing:
                    is_failing = True
                    reason = "NotReady"
                    message = str(cond.get("message") or "")

    # Sanitize the summary
    sanitized_message = message
    if message:
        sanitized = sanitize_payload(message)
        if isinstance(sanitized, str):
            sanitized_message = sanitized

    return PodSummary(
        name=name,
        namespace=ns,
        phase=phase,
        health_status=health_status,
        restart_count=restart_count,
        node=node,
        image_refs=tuple(image_refs),
        reason=reason,
        message=sanitized_message,
        is_failing=is_failing,
    )


def _collect_deployments(
    namespace: str,
    context: str | None,
) -> tuple[list[DeploymentSummary], list[str]]:
    """Collect deployment evidence for namespace."""
    errors: list[str] = []
    try:
        output = _kubectl(
            context, "get", "deployments", "-n", namespace, "-o", "json"
        )
    except RuntimeError as exc:
        errors.append(f"deployments_collection: {exc}")
        return [], errors

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"deployments_parse: {exc}")
        return [], errors

    items = _extract_items(payload)
    deployments: list[DeploymentSummary] = []

    for item in items:
        deployment_summary = _parse_deployment_summary(item)
        deployments.append(deployment_summary)

    return deployments, errors


def _parse_deployment_summary(deployment: Mapping[str, Any]) -> DeploymentSummary:
    """Parse a deployment into a minimal DeploymentSummary."""
    metadata = deployment.get("metadata") or {}
    spec = deployment.get("spec") or {}
    status = deployment.get("status") or {}

    name = str(metadata.get("name") or "")
    ns = str(metadata.get("namespace") or "")

    replicas = _int_or_zero(spec.get("replicas"))
    available_replicas = _int_or_zero(status.get("availableReplicas"))
    ready_replicas = _int_or_zero(status.get("readyReplicas"))
    updated_replicas = _int_or_zero(status.get("updatedReplicas"))

    # available = all replicas are available
    available = available_replicas >= replicas and replicas > 0

    return DeploymentSummary(
        name=name,
        namespace=ns,
        replicas=replicas,
        available_replicas=available_replicas,
        ready_replicas=ready_replicas,
        updated_replicas=updated_replicas,
        available=available,
    )


def _collect_events(
    namespace: str,
    context: str | None,
    since_hours: int,
) -> tuple[list[EventSummary], list[str]]:
    """Collect event evidence for namespace."""
    errors: list[str] = []
    try:
        output = _kubectl(
            context,
            "get",
            "events",
            "-n",
            namespace,
            "--field-selector",
            f"lastTimestamp>=now-{since_hours}h",
            "-o",
            "json",
        )
    except RuntimeError:
        # Fallback without time filter
        try:
            output = _kubectl(context, "get", "events", "-n", namespace, "-o", "json")
        except RuntimeError as exc:
            errors.append(f"events_collection: {exc}")
            return [], errors

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        errors.append(f"events_parse: {exc}")
        return [], errors

    items = _extract_items(payload)
    events: list[EventSummary] = []

    for item in items:
        event_summary = _parse_event_summary(item)
        events.append(event_summary)

    return events, errors


def _parse_event_summary(event: Mapping[str, Any]) -> EventSummary:
    """Parse an event into a minimal EventSummary."""
    metadata = event.get("metadata") or {}
    involved = event.get("involvedObject") or {}

    # Sanitize message to prevent credential leakage
    raw_message = str(event.get("message") or "")
    sanitized_message = raw_message
    if raw_message:
        sanitized = sanitize_payload(raw_message)
        if isinstance(sanitized, str):
            sanitized_message = sanitized

    return EventSummary(
        namespace=str(metadata.get("namespace") or ""),
        name=str(metadata.get("name") or ""),
        type=str(event.get("type") or "Normal"),
        reason=str(event.get("reason") or ""),
        message=sanitized_message,
        involved_object_kind=str(involved.get("kind") or ""),
        involved_object_name=str(involved.get("name") or ""),
        count=_int_or_zero(event.get("count")),
        last_timestamp=str(
            metadata.get("lastTimestamp") or metadata.get("eventTime") or ""
        ),
    )


def _detect_symptoms(
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


def _kubectl(context: str | None, *args: str) -> str:
    """Execute a kubectl command with optional context."""
    command = ["kubectl"]
    if context:
        command.extend(["--context", context])
    command.extend(args)
    return _run_command(command)


def _run_command(command: Sequence[str]) -> str:
    """Execute a command with timeout."""
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=KUBECTL_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"`{command[0]}` timed out after {KUBECTL_COMMAND_TIMEOUT_SECONDS}s"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command `{command[0]}` not found") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr if exc.stderr else exc.stdout
        raise RuntimeError(f"`{command[0]}` failed: {stderr[:200]}") from exc
    return result.stdout


def write_incident_bundle(
    bundle: IncidentEvidenceBundle,
    output_dir: Path,
) -> dict[str, Path]:
    """Write incident bundle to disk with deterministic layout.

    Returns:
        Mapping of file names to written paths
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}

    # Write incident.json (machine-readable summary)
    incident_path = output_dir / "incident.json"
    incident_path.write_text(
        json.dumps(bundle.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written["incident.json"] = incident_path

    # Write evidence-index.md (human-readable index)
    index_path = output_dir / "evidence-index.md"
    index_path.write_text(_build_evidence_index(bundle), encoding="utf-8")
    written["evidence-index.md"] = index_path

    # Write objects/
    objects_dir = output_dir / "objects"
    objects_dir.mkdir(exist_ok=True)

    pods_path = objects_dir / "pods.json"
    pods_path.write_text(
        json.dumps([p.to_dict() for p in bundle.pods], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written["objects/pods.json"] = pods_path

    deployments_path = objects_dir / "deployments.json"
    deployments_path.write_text(
        json.dumps(
            [d.to_dict() for d in bundle.deployments], indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    written["objects/deployments.json"] = deployments_path

    events_path = objects_dir / "events.json"
    events_path.write_text(
        json.dumps([e.to_dict() for e in bundle.events], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    written["objects/events.json"] = events_path

    # Write summary/symptoms.md
    summary_dir = output_dir / "summary"
    summary_dir.mkdir(exist_ok=True)

    symptoms_path = summary_dir / "symptoms.md"
    symptoms_path.write_text(_build_symptoms_report(bundle), encoding="utf-8")
    written["summary/symptoms.md"] = symptoms_path

    return written


def _build_evidence_index(bundle: IncidentEvidenceBundle) -> str:
    """Build evidence index markdown."""
    lines = [
        "# Incident Evidence Index",
        "",
        f"**Bundle ID**: {bundle.metadata.bundle_id}",
        f"**Captured**: {bundle.metadata.captured_at.isoformat()}",
        f"**Namespace**: {bundle.metadata.namespace}",
        f"**Context**: {bundle.metadata.context or 'in-cluster'}",
        "",
        "## Evidence Summary",
        "",
        f"- Pods: {bundle.metadata.total_pods} (failing: {bundle.metadata.failing_pods_count})",
        f"- Deployments: {bundle.metadata.total_deployments}",
        f"- Events: {bundle.metadata.total_events}",
        f"- Symptoms: {bundle.metadata.symptoms_count}",
        "",
        "## Bundle Contents",
        "",
        "```",
        "incident.json          # Machine-readable incident bundle",
        "evidence-index.md      # This file",
        "objects/",
        "  pods.json            # All pods in namespace",
        "  deployments.json     # All deployments in namespace",
        "  events.json          # Events in namespace",
        "summary/",
        "  symptoms.md          # Detected symptoms and triage",
        "```",
        "",
        "## Detected Symptoms",
        "",
    ]

    if bundle.symptoms:
        for symptom in bundle.symptoms:
            lines.append(
                f"- **{symptom.symptom_type}** ({symptom.severity}): {symptom.message}"
            )
    else:
        lines.append("_No symptoms detected_")

    if bundle.collection_errors:
        lines.append("")
        lines.append("## Collection Errors")
        lines.append("")
        for error in bundle.collection_errors:
            lines.append(f"- {error}")

    lines.append("")
    return "\n".join(lines)


def _build_symptoms_report(bundle: IncidentEvidenceBundle) -> str:
    """Build symptoms report markdown."""
    lines = [
        "# Incident Symptoms",
        "",
        f"**Bundle ID**: {bundle.metadata.bundle_id}",
        f"**Namespace**: {bundle.metadata.namespace}",
        "",
        f"Total symptoms detected: {bundle.metadata.symptoms_count}",
        "",
    ]

    if not bundle.symptoms:
        lines.append("## No Symptoms Detected")
        lines.append("")
        lines.append("No mechanical symptoms were detected in the captured evidence.")
        lines.append("Manual investigation may be required.")
    else:
        # Group by severity
        errors = [s for s in bundle.symptoms if s.severity == "error"]
        warnings = [s for s in bundle.symptoms if s.severity == "warning"]

        if errors:
            lines.append("## Critical Symptoms (Error)")
            lines.append("")
            for symptom in errors:
                pod_info = f"Pod: `{symptom.pod_name}`" if symptom.pod_name else ""
                lines.append(f"- **{symptom.symptom_type}**")
                lines.append(f"  - {pod_info}")
                lines.append(f"  - {symptom.message}")
                lines.append("")

        if warnings:
            lines.append("## Warning Symptoms")
            lines.append("")
            for symptom in warnings:
                pod_info = f"Pod: `{symptom.pod_name}`" if symptom.pod_name else ""
                lines.append(f"- **{symptom.symptom_type}**")
                lines.append(f"  - {pod_info}")
                lines.append(f"  - {symptom.message}")
                lines.append("")

    lines.append("## Manual Investigation Required")
    lines.append("")
    lines.append(
        "This is a deterministic symptom summary only. "
        "LLM review of the raw evidence is required for root cause analysis."
    )

    return "\n".join(lines)


__all__ = [
    "IncidentEvidenceBundle",
    "IncidentBundleMetadata",
    "PodSummary",
    "DeploymentSummary",
    "EventSummary",
    "IncidentSymptom",
    "PodHealthStatus",
    "collect_incident_snapshot",
    "write_incident_bundle",
    "DEFAULT_SINCE_HOURS",
]
