"""Targeted drilldown helpers for health loop diagnostics."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from textwrap import shorten
from typing import ClassVar

from ..collect.cluster_snapshot import WarningEventSummary
from ..security.kubectl_subprocess import (
    run_kubectl,
)
from .drilldown_models import (
    DrilldownArtifact,
    DrilldownEvidence,
    DrilldownPod,
    DrilldownRolloutStatus,
    _extract_items,
    _int_or_zero,
    _now_iso,
)
from .image_pull_secret import KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS, ImagePullSecretInsight

# Re-export for backward compatibility
__all__ = [
    "DrilldownArtifact",
    "DrilldownCollector",
    "DrilldownEvidence",
    "DrilldownPod",
    "DrilldownRolloutStatus",
]


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
        """Build and execute a kubectl command with validated context.

        Args:
            context: Kubernetes context name (validated), or "in-cluster" for service account auth
            *args: kubectl arguments

        Returns:
            Command output

        Raises:
            SecurityError: If context name is invalid
        """
        from ..security.kubectl_context import render_kubectl_context_args

        # Use render_kubectl_context_args() to safely handle in-cluster mode
        context_args = render_kubectl_context_args(context)
        return self._runner(["kubectl", *args, *context_args])

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


def _run_command(command: Sequence[str]) -> str:
    """Execute a kubectl command with bounded output and memory safety.

    This is the default command runner for DrilldownCollector when no
    custom runner is provided. It uses bounded kubectl execution to
    prevent memory growth from large collections.
    """
    return run_kubectl(
        command,
        timeout_seconds=KUBECTL_HEALTH_COMMAND_TIMEOUT_SECONDS,
    )
