"""Data models for drilldown artifacts and evidence."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..collect.cluster_snapshot import WarningEventSummary
from ..datetime_utils import parse_iso_to_utc
from .image_pull_secret import ImagePullSecretInsight


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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
