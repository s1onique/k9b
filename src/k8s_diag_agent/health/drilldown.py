"""Targeted drilldown helpers for health loop diagnostics."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from textwrap import shorten
from typing import Any, ClassVar

from ..collect.cluster_snapshot import WarningEventSummary
from ..datetime_utils import parse_iso_to_utc
from .image_pull_secret import ImagePullSecretInsight


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _run_command(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command `{command[0]}` not found.") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"`{command[0]}` failed: {message}") from exc
    return result.stdout


def _extract_items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, Mapping)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    return []


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class DrilldownPod:
    namespace: str
    name: str
    phase: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "namespace": self.namespace,
            "name": self.name,
            "phase": self.phase,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> DrilldownPod:
        if not isinstance(raw, Mapping):
            raise ValueError("pod entry must be a mapping")
        return cls(
            namespace=str(raw.get("namespace") or ""),
            name=str(raw.get("name") or ""),
            phase=str(raw.get("phase") or ""),
            reason=str(raw.get("reason") or ""),
        )


@dataclass(frozen=True)
class DrilldownRolloutStatus:
    kind: str
    namespace: str
    name: str
    desired_replicas: int
    available_replicas: int
    unavailable_replicas: int
    updated_replicas: int
    generation: int
    observed_generation: int
    conditions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "namespace": self.namespace,
            "name": self.name,
            "desired_replicas": self.desired_replicas,
            "available_replicas": self.available_replicas,
            "unavailable_replicas": self.unavailable_replicas,
            "updated_replicas": self.updated_replicas,
            "generation": self.generation,
            "observed_generation": self.observed_generation,
            "conditions": list(self.conditions),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> DrilldownRolloutStatus:
        if not isinstance(raw, Mapping):
            raise ValueError("rollout entry must be a mapping")
        def _to_int(key: str) -> int:
            return _int_or_zero(raw.get(key))
        conditions_raw = raw.get("conditions")
        if isinstance(conditions_raw, Sequence):
            conds = tuple(str(item) for item in conditions_raw)
        else:
            conds = ()
        return cls(
            kind=str(raw.get("kind") or ""),
            namespace=str(raw.get("namespace") or ""),
            name=str(raw.get("name") or ""),
            desired_replicas=_to_int("desired_replicas"),
            available_replicas=_to_int("available_replicas"),
            unavailable_replicas=_to_int("unavailable_replicas"),
            updated_replicas=_to_int("updated_replicas"),
            generation=_to_int("generation"),
            observed_generation=_to_int("observed_generation"),
            conditions=conds,
        )


@dataclass(frozen=True)
class DrilldownEvidence:
    warning_events: tuple[WarningEventSummary, ...]
    non_running_pods: tuple[DrilldownPod, ...]
    pod_descriptions: dict[str, str]
    rollouts: tuple[DrilldownRolloutStatus, ...]
    affected_namespaces: tuple[str, ...]
    affected_workloads: tuple[dict[str, Any], ...]
    summary: dict[str, Any]
    collection_timestamps: dict[str, str]
    pattern_details: dict[str, str] = field(default_factory=dict)
    image_pull_secret_insights: tuple[dict[str, Any], ...] = field(default_factory=tuple)


@dataclass
class DrilldownCollector:
    max_warning_events: int = 10
    max_non_running_pods: int = 8
    max_pod_descriptions: int = 3
    max_rollout_namespaces: int = 3
    max_rollouts: int = 8
    command_runner: Callable[[Sequence[str]], str] | None = None
    _PATTERN_COMMAND_TEMPLATES: ClassVar[dict[str, list[Sequence[str]]]] = {
        "probe_failure": [
            ("get", "pods", "-n", "{namespace}", "-o", "wide"),
            ("describe", "pods", "-n", "{namespace}"),
        ],
        "failed_scheduling": [
            ("describe", "pods", "-n", "{namespace}"),
            ("describe", "nodes"),
            ("get", "nodes", "-o", "wide"),
        ],
        "missing_metrics": [
            ("get", "hpa", "-n", "{namespace}"),
            ("get", "deployment", "metrics-server", "-n", "kube-system"),
            ("get", "pods", "-n", "kube-system", "-l", "k8s-app=metrics-server"),
        ],
        "pvc_pending": [
            ("get", "pvc", "-n", "{namespace}"),
            ("describe", "pvc", "-n", "{namespace}"),
        ],
        "ingress_timeout": [
            ("get", "ingress", "-n", "{namespace}"),
            ("get", "endpoints", "-n", "{namespace}"),
            ("describe", "svc", "-n", "{namespace}"),
        ],
    }
    _PATTERN_DEFAULT_NAMESPACE: ClassVar[dict[str, str]] = {
        "probe_failure": "default",
        "failed_scheduling": "default",
        "missing_metrics": "kube-system",
        "pvc_pending": "default",
        "ingress_timeout": "default",
    }

    def __post_init__(self) -> None:
        if self.command_runner is None:
            self._runner: Callable[[Sequence[str]], str] = _run_command
        else:
            self._runner = self.command_runner

    def collect(
        self,
        context: str,
        namespaces: Sequence[str],
        image_pull_secret_insight: ImagePullSecretInsight | None = None,
        pattern_reasons: Sequence[str] | None = None,
        pattern_metadata: Mapping[str, Sequence[str]] | None = None,
    ) -> DrilldownEvidence:
        warning_events = self._collect_warning_events(context, limit=self.max_warning_events)
        non_running = self._collect_non_running_pods(context, limit=self.max_non_running_pods)
        described = self._describe_pods(context, non_running[: self.max_pod_descriptions])
        candidate_namespaces = self._make_namespace_list(namespaces, warning_events, non_running)
        rollout_entries = self._collect_rollout_status(
            context,
            candidate_namespaces,
            limit=self.max_rollouts,
        )
        summary = {
            "warning_events": len(warning_events),
            "non_running_pods": len(non_running),
            "pod_descriptions": len(described),
            "rollout_entries": len(rollout_entries),
            "image_pull_secret_insights": 1 if image_pull_secret_insight else 0,
        }
        pattern_details = self._collect_pattern_details(context, pattern_reasons, pattern_metadata)
        summary["pattern_details"] = len(pattern_details)
        affected_workloads = tuple(
            {"kind": "Pod", "namespace": pod.namespace, "name": pod.name, "phase": pod.phase, "reason": pod.reason}
            for pod in non_running
        )
        affected_workloads += tuple(entry.to_dict() for entry in rollout_entries)
        collection_timestamps = {
            "warning_events": _now_iso(),
            "pods": _now_iso(),
            "rollouts": _now_iso(),
            "image_pull_secret_insight": _now_iso(),
        }
        return DrilldownEvidence(
            warning_events=warning_events,
            non_running_pods=non_running,
            pod_descriptions=described,
            rollouts=tuple(rollout_entries),
            affected_namespaces=tuple(candidate_namespaces),
            affected_workloads=affected_workloads,
            summary=summary,
            collection_timestamps=collection_timestamps,
            pattern_details=pattern_details,
            image_pull_secret_insights=(image_pull_secret_insight.to_dict(),)
            if image_pull_secret_insight
            else (),
        )

    def _kubectl(self, context: str, *args: str) -> str:
        return self._runner(["kubectl", *args, "--context", context])

    def _collect_warning_events(
        self, context: str, limit: int
    ) -> tuple[WarningEventSummary, ...]:
        try:
            output = self._kubectl(
                context,
                "get",
                "events",
                "--all-namespaces",
                "--field-selector",
                "type=Warning",
                "--sort-by=.metadata.creationTimestamp",
                "-o",
                "json",
            )
        except RuntimeError:
            return ()
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return ()
        items = sorted(
            _extract_items(payload),
            key=lambda event: str((event.get("metadata") or {}).get("creationTimestamp") or ""),
            reverse=True,
        )
        events: list[WarningEventSummary] = []
        for entry in items:
            if len(events) >= limit:
                break
            metadata = entry.get("metadata") or {}
            namespace = str(metadata.get("namespace") or "")
            reason = str(entry.get("reason") or "")
            message = str(entry.get("message") or "")
            last_seen = str(
                metadata.get("lastTimestamp")
                or metadata.get("eventTime")
                or metadata.get("creationTimestamp")
                or ""
            )
            events.append(
                WarningEventSummary(
                    namespace=namespace,
                    reason=reason,
                    message=message,
                    count=_int_or_zero(entry.get("count")),
                    last_seen=last_seen,
                )
            )
        return tuple(events)

    def _collect_non_running_pods(
        self, context: str, limit: int
    ) -> tuple[DrilldownPod, ...]:
        try:
            output = self._kubectl(context, "get", "pods", "--all-namespaces", "-o", "json")
        except RuntimeError:
            return ()
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return ()
        items = _extract_items(payload)
        pods: list[DrilldownPod] = []
        for entry in items:
            if len(pods) >= limit:
                break
            metadata = entry.get("metadata") or {}
            namespace = str(metadata.get("namespace") or "")
            name = str(metadata.get("name") or "")
            status = entry.get("status") or {}
            phase = str(status.get("phase") or "").lower()
            counted = phase and phase != "running"
            reason_text = phase
            container_statuses = status.get("containerStatuses") or []
            for container in container_statuses:
                for attr in ("state", "lastState"):
                    state = container.get(attr) or {}
                    waiting = state.get("waiting") or {}
                    waiting_reason = str(waiting.get("reason") or "")
                    if waiting_reason:
                        reason_text = waiting_reason
                        break
                if reason_text not in {"", phase}:
                    break
            if counted:
                pods.append(
                    DrilldownPod(
                        namespace=namespace,
                        name=name,
                        phase=phase or "unknown",
                        reason=reason_text or "non-running",
                    )
                )
        return tuple(pods)

    def _describe_pods(
        self, context: str, pods: Sequence[DrilldownPod]
    ) -> dict[str, str]:
        descriptions: dict[str, str] = {}
        for pod in pods:
            try:
                output = self._kubectl(
                    context,
                    "describe",
                    "pod",
                    pod.name,
                    "-n",
                    pod.namespace,
                )
            except RuntimeError as exc:
                descriptions[f"{pod.namespace}/{pod.name}"] = str(exc)
                continue
            descriptions[f"{pod.namespace}/{pod.name}"] = shorten(output, width=1200, placeholder="... (truncated)")
        return descriptions

    def _collect_rollout_status(
        self, context: str, namespaces: Sequence[str], limit: int
    ) -> list[DrilldownRolloutStatus]:
        entries: list[DrilldownRolloutStatus] = []
        for namespace in namespaces:
            if len(entries) >= limit:
                break
            deployments = self._collect_resource_status(context, namespace, "deployments", limit - len(entries))
            entries.extend(deployments)
            if len(entries) >= limit:
                break
            statefulsets = self._collect_resource_status(context, namespace, "statefulsets", limit - len(entries))
            entries.extend(statefulsets)
        return entries

    def _collect_resource_status(
        self, context: str, namespace: str, resource: str, limit: int
    ) -> list[DrilldownRolloutStatus]:
        try:
            output = self._kubectl(context, "get", resource, "-n", namespace, "-o", "json")
        except RuntimeError:
            return []
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return []
        items = _extract_items(payload)
        results: list[DrilldownRolloutStatus] = []
        for entry in items:
            if len(results) >= limit:
                break
            metadata = entry.get("metadata") or {}
            status = entry.get("status") or {}
            spec = entry.get("spec") or {}
            name = str(metadata.get("name") or "")
            kind = resource.capitalize()
            desired = _int_or_zero(spec.get("replicas"))
            available = _int_or_zero(status.get("availableReplicas"))
            unavailable = _int_or_zero(status.get("unavailableReplicas"))
            updated = _int_or_zero(status.get("updatedReplicas"))
            generation = _int_or_zero(metadata.get("generation"))
            observed = _int_or_zero(status.get("observedGeneration"))
            conditions: tuple[str, ...] = ()
            condition_items = status.get("conditions") or []
            if isinstance(condition_items, list):
                conditions = tuple(
                    f"{str(condition.get('type'))}={str(condition.get('status'))}" for condition in condition_items if isinstance(condition, Mapping)
                )
            results.append(
                DrilldownRolloutStatus(
                    kind=kind,
                    namespace=namespace,
                    name=name,
                    desired_replicas=desired,
                    available_replicas=available,
                    unavailable_replicas=unavailable,
                    updated_replicas=updated,
                    generation=generation,
                    observed_generation=observed,
                    conditions=conditions,
                )
            )
        return results

    def _collect_pattern_details(
        self,
        context: str,
        pattern_reasons: Sequence[str] | None,
        pattern_metadata: Mapping[str, Sequence[str]] | None,
    ) -> dict[str, str]:
        details: dict[str, str] = {}
        if not pattern_reasons:
            return details
        metadata = pattern_metadata or {}
        for reason in dict.fromkeys(pattern_reasons):
            commands = self._commands_for_reason(reason, metadata.get(reason))
            if not commands:
                continue
            outputs: list[str] = []
            for command in commands:
                try:
                    output = self._kubectl(context, *command)
                except RuntimeError as exc:
                    outputs.append(f"error: {exc}")
                    continue
                outputs.append(shorten(output, width=800, placeholder="... (truncated)"))
            if outputs:
                details[reason] = "\n".join(outputs)
        return details

    def _commands_for_reason(
        self, reason: str, namespaces: Sequence[str] | None
    ) -> list[Sequence[str]]:
        templates = self._PATTERN_COMMAND_TEMPLATES.get(reason)
        if not templates:
            return []
        namespace = self._namespace_for_reason(reason, namespaces)
        commands: list[Sequence[str]] = []
        for template in templates:
            commands.append(
                tuple(
                    namespace if token == "{namespace}" else token
                    for token in template
                )
            )
        return commands

    def _namespace_for_reason(
        self, reason: str, namespaces: Sequence[str] | None
    ) -> str:
        if namespaces:
            for namespace in namespaces:
                if namespace:
                    return namespace
        return self._PATTERN_DEFAULT_NAMESPACE.get(reason, "default")

    def _make_namespace_list(
        self,
        namespaces: Sequence[str],
        events: Sequence[WarningEventSummary],
        pods: Sequence[DrilldownPod],
    ) -> list[str]:
        candidates = []
        for ns in namespaces:
            if ns and ns not in candidates:
                candidates.append(ns)
        for event in events:
            if event.namespace and event.namespace not in candidates:
                candidates.append(event.namespace)
        for pod in pods:
            if pod.namespace and pod.namespace not in candidates:
                candidates.append(pod.namespace)
        return candidates[: self.max_rollout_namespaces]


@dataclass(frozen=True)
class DrilldownArtifact:
    run_label: str
    run_id: str
    timestamp: datetime
    snapshot_timestamp: datetime
    context: str
    label: str
    cluster_id: str
    trigger_reasons: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    evidence_summary: dict[str, Any]
    affected_namespaces: tuple[str, ...]
    affected_workloads: tuple[dict[str, Any], ...]
    warning_events: tuple[WarningEventSummary, ...]
    non_running_pods: tuple[DrilldownPod, ...]
    pod_descriptions: dict[str, str]
    rollout_status: tuple[DrilldownRolloutStatus, ...]
    collection_timestamps: dict[str, str]
    image_pull_secret_insight: ImagePullSecretInsight | None = None
    pattern_details: dict[str, str] = field(default_factory=dict)
    artifact_path: str | None = None
    artifact_id: str | None = None  # Immutable artifact instance identity (UUIDv7); None for legacy artifacts

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "run_label": self.run_label,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "snapshot_timestamp": self.snapshot_timestamp.isoformat(),
            "context": self.context,
            "label": self.label,
            "cluster_id": self.cluster_id,
            "trigger_reasons": list(self.trigger_reasons),
            "missing_evidence": list(self.missing_evidence),
            "evidence_summary": self.evidence_summary,
            "affected_namespaces": list(self.affected_namespaces),
            "affected_workloads": list(self.affected_workloads),
            "warning_events": [event.to_dict() for event in self.warning_events],
            "non_running_pods": [pod.to_dict() for pod in self.non_running_pods],
            "pod_descriptions": self.pod_descriptions,
            "rollout_status": [entry.to_dict() for entry in self.rollout_status],
            "collection_timestamps": self.collection_timestamps,
            "pattern_details": self.pattern_details,
            "image_pull_secret_insight": self.image_pull_secret_insight.to_dict()
            if self.image_pull_secret_insight
            else None,
        }
        if self.artifact_path:
            data["artifact_path"] = self.artifact_path
        # Include artifact_id when present (backward compat: legacy artifacts without it)
        if self.artifact_id is not None:
            data["artifact_id"] = self.artifact_id
        return data

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> DrilldownArtifact:
        if not isinstance(raw, Mapping):
            raise ValueError("drilldown artifact must be an object")
        def _as_tuple(value: Any, path: str) -> tuple[Any, ...]:
            if isinstance(value, Sequence) and not isinstance(value, str | bytes):
                return tuple(value)
            raise ValueError(f"{path} expected a list")

        def _parse_datetime(value: Any, path: str) -> datetime:
            """Parse timestamp with UTC normalization for safe comparisons."""
            if not isinstance(value, str):
                raise ValueError(f"{path} expected a timestamp string")
            parsed = parse_iso_to_utc(value)
            if parsed is None:
                raise ValueError(f"{path} expected a valid ISO timestamp string")
            return parsed

        warning_raw = raw.get("warning_events", [])
        warnings: list[WarningEventSummary] = []
        if isinstance(warning_raw, Sequence):
            for entry in warning_raw:
                if isinstance(entry, Mapping):
                    warnings.append(WarningEventSummary.from_dict(entry))
        pod_raw = raw.get("non_running_pods", [])
        pods: list[DrilldownPod] = []
        if isinstance(pod_raw, Sequence):
            for entry in pod_raw:
                if isinstance(entry, Mapping):
                    pods.append(DrilldownPod.from_dict(entry))
        rollout_raw = raw.get("rollout_status", [])
        rollouts: list[DrilldownRolloutStatus] = []
        if isinstance(rollout_raw, Sequence):
            for entry in rollout_raw:
                if isinstance(entry, Mapping):
                    rollouts.append(DrilldownRolloutStatus.from_dict(entry))
        pattern_details_raw = raw.get("pattern_details", {})
        pattern_details: dict[str, str] = {}
        if isinstance(pattern_details_raw, Mapping):
            for key, value in pattern_details_raw.items():
                pattern_details[str(key)] = str(value)
        insight_raw = raw.get("image_pull_secret_insight")
        if isinstance(insight_raw, Mapping):
            insight_value = ImagePullSecretInsight.from_dict(insight_raw)
        else:
            insight_value = None
        return cls(
            run_label=str(raw.get("run_label") or ""),
            run_id=str(raw.get("run_id") or ""),
            timestamp=_parse_datetime(raw.get("timestamp"), "timestamp"),
            snapshot_timestamp=_parse_datetime(raw.get("snapshot_timestamp"), "snapshot_timestamp"),
            context=str(raw.get("context") or ""),
            label=str(raw.get("label") or ""),
            cluster_id=str(raw.get("cluster_id") or ""),
            trigger_reasons=tuple(str(item) for item in _as_tuple(raw.get("trigger_reasons", []), "trigger_reasons")),
            missing_evidence=tuple(str(item) for item in _as_tuple(raw.get("missing_evidence", []), "missing_evidence")),
            evidence_summary=dict(raw.get("evidence_summary") or {}),
            affected_namespaces=tuple(str(item) for item in _as_tuple(raw.get("affected_namespaces", []), "affected_namespaces")),
            affected_workloads=tuple(dict(item) for item in _as_tuple(raw.get("affected_workloads", []), "affected_workloads")),
            warning_events=tuple(warnings),
            non_running_pods=tuple(pods),
            pod_descriptions={
                str(key): str(value) for key, value in (raw.get("pod_descriptions") or {}).items()
            },
            rollout_status=tuple(rollouts),
            collection_timestamps={
                str(key): str(value) for key, value in (raw.get("collection_timestamps") or {}).items()
            },
            pattern_details=pattern_details,
            image_pull_secret_insight=insight_value,
            artifact_id=str(raw.get("artifact_id")) if raw.get("artifact_id") else None,
            artifact_path=str(raw.get("artifact_path")) if raw.get("artifact_path") else None,
        )
