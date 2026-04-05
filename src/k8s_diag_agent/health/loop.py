"""Per-cluster health assessment loop with trigger-aware comparisons."""
from __future__ import annotations

import json
import os
import re
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..collect.cluster_snapshot import ClusterSnapshot
from ..collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from ..compare.two_cluster import ClusterComparison, compare_snapshots
from ..models import (
    Assessment,
    ConfidenceLevel,
    Finding,
    Hypothesis,
    Layer,
    NextCheck,
    RecommendedAction,
    SafetyLevel,
    Signal,
)
from ..render.formatter import assessment_to_dict
from .baseline import BaselineDriftCategory, BaselinePolicy
from .drilldown import DrilldownArtifact, DrilldownCollector
from .utils import normalize_ref


_LABEL_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_HISTORY_FILENAME = "history.json"


def _safe_label(value: str) -> str:
    cleaned = _LABEL_RE.sub("-", value or "")
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned.lower() or "entry"



def _serialize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _write_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _format_snapshot_filename(run_id: str, label: str, captured_at: datetime) -> str:
    timestamp = captured_at.strftime("%Y%m%dT%H%M%SZ")
    safe_label = _safe_label(label)
    return f"{run_id}-{safe_label}-{timestamp}.json"


def _build_runtime_run_id(label: str) -> str:
    component = _safe_label(label)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{component}-{timestamp}"


def _watched_release_versions(
    snapshot: ClusterSnapshot, watched: Iterable[str]
) -> Dict[str, Optional[str]]:
    versions: Dict[str, Optional[str]] = {}
    for release_key in watched:
        release = snapshot.helm_releases.get(release_key)
        versions[release_key] = release.chart_version if release else None
    return versions


def _watched_crd_versions(
    snapshot: ClusterSnapshot, watched: Iterable[str]
) -> Dict[str, Optional[str]]:
    versions: Dict[str, Optional[str]] = {}
    for crd_name in watched:
        crd = snapshot.crds.get(crd_name)
        versions[crd_name] = crd.storage_version if crd else None
    return versions


class HealthRating(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class HealthTarget:
    context: str
    label: str
    monitor_health: bool
    watched_helm_releases: Tuple[str, ...]
    watched_crd_families: Tuple[str, ...]


@dataclass(frozen=True)
class ComparisonPeer:
    source: str
    peers: Tuple[str, ...]


@dataclass(frozen=True)
class ManualComparison:
    primary: str
    secondary: str


@dataclass(frozen=True)
class TriggerPolicy:
    control_plane_version: bool
    watched_helm_release: bool
    watched_crd: bool
    health_regression: bool
    missing_evidence: bool
    manual: bool
    warning_event_threshold: int = 3


@dataclass
class HealthHistoryEntry:
    cluster_id: str
    node_count: int
    pod_count: Optional[int]
    control_plane_version: str
    health_rating: HealthRating
    missing_evidence: Tuple[str, ...]
    watched_helm_releases: Dict[str, Optional[str]] = field(default_factory=dict)
    watched_crd_families: Dict[str, Optional[str]] = field(default_factory=dict)
    node_conditions: Dict[str, int] = field(default_factory=dict)
    pod_counts: Dict[str, int] = field(default_factory=dict)
    job_failures: int = 0
    warning_event_count: int = 0

    @classmethod
    def from_dict(cls, cluster_id: str, data: Dict[str, Any]) -> "HealthHistoryEntry":
        raw_helm = data.get("watched_helm_releases")
        if isinstance(raw_helm, dict):
            watched_helm = {
                str(key): str(value) if value is not None else None
                for key, value in raw_helm.items()
                if key
            }
        else:
            watched_helm = {}
        raw_crd = data.get("watched_crd_families")
        if isinstance(raw_crd, dict):
            watched_crds = {
                str(key): str(value) if value is not None else None
                for key, value in raw_crd.items()
                if key
            }
        else:
            watched_crds = {}
        node_condition_raw = data.get("node_conditions")
        if isinstance(node_condition_raw, dict):
            node_conditions = {
                str(key): int(value) if isinstance(value, int) else int(value or 0)
                for key, value in node_condition_raw.items()
                if key
            }
        else:
            node_conditions = {}
        pod_count_raw = data.get("pod_counts")
        if isinstance(pod_count_raw, dict):
            pod_counts = {
                str(key): int(value) if isinstance(value, int) else int(value or 0)
                for key, value in pod_count_raw.items()
                if key
            }
        else:
            pod_counts = {}
        return cls(
            cluster_id=cluster_id,
            node_count=int(data.get("node_count", 0)),
            pod_count=data.get("pod_count"),
            control_plane_version=str(data.get("control_plane_version") or ""),
            health_rating=HealthRating(data.get("health_rating", "healthy")),
            missing_evidence=tuple(data.get("missing_evidence", [])),
            watched_helm_releases=watched_helm,
            watched_crd_families=watched_crds,
            node_conditions=node_conditions,
            pod_counts=pod_counts,
            job_failures=_safe_int(data.get("job_failures")) or 0,
            warning_event_count=_safe_int(data.get("warning_event_count")) or 0,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_count": self.node_count,
            "pod_count": self.pod_count,
            "control_plane_version": self.control_plane_version,
            "health_rating": self.health_rating.value,
            "missing_evidence": list(self.missing_evidence),
            "watched_helm_releases": self.watched_helm_releases,
            "watched_crd_families": self.watched_crd_families,
            "node_conditions": self.node_conditions,
            "pod_counts": self.pod_counts,
            "job_failures": self.job_failures,
            "warning_event_count": self.warning_event_count,
        }


@dataclass
class HealthAssessmentResult:
    assessment: Assessment
    rating: HealthRating
    missing_evidence: Tuple[str, ...]
    node_count: int
    pod_count: Optional[int]
    control_plane_version: str


@dataclass
class HealthAssessmentArtifact:
    run_label: str
    run_id: str
    timestamp: datetime
    context: str
    label: str
    cluster_id: str
    snapshot_path: str
    assessment: Dict[str, Any]
    missing_evidence: Tuple[str, ...]
    health_rating: HealthRating
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_label": self.run_label,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "label": self.label,
            "cluster_id": self.cluster_id,
            "snapshot_path": self.snapshot_path,
            "assessment": self.assessment,
            "missing_evidence": list(self.missing_evidence),
            "health_rating": self.health_rating.value,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class TriggerDetail:
    type: str
    reason: str
    baseline_expectation: Optional[str]
    actual_value: str
    previous_run_value: Optional[str]
    why: str
    next_check: Optional[str]
    peer_roles: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": self.type,
            "reason": self.reason,
            "baseline_expectation": self.baseline_expectation,
            "actual_value": self.actual_value,
            "previous_run_value": self.previous_run_value,
            "why": self.why,
            "next_check": self.next_check,
        }
        if self.peer_roles:
            data["peer_roles"] = self.peer_roles
        return data


@dataclass
class ComparisonTriggerArtifact:
    run_label: str
    run_id: str
    timestamp: datetime
    primary: str
    secondary: str
    primary_label: str
    secondary_label: str
    trigger_reasons: Tuple[str, ...]
    comparison_summary: Dict[str, int]
    differences: Dict[str, Dict[str, Any]]
    trigger_details: Tuple[TriggerDetail, ...]
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_label": self.run_label,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "primary": self.primary,
            "secondary": self.secondary,
            "primary_label": self.primary_label,
            "secondary_label": self.secondary_label,
            "trigger_reasons": list(self.trigger_reasons),
            "comparison_summary": self.comparison_summary,
            "differences": self.differences,
            "trigger_details": [detail.to_dict() for detail in self.trigger_details],
            "notes": self.notes,
        }


@dataclass
class HealthRunConfig:
    run_label: str
    output_dir: Path
    collector_version: str
    targets: Tuple[HealthTarget, ...]
    peers: Tuple[ComparisonPeer, ...]
    trigger_policy: TriggerPolicy
    manual_pairs: Tuple[ManualComparison, ...]
    baseline_policy: BaselinePolicy

    @classmethod
    def load(cls, path: Path) -> "HealthRunConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw_label = raw.get("run_label")
        legacy_run_id = raw.get("run_id")
        if raw_label is not None:
            label_source = str(raw_label)
        elif legacy_run_id is not None:
            label_source = str(legacy_run_id)
            warnings.warn(
                "The health config key 'run_id' is deprecated. "
                "Provide 'run_label' instead; the legacy value will be used as the stable label while each execution generates a unique run_id.",
                DeprecationWarning,
                stacklevel=2,
            )
        else:
            label_source = path.stem
        run_label = _safe_label(label_source)
        output_dir = Path(str(raw.get("output_dir") or "runs"))
        collector_version = str(raw.get("collector_version") or "dev")

        targets_raw = raw.get("targets")
        if not isinstance(targets_raw, list):
            raise ValueError("`targets` must be a list")
        targets: List[HealthTarget] = []
        for entry in targets_raw:
            if not isinstance(entry, dict):
                continue
            context = entry.get("context")
            if not context:
                continue
            label = _safe_label(str(entry.get("label") or context))
            monitor_health = bool(entry.get("monitor_health", True))
            watched_helm = tuple(
                str(item).strip()
                for item in entry.get("watched_helm_releases") or []
                if str(item).strip()
            )
            watched_crd = tuple(
                str(item).strip()
                for item in entry.get("watched_crd_families") or []
                if str(item).strip()
            )
            targets.append(
                HealthTarget(
                    context=str(context),
                    label=label,
                    monitor_health=monitor_health,
                    watched_helm_releases=watched_helm,
                    watched_crd_families=watched_crd,
                )
            )
        if not targets:
            raise ValueError("`targets` must include at least one entry")

        references: Set[str] = set()
        for target in targets:
            references.add(normalize_ref(target.context))
            references.add(normalize_ref(target.label))

        manual_raw = raw.get("manual_pairs") or []
        manual_pairs: List[ManualComparison] = []
        for entry in manual_raw:
            if not isinstance(entry, dict):
                continue
            primary = entry.get("primary")
            secondary = entry.get("secondary")
            if not primary or not secondary:
                continue
            normalized_primary = normalize_ref(str(primary))
            normalized_secondary = normalize_ref(str(secondary))
            if normalized_primary not in references or normalized_secondary not in references:
                raise ValueError("Manual pair references unknown cluster")
            manual_pairs.append(
                ManualComparison(primary=normalized_primary, secondary=normalized_secondary)
            )

        peers_raw = raw.get("peer_mappings")
        if peers_raw is None:
            peers_raw = []
        if not isinstance(peers_raw, list):
            raise ValueError("`peer_mappings` must be a list")
        peers: List[ComparisonPeer] = []
        for entry in peers_raw:
            if not isinstance(entry, dict):
                continue
            source = entry.get("source")
            if not source:
                continue
            normalized_source = normalize_ref(str(source))
            if normalized_source not in references:
                raise ValueError(f"Unknown peer source: {source}")
            peers_list = entry.get("peers")
            if not isinstance(peers_list, list):
                continue
            normalized_peers: List[str] = []
            for item in peers_list:
                if not item:
                    continue
                normalized_peer = normalize_ref(str(item))
                if normalized_peer not in references:
                    raise ValueError(f"Unknown peer target: {item}")
                normalized_peers.append(normalized_peer)
            if not normalized_peers:
                continue
            peers.append(
                ComparisonPeer(
                    source=normalized_source,
                    peers=tuple(normalized_peers),
                )
            )
        if not peers and manual_pairs:
            raise ValueError("`peer_mappings` must define at least one group")

        trigger_raw = raw.get("comparison_triggers") or {}
        trigger_policy = TriggerPolicy(
            control_plane_version=bool(trigger_raw.get("control_plane_version", True)),
            watched_helm_release=bool(trigger_raw.get("watched_helm_release", True)),
            watched_crd=bool(trigger_raw.get("watched_crd", True)),
            health_regression=bool(trigger_raw.get("health_regression", True)),
            missing_evidence=bool(trigger_raw.get("missing_evidence", True)),
            manual=bool(trigger_raw.get("manual", True)),
            warning_event_threshold=_parse_threshold(trigger_raw.get("warning_event_threshold")),
        )

        baseline_raw = raw.get("baseline_policy_path")
        if baseline_raw:
            baseline_path = Path(str(baseline_raw))
            if not baseline_path.is_absolute():
                baseline_path = path.parent / baseline_path
        else:
            baseline_path = path.parent / "health-baseline.json"
        try:
            baseline_policy = BaselinePolicy.load_from_file(baseline_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Unable to load baseline policy {baseline_path}: {exc}")

        return cls(
            run_label=run_label,
            output_dir=output_dir,
            collector_version=collector_version,
            targets=tuple(targets),
            peers=tuple(peers),
            trigger_policy=trigger_policy,
            manual_pairs=tuple(manual_pairs),
            baseline_policy=baseline_policy,
        )


class _SignalIdGenerator:
    def __init__(self, label: str) -> None:
        self._label = _safe_label(label)
        self._counter = 0

    def next_id(self) -> str:
        self._counter += 1
        return f"health-{self._label}-sig-{self._counter:02d}"


def build_health_assessment(
    snapshot: ClusterSnapshot,
    target: HealthTarget,
    previous: Optional[HealthHistoryEntry],
    baseline: BaselinePolicy,
    warning_event_threshold: int = 0,
) -> HealthAssessmentResult:
    generator = _SignalIdGenerator(target.label)
    signals: List[Signal] = []
    evidence_id = snapshot.metadata.cluster_id
    status = snapshot.collection_status
    missing = tuple(status.missing_evidence)
    issues_detected = False
    issue_findings: List[Finding] = []
    health_signals = snapshot.health_signals
    node_conditions = health_signals.node_conditions
    pod_counts = health_signals.pod_counts
    job_failures = health_signals.job_failures
    warning_events = health_signals.warning_events

    def add_signal(description: str, severity: str, layer: Layer) -> Signal:
        signal = Signal(
            id=generator.next_id(),
            description=description,
            layer=layer,
            evidence_id=evidence_id,
            severity=severity,
        )
        signals.append(signal)
        return signal

    def record_finding(description: str, layer: Layer, signal_ids: Sequence[str]) -> None:
        if not signal_ids:
            return
        issue_findings.append(
            Finding(
                id=generator.next_id(),
                description=description,
                supporting_signals=list(signal_ids),
                layer=layer,
            )
        )

    def _record_issue(description: str, severity: str, layer: Layer) -> Signal:
        signal = add_signal(description, severity, layer)
        record_finding(description, layer, [signal.id])
        return signal

    add_signal("Snapshot captured with available telemetry.", "low", Layer.OBSERVABILITY)
    if status.helm_error:
        issues_detected = True
        signal = add_signal(
            f"Helm collection reported an error ({status.helm_error}).",
            "high",
            Layer.OBSERVABILITY,
        )
        record_finding(
            f"Helm collection reported an error ({status.helm_error}).",
            Layer.OBSERVABILITY,
            [signal.id],
        )
    missing_signal_ids: List[str] = []
    missing_signal_map: Dict[str, str] = {}
    baseline_next_checks: List[NextCheck] = []
    baseline_reasons: List[str] = []
    references: List[str] = []
    for missing_item in missing:
        issues_detected = True
        signal = add_signal(
            f"Missing evidence: {missing_item}.",
            "medium",
            Layer.OBSERVABILITY,
        )
        missing_signal_ids.append(signal.id)
        missing_signal_map[missing_item] = signal.id
    if missing_signal_ids:
        record_finding(
            f"Snapshot is missing telemetry: {', '.join(sorted(missing))}.",
            Layer.OBSERVABILITY,
            missing_signal_ids,
        )
        if previous:
            prev_missing = set(previous.missing_evidence)
            new_missing = sorted(set(missing) - prev_missing)
            new_signal_ids = [missing_signal_map[item] for item in new_missing if item in missing_signal_map]
            if new_missing and new_signal_ids:
                record_finding(
                    f"New missing telemetry since last run: {', '.join(new_missing)}.",
                    Layer.OBSERVABILITY,
                    new_signal_ids,
                )
    control_plane_version = snapshot.metadata.control_plane_version or "unknown"
    has_control_plane_version = bool(control_plane_version.strip()) and control_plane_version.lower() != "unknown"
    if not has_control_plane_version:
        issues_detected = True
        signal = add_signal(
            "Control plane version is missing or unknown.",
            "medium",
            Layer.ROLLOUT,
        )
        record_finding(
            "Control plane version is missing or unknown.",
            Layer.ROLLOUT,
            [signal.id],
        )
    control_plane_expectation = baseline.control_plane_expectation
    if (
        control_plane_expectation
        and has_control_plane_version
        and not baseline.is_drift_allowed(BaselineDriftCategory.CONTROL_PLANE_VERSION)
        and not control_plane_expectation.allows(control_plane_version)
    ):
        issues_detected = True
        expectation_desc = control_plane_expectation.describe()
        signal = add_signal(
            f"Control plane version {control_plane_version} falls outside baseline ({expectation_desc}).",
            "medium",
            Layer.ROLLOUT,
        )
        record_finding(
            (
                f"Control plane version {control_plane_version} violates the baseline expectation ({expectation_desc}). "
                f"{control_plane_expectation.why}"
            ),
            Layer.ROLLOUT,
            [signal.id],
        )
        baseline_next_checks.append(
            NextCheck(
                description=control_plane_expectation.next_check,
                owner="platform engineer",
                method="kubectl",
                evidence_needed=["control plane version"],
            )
        )
        baseline_reasons.append(control_plane_expectation.why)
        references.append("control plane baseline")
    if previous:
        previous_version = previous.control_plane_version or "unknown"
        if previous_version != control_plane_version:
            issues_detected = True
        signal = add_signal(
            f"Control plane version changed since last run ({previous_version} -> {control_plane_version}).",
            "medium",
            Layer.ROLLOUT,
        )
        record_finding(
            f"Control plane version changed since last run ({previous_version} -> {control_plane_version}).",
                Layer.ROLLOUT,
                [signal.id],
            )
    if previous and snapshot.metadata.node_count != previous.node_count:
        issues_detected = True
        signal = add_signal(
            f"Node count changed since last run ({previous.node_count} -> {snapshot.metadata.node_count}).",
            "medium",
            Layer.NODE,
        )
        record_finding(
            f"Node count changed since last run ({previous.node_count} -> {snapshot.metadata.node_count}).",
            Layer.NODE,
            [signal.id],
        )
    if previous and snapshot.metadata.pod_count != previous.pod_count:
        issues_detected = True
        prev_label = (
            str(previous.pod_count) if previous.pod_count is not None else "unknown"
        )
        curr_label = (
            str(snapshot.metadata.pod_count)
            if snapshot.metadata.pod_count is not None
            else "unknown"
        )
        signal = add_signal(
            f"Pod count changed since last run ({prev_label} -> {curr_label}).",
            "medium",
            Layer.WORKLOAD,
        )
        record_finding(
            f"Pod count changed since last run ({prev_label} -> {curr_label}).",
            Layer.WORKLOAD,
            [signal.id],
        )

    watched_release_versions = _watched_release_versions(
        snapshot, target.watched_helm_releases
    )
    watched_crd_versions = _watched_crd_versions(
        snapshot, target.watched_crd_families
    )
    if (
        baseline.release_policies
        and not baseline.is_drift_allowed(BaselineDriftCategory.WATCHED_HELM_RELEASE)
    ):
        for release_key in sorted(target.watched_helm_releases):
            policy = baseline.release_policy(release_key)
            if not policy:
                continue
            current_version = watched_release_versions.get(release_key)
            if policy.allows(current_version):
                continue
            issues_detected = True
            actual_label = current_version if current_version is not None else "missing"
            expectation_desc = policy.describe()
            signal = add_signal(
                (
                    f"Watched Helm release {release_key} ({actual_label}) "
                    f"violates baseline policy ({expectation_desc})."
                ),
                "medium",
                Layer.ROLLOUT,
            )
            record_finding(
                (
                    f"Watched Helm release {release_key} reported {actual_label} but baseline requires {expectation_desc}. "
                    f"{policy.why}"
                ),
                Layer.ROLLOUT,
                [signal.id],
            )
            baseline_next_checks.append(
                NextCheck(
                    description=policy.next_check,
                    owner="platform engineer",
                    method="helm",
                    evidence_needed=[f"Helm release {release_key}"],
                )
            )
            baseline_reasons.append(policy.why)
            references.append(f"baseline release {release_key}")
    if (
        baseline.required_crds
        and not baseline.is_drift_allowed(BaselineDriftCategory.WATCHED_CRD)
    ):
        for family, crd_policy in baseline.required_crds.items():
            if snapshot.crds.get(family):
                continue
            issues_detected = True
            signal = add_signal(
                f"Required CRD family {family} is missing from the snapshot.",
                "medium",
                Layer.STORAGE,
            )
            record_finding(
                (
                    f"Baseline expects CRD family {family} to exist. {crd_policy.why}"
                ),
                Layer.STORAGE,
                [signal.id],
            )
            baseline_next_checks.append(
                NextCheck(
                    description=crd_policy.next_check,
                    owner="platform engineer",
                    method="kubectl",
                    evidence_needed=[f"CRD {family}"],
                )
            )
            baseline_reasons.append(crd_policy.why)
            references.append(f"baseline CRD {family}")
    if previous:
        previous_release_versions = previous.watched_helm_releases
        for release_key in sorted(
            set(watched_release_versions) | set(previous_release_versions)
        ):
            release_current_version: Optional[str] = watched_release_versions.get(release_key)
            release_previous_version: Optional[str] = previous_release_versions.get(release_key)
            if release_current_version == release_previous_version:
                continue
            issues_detected = True
            release_prev_label: str = (
                release_previous_version if release_previous_version is not None else "missing"
            )
            release_curr_label: str = (
                release_current_version if release_current_version is not None else "missing"
            )
            signal = add_signal(
                f"Watched Helm release {release_key} changed since last run ({release_prev_label} -> {release_curr_label}).",
                "medium",
                Layer.ROLLOUT,
            )
            record_finding(
                f"Watched Helm release {release_key} changed since last run ({release_prev_label} -> {release_curr_label}).",
                Layer.ROLLOUT,
                [signal.id],
            )
        previous_crd_versions = previous.watched_crd_families
        for crd_key in sorted(
            set(watched_crd_versions) | set(previous_crd_versions)
        ):
            crd_current_version: Optional[str] = watched_crd_versions.get(crd_key)
            crd_previous_version: Optional[str] = previous_crd_versions.get(crd_key)
            if crd_current_version == crd_previous_version:
                continue
            issues_detected = True
            crd_prev_label: str = (
                crd_previous_version if crd_previous_version is not None else "missing"
            )
            crd_curr_label: str = (
                crd_current_version if crd_current_version is not None else "missing"
            )
            signal = add_signal(
                f"Watched CRD {crd_key} storage version changed since last run ({crd_prev_label} -> {crd_curr_label}).",
                "medium",
                Layer.ROLLOUT,
            )
            record_finding(
                f"Watched CRD {crd_key} storage version changed since last run ({crd_prev_label} -> {crd_curr_label}).",
                Layer.ROLLOUT,
                [signal.id],
            )

    workload_issue_present = False
    node_issue_present = False
    warning_event_count = len(warning_events)
    warning_threshold = warning_event_threshold
    warning_triggered = (
        warning_event_count > 0
        if warning_threshold <= 0
        else warning_event_count >= warning_threshold
    )
    node_components: List[str] = []
    node_severity = "medium"
    if node_conditions.not_ready > 0:
        node_components.append(f"{node_conditions.not_ready} nodes NotReady")
        node_severity = "high"
    if node_conditions.memory_pressure:
        node_components.append(f"{node_conditions.memory_pressure} nodes with MemoryPressure")
    if node_conditions.disk_pressure:
        node_components.append(f"{node_conditions.disk_pressure} nodes with DiskPressure")
    if node_conditions.pid_pressure:
        node_components.append(f"{node_conditions.pid_pressure} nodes with PIDPressure")
    if node_conditions.network_unavailable:
        node_components.append(f"{node_conditions.network_unavailable} nodes with NetworkUnavailable")
    if node_components:
        node_issue_present = True
        issues_detected = True
        references.append("node health")
        _record_issue(
            f"Node health signals: {', '.join(node_components)}.",
            node_severity,
            Layer.NODE,
        )
    if pod_counts.non_running > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("pod readiness")
        _record_issue(
            f"{pod_counts.non_running} pods are not running.",
            "medium",
            Layer.WORKLOAD,
        )
    if pod_counts.pending > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("pod scheduling")
        _record_issue(
            f"{pod_counts.pending} pods are pending scheduling.",
            "medium",
            Layer.WORKLOAD,
        )
    if pod_counts.crash_loop_backoff > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("CrashLoopBackOff")
        _record_issue(
            f"{pod_counts.crash_loop_backoff} pods in CrashLoopBackOff.",
            "high",
            Layer.WORKLOAD,
        )
    if pod_counts.image_pull_backoff > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("ImagePullBackOff")
        _record_issue(
            f"{pod_counts.image_pull_backoff} pods in ImagePullBackOff.",
            "high",
            Layer.WORKLOAD,
        )
    if job_failures > 0:
        workload_issue_present = True
        issues_detected = True
        references.append("job failures")
        _record_issue(
            f"{job_failures} failed job(s) observed.",
            "medium",
            Layer.WORKLOAD,
        )
    if warning_triggered:
        workload_issue_present = True
        issues_detected = True
        latest_warning = warning_events[0]
        warning_desc = (
            f" {latest_warning.reason} in {latest_warning.namespace}"
            if latest_warning.namespace and latest_warning.reason
            else ""
        )
        references.append("warning events")
        threshold_note = (
            f" (threshold {warning_threshold})" if warning_threshold > 0 else ""
        )
        _record_issue(
            f"{warning_event_count} warning events recorded{threshold_note}{warning_desc}.",
            "low",
            Layer.OBSERVABILITY,
        )
    previous_node_conditions = previous.node_conditions if previous else {}
    previous_pod_metrics = previous.pod_counts if previous else {}
    previous_job_failures = previous.job_failures if previous else 0
    previous_warning_count = previous.warning_event_count if previous else 0
    def _check_regression(current: int, previous_value: int, description: str, layer: Layer) -> None:
        nonlocal issues_detected, workload_issue_present, node_issue_present
        if current > previous_value:
            issues_detected = True
            if layer == Layer.WORKLOAD:
                workload_issue_present = True
            elif layer == Layer.NODE:
                node_issue_present = True
            references.append("regression")
            _record_issue(description, "medium", layer)
    _check_regression(
        node_conditions.not_ready,
        previous_node_conditions.get("not_ready", 0),
        f"NotReady node count increased ({previous_node_conditions.get('not_ready', 0)} -> {node_conditions.not_ready}).",
        Layer.NODE,
    )
    _check_regression(
        pod_counts.non_running,
        previous_pod_metrics.get("non_running", 0),
        f"Non-running pods increased ({previous_pod_metrics.get('non_running', 0)} -> {pod_counts.non_running}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        pod_counts.pending,
        previous_pod_metrics.get("pending", 0),
        f"Pending pod count increased ({previous_pod_metrics.get('pending', 0)} -> {pod_counts.pending}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        pod_counts.crash_loop_backoff,
        previous_pod_metrics.get("crash_loop_backoff", 0),
        f"CrashLoopBackOff pods increased ({previous_pod_metrics.get('crash_loop_backoff', 0)} -> {pod_counts.crash_loop_backoff}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        pod_counts.image_pull_backoff,
        previous_pod_metrics.get("image_pull_backoff", 0),
        f"ImagePullBackOff pods increased ({previous_pod_metrics.get('image_pull_backoff', 0)} -> {pod_counts.image_pull_backoff}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        job_failures,
        previous_job_failures,
        f"Job failure count increased ({previous_job_failures} -> {job_failures}).",
        Layer.WORKLOAD,
    )
    _check_regression(
        warning_event_count,
        previous_warning_count,
        f"Warning events increased ({previous_warning_count} -> {warning_event_count}).",
        Layer.OBSERVABILITY,
    )

    def _pick_layer() -> Layer:
        ranking = {"high": 0, "medium": 1, "low": 2}
        best = min(signals, key=lambda signal: ranking.get(signal.severity, 2))
        return best.layer

    rating = HealthRating.DEGRADED if issues_detected else HealthRating.HEALTHY
    dominant_layer = _pick_layer()
    findings = [
        Finding(
            id=generator.next_id(),
            description=f"Health assessment for {target.label} is {rating.value}.",
            supporting_signals=[signal.id for signal in signals],
            layer=dominant_layer,
        )
    ]
    findings.extend(issue_findings)
    if issues_detected:
        baseline_note = "; ".join(dict.fromkeys(baseline_reasons))
        description = (
            f"Baseline policy violation: {baseline_note}"
            if baseline_note
            else (
                "Node/workload health signals or regressions suggest the cluster may be unstable."
                if node_issue_present or workload_issue_present
                else "Missing telemetry or version drift suggests the cluster may be unstable."
            )
        )
        hypotheses = [
            Hypothesis(
                id=generator.next_id(),
                description=description,
                confidence=ConfidenceLevel.MEDIUM,
                probable_layer=dominant_layer,
                what_would_falsify=(
                    "Nodes become ready, pods stay running, warning events quiet down, and Helm errors stay absent."
                    if node_issue_present or workload_issue_present
                    else "Telemetry gaps close and node/pod counts stabilize without Helm errors."
                ),
            )
        ]
        safety_level = SafetyLevel.LOW_RISK
    else:
        hypotheses = [
            Hypothesis(
                id=generator.next_id(),
                description="Telemetry is complete and no high-severity drift is observed.",
                confidence=ConfidenceLevel.HIGH,
                probable_layer=dominant_layer,
                what_would_falsify="A new control plane drift, missing evidence, or Helm error appears.",
            )
        ]
        safety_level = SafetyLevel.OBSERVE_ONLY

    next_checks: List[NextCheck] = []
    if missing:
        next_checks.append(
            NextCheck(
                description="Collect the missing telemetry referenced above.",
                owner="platform engineer",
                method="kubectl",
                evidence_needed=list(missing),
            )
        )
    else:
        next_checks.append(
            NextCheck(
                description="Review node, pod, and control plane status before taking action.",
                owner="platform engineer",
                method="kubectl",
                evidence_needed=["nodes", "pods", "control plane version"],
            )
        )
    if node_issue_present or workload_issue_present:
        next_checks.append(
            NextCheck(
                description="Investigate the flagged nodes, pods, jobs, and warning events.",
                owner="platform engineer",
                method="kubectl",
                evidence_needed=["nodes", "pods", "jobs", "events"],
            )
        )
    next_checks.extend(baseline_next_checks)

    if status.helm_error:
        references.append("helm collection error")
    if missing:
        references.append("missing evidence")
    if not references:
        references.append("routine health monitoring")

    assessment_action = RecommendedAction(
        type="observation",
        description="Track the observed signals before escalating to corrective actions.",
        references=references,
        safety_level=safety_level,
    )

    overall_confidence = ConfidenceLevel.MEDIUM if issues_detected else ConfidenceLevel.HIGH
    assessment = Assessment(
        observed_signals=signals,
        findings=findings,
        hypotheses=hypotheses,
        next_evidence_to_collect=next_checks,
        recommended_action=assessment_action,
        safety_level=safety_level,
        probable_layer_of_origin=dominant_layer,
        overall_confidence=overall_confidence,
    )
    return HealthAssessmentResult(
        assessment=assessment,
        rating=rating,
        missing_evidence=missing,
        node_count=snapshot.metadata.node_count,
        pod_count=snapshot.metadata.pod_count,
        control_plane_version=control_plane_version,
    )


@dataclass
class HealthSnapshotRecord:
    target: HealthTarget
    snapshot: ClusterSnapshot
    path: Path
    assessment: Optional[HealthAssessmentResult] = None

    def refs(self) -> Tuple[str, str]:
        return (normalize_ref(self.target.context), normalize_ref(self.target.label))


def determine_pair_trigger_reasons(
    primary: HealthSnapshotRecord,
    secondary: HealthSnapshotRecord,
    policy: TriggerPolicy,
    history: Dict[str, HealthHistoryEntry],
    manual_keys: Set[Tuple[str, str]],
    baseline: BaselinePolicy,
) -> List[TriggerDetail]:
    details: List[TriggerDetail] = []
    primary_ref, _ = primary.refs()
    secondary_ref, _ = secondary.refs()
    pair_key = (primary_ref, secondary_ref)

    def _peer_role_summary() -> Optional[str]:
        primary_role = baseline.role_for(primary_ref) or baseline.role_for(primary.target.label)
        secondary_role = baseline.role_for(secondary_ref) or baseline.role_for(secondary.target.label)
        if not primary_role and not secondary_role:
            return None
        summary_parts: List[str] = []
        summary_parts.append(
            f"{primary.target.label} ({primary_role})" if primary_role else primary.target.label
        )
        summary_parts.append(
            f"{secondary.target.label} ({secondary_role})" if secondary_role else secondary.target.label
        )
        return " vs ".join(summary_parts)

    role_summary = _peer_role_summary()

    def _format_previous_control_plane(cluster_id: str) -> str:
        prev = history.get(cluster_id)
        if not prev:
            return "unknown"
        return prev.control_plane_version or "unknown"

    def _format_previous_release(cluster_id: str, release_key: str) -> str:
        prev = history.get(cluster_id)
        if not prev:
            return "unknown"
        return prev.watched_helm_releases.get(release_key) or "missing"

    def _format_previous_crd(cluster_id: str, crd_key: str) -> str:
        prev = history.get(cluster_id)
        if not prev:
            return "unknown"
        return prev.watched_crd_families.get(crd_key) or "missing"

    if policy.manual and pair_key in manual_keys:
        details.append(
            TriggerDetail(
                type="manual",
                reason="manual comparison requested",
                baseline_expectation=None,
                actual_value="manual comparison",
                previous_run_value=None,
                why="Manual comparison requested",
                next_check=None,
                peer_roles=role_summary,
            )
        )
    if policy.control_plane_version and not baseline.is_drift_allowed(
        BaselineDriftCategory.CONTROL_PLANE_VERSION
    ):
        primary_version = primary.snapshot.metadata.control_plane_version or "unknown"
        secondary_version = secondary.snapshot.metadata.control_plane_version or "unknown"
        if primary_version != secondary_version:
            expectation = baseline.control_plane_expectation
            expectation_desc = expectation.describe() if expectation else None
            reason = f"control plane version drift ({primary_version} vs {secondary_version})"
            previous_value = (
                f"{primary.target.label}: {_format_previous_control_plane(primary.snapshot.metadata.cluster_id)} | "
                f"{secondary.target.label}: {_format_previous_control_plane(secondary.snapshot.metadata.cluster_id)}"
            )
            why_parts = []
            if expectation and expectation.why:
                why_parts.append(expectation.why)
            else:
                why_parts.append("Control plane divergence can affect platform stability.")
            if role_summary:
                why_parts.append(role_summary)
            details.append(
                TriggerDetail(
                    type=BaselineDriftCategory.CONTROL_PLANE_VERSION.value,
                    reason=reason,
                    baseline_expectation=expectation_desc,
                    actual_value=f"{primary_version} vs {secondary_version}",
                    previous_run_value=previous_value,
                    why=" ".join(why_parts).strip(),
                    next_check=expectation.next_check if expectation else None,
                    peer_roles=role_summary,
                )
            )
    if policy.watched_helm_release and not baseline.is_drift_allowed(
        BaselineDriftCategory.WATCHED_HELM_RELEASE
    ):
        watched_releases = (
            set(primary.target.watched_helm_releases) | set(secondary.target.watched_helm_releases)
        )
        for release_key in sorted(watched_releases):
            primary_release = primary.snapshot.helm_releases.get(release_key)
            secondary_release = secondary.snapshot.helm_releases.get(release_key)
            if not primary_release and not secondary_release:
                continue
            primary_version = primary_release.chart_version if primary_release else "missing"
            secondary_version = secondary_release.chart_version if secondary_release else "missing"
            if primary_version == secondary_version:
                continue
            release_policy = baseline.release_policy(release_key)
            expectation_desc = release_policy.describe() if release_policy else None
            next_check_value = release_policy.next_check if release_policy else None
            reason = f"watched Helm release {release_key} drift ({primary_version} vs {secondary_version})"
            previous_value = (
                f"{primary.target.label}: {_format_previous_release(primary.snapshot.metadata.cluster_id, release_key)} | "
                f"{secondary.target.label}: {_format_previous_release(secondary.snapshot.metadata.cluster_id, release_key)}"
            )
            why_parts = []
            if release_policy:
                if release_policy.why:
                    why_parts.append(release_policy.why)
            else:
                why_parts.append(
                    f"Watched Helm release {release_key} drift can cause workload unpredictability."
                )
            if role_summary:
                why_parts.append(role_summary)
            details.append(
                TriggerDetail(
                    type=BaselineDriftCategory.WATCHED_HELM_RELEASE.value,
                    reason=reason,
                    baseline_expectation=expectation_desc,
                    actual_value=f"{primary_version} vs {secondary_version}",
                    previous_run_value=previous_value,
                    why=" ".join(why_parts).strip(),
                    next_check=next_check_value,
                    peer_roles=role_summary,
                )
            )
    if policy.watched_crd and not baseline.is_drift_allowed(
        BaselineDriftCategory.WATCHED_CRD
    ):
        watched_crds = set(primary.target.watched_crd_families) | set(secondary.target.watched_crd_families)
        for crd_name in sorted(watched_crds):
            primary_crd = primary.snapshot.crds.get(crd_name)
            secondary_crd = secondary.snapshot.crds.get(crd_name)
            if not primary_crd and not secondary_crd:
                continue
            primary_storage = primary_crd.storage_version if primary_crd else "missing"
            secondary_storage = secondary_crd.storage_version if secondary_crd else "missing"
            if primary_storage == secondary_storage:
                continue
            crd_policy = baseline.crd_policy(crd_name)
            expectation_desc = f"CRD {crd_name} must exist" if crd_policy else None
            next_crd_check = crd_policy.next_check if crd_policy else None
            reason = f"watched CRD {crd_name} storage drift ({primary_storage} vs {secondary_storage})"
            previous_value = (
                f"{primary.target.label}: {_format_previous_crd(primary.snapshot.metadata.cluster_id, crd_name)} | "
                f"{secondary.target.label}: {_format_previous_crd(secondary.snapshot.metadata.cluster_id, crd_name)}"
            )
            why_parts = []
            if crd_policy:
                if crd_policy.why:
                    why_parts.append(crd_policy.why)
            else:
                why_parts.append(f"CRD {crd_name} drift can impact dependent controllers.")
            if role_summary:
                why_parts.append(role_summary)
            details.append(
                TriggerDetail(
                    type=BaselineDriftCategory.WATCHED_CRD.value,
                    reason=reason,
                    baseline_expectation=expectation_desc,
                    actual_value=f"{primary_storage} vs {secondary_storage}",
                    previous_run_value=previous_value,
                    why=" ".join(why_parts).strip(),
                    next_check=next_crd_check,
                    peer_roles=role_summary,
                )
            )
    if policy.health_regression:
        primary_prev = history.get(primary.snapshot.metadata.cluster_id)
        if (
            primary_prev
            and primary_prev.health_rating == HealthRating.HEALTHY
            and (primary.assessment and primary.assessment.rating == HealthRating.DEGRADED)
        ):
            details.append(
                TriggerDetail(
                    type="health_regression",
                    reason=f"health regression detected for {primary.target.label}",
                    baseline_expectation=None,
                    actual_value="health regression",
                    previous_run_value=None,
                    why="Health rating degraded since last healthy run.",
                    next_check=None,
                    peer_roles=role_summary,
                )
            )
        secondary_prev = history.get(secondary.snapshot.metadata.cluster_id)
        if (
            secondary_prev
            and secondary_prev.health_rating == HealthRating.HEALTHY
            and (secondary.assessment and secondary.assessment.rating == HealthRating.DEGRADED)
        ):
            details.append(
                TriggerDetail(
                    type="health_regression",
                    reason=f"health regression detected for {secondary.target.label}",
                    baseline_expectation=None,
                    actual_value="health regression",
                    previous_run_value=None,
                    why="Health rating degraded since last healthy run.",
                    next_check=None,
                    peer_roles=role_summary,
                )
            )
    if policy.missing_evidence:
        def _missing_delta(entry: HealthSnapshotRecord) -> None:
            prev = history.get(entry.snapshot.metadata.cluster_id)
            prev_missing = set(prev.missing_evidence) if prev else set()
            current_missing = set(entry.assessment.missing_evidence) if entry.assessment else set()
            new_missing = current_missing - prev_missing
            if new_missing:
                details.append(
                    TriggerDetail(
                        type="missing_evidence",
                        reason=(
                            f"missing evidence anomaly for {entry.target.label}: {', '.join(sorted(new_missing))}"
                        ),
                        baseline_expectation=None,
                        actual_value=", ".join(sorted(new_missing)),
                        previous_run_value=None,
                        why="Missing telemetry appeared since last run.",
                        next_check=None,
                        peer_roles=role_summary,
                    )
                )

        _missing_delta(primary)
        _missing_delta(secondary)
    return details


class HealthLoopRunner:
    def __init__(
        self,
        config: HealthRunConfig,
        available_contexts: Iterable[str],
        manual_overrides: Sequence[ManualComparison] | None = None,
        manual_drilldown_contexts: Sequence[str] | None = None,
        snapshot_collector: Callable[[str], ClusterSnapshot] = collect_cluster_snapshot,
        comparison_fn: Callable[[ClusterSnapshot, ClusterSnapshot], ClusterComparison] = compare_snapshots,
        quiet: bool = False,
        drilldown_collector: DrilldownCollector | None = None,
    ) -> None:
        self.config = config
        self.available_contexts = set(available_contexts)
        self.snapshot_collector = snapshot_collector
        self.comparison_fn = comparison_fn
        self.quiet = quiet
        manual_items = list(config.manual_pairs)
        if manual_overrides:
            manual_items.extend(manual_overrides)
        self._manual_keys: Set[Tuple[str, str]] = {
            (item.primary, item.secondary) for item in manual_items
        }
        self._collection_messages: List[str] = []
        self._manual_drilldown_contexts: Set[str] = {
            normalize_ref(value) for value in (manual_drilldown_contexts or []) if value
        }
        self.run_label = config.run_label
        self.run_id = _build_runtime_run_id(self.run_label)
        self.baseline_policy = config.baseline_policy
        self._drilldown_collector = drilldown_collector

    def execute(
        self,
    ) -> Tuple[
        List[HealthAssessmentArtifact],
        List[ComparisonTriggerArtifact],
        List[DrilldownArtifact],
    ]:
        directories = self._ensure_directories()
        history = self._load_history(directories["history"])
        previous_history = {key: entry for key, entry in history.items()}
        records = self._collect_snapshots(directories["snapshots"])
        assessments = self._build_assessments(records, history, directories["assessments"])
        triggers = self._evaluate_triggers(records, previous_history, directories)
        drilldowns = self._build_drilldowns(records, previous_history, directories["drilldowns"])
        self._persist_history(history, directories["history"])
        if not self.quiet:
            print(
                f"Health run '{self.run_label}' ({self.run_id}) produced {len(assessments)} assessments and {len(triggers)} triggered comparison(s)."
            )
            for message in self._collection_messages:
                print(message)
        return assessments, triggers, drilldowns

    def _ensure_directories(self) -> Dict[str, Path]:
        root = self.config.output_dir / "health"
        subdirs = {
            "root": root,
            "snapshots": root / "snapshots",
            "assessments": root / "assessments",
            "comparisons": root / "comparisons",
            "triggers": root / "triggers",
            "drilldowns": root / "drilldowns",
            "history": root / _HISTORY_FILENAME,
        }
        for key, path in subdirs.items():
            if key == "history":
                continue
            path.mkdir(parents=True, exist_ok=True)
        return subdirs

    def _collect_snapshots(self, directory: Path) -> List[HealthSnapshotRecord]:
        records: List[HealthSnapshotRecord] = []
        for target in self.config.targets:
            if target.context not in self.available_contexts:
                message = f"Context '{target.context}' not available; skipping {target.label}."
                self._collection_messages.append(message)
                continue
            try:
                snapshot = self.snapshot_collector(target.context)
            except RuntimeError as exc:
                message = f"Snapshot for '{target.context}' failed: {exc}"
                self._collection_messages.append(message)
                continue
            filename = _format_snapshot_filename(self.run_id, target.label, snapshot.metadata.captured_at)
            path = directory / filename
            _write_json(snapshot.to_dict(), path)
            self._collection_messages.append(f"Collected snapshot for '{target.context}' -> {path}")
            records.append(HealthSnapshotRecord(target=target, snapshot=snapshot, path=path))
        return records

    def _build_assessments(
        self,
        records: List[HealthSnapshotRecord],
        history: Dict[str, HealthHistoryEntry],
        assessment_dir: Path,
    ) -> List[HealthAssessmentArtifact]:
        artifacts: List[HealthAssessmentArtifact] = []
        for record in records:
            cluster_id = record.snapshot.metadata.cluster_id
            previous = history.get(cluster_id)
            watched_release_versions = _watched_release_versions(
                record.snapshot, record.target.watched_helm_releases
            )
            watched_crd_versions = _watched_crd_versions(
                record.snapshot, record.target.watched_crd_families
            )
            assessment_result: Optional[HealthAssessmentResult] = None
            if record.target.monitor_health:
                assessment_result = build_health_assessment(
                    record.snapshot,
                    record.target,
                    previous,
                    self.config.baseline_policy,
                    self.config.trigger_policy.warning_event_threshold,
                )
                record.assessment = assessment_result
                assessment_path = assessment_dir / f"{self.run_id}-{record.target.label}-assessment.json"
                artifact = HealthAssessmentArtifact(
                    run_label=self.run_label,
                    run_id=self.run_id,
                    timestamp=datetime.now(timezone.utc),
                    context=record.target.context,
                    label=record.target.label,
                    cluster_id=cluster_id,
                    snapshot_path=str(record.path),
                    assessment=assessment_to_dict(assessment_result.assessment),
                    missing_evidence=assessment_result.missing_evidence,
                    health_rating=assessment_result.rating,
                )
                _write_json(artifact.to_dict(), assessment_path)
                artifacts.append(artifact)
            history[cluster_id] = HealthHistoryEntry(
                cluster_id=cluster_id,
                node_count=record.snapshot.metadata.node_count,
                pod_count=record.snapshot.metadata.pod_count,
                control_plane_version=record.snapshot.metadata.control_plane_version or "",
                health_rating=assessment_result.rating if assessment_result else HealthRating.HEALTHY,
                missing_evidence=assessment_result.missing_evidence if assessment_result else (),
                watched_helm_releases=watched_release_versions,
                watched_crd_families=watched_crd_versions,
                node_conditions=record.snapshot.health_signals.node_conditions.to_dict(),
                pod_counts=record.snapshot.health_signals.pod_counts.to_dict(),
                job_failures=record.snapshot.health_signals.job_failures,
                warning_event_count=len(record.snapshot.health_signals.warning_events),
            )
        return artifacts

    def _build_drilldowns(
        self,
        records: List[HealthSnapshotRecord],
        previous_history: Dict[str, HealthHistoryEntry],
        directory: Path,
    ) -> List[DrilldownArtifact]:
        collector = self._drilldown_collector or DrilldownCollector()
        artifacts: List[DrilldownArtifact] = []
        for record in records:
            reasons = self._determine_drilldown_reasons(record, previous_history)
            if not reasons:
                continue
            try:
                evidence = collector.collect(record.target.context, (record.target.context,))
            except RuntimeError as exc:
                self._collection_messages.append(
                    f"Drilldown for '{record.target.context}' failed: {exc}"
                )
                continue
            artifact = DrilldownArtifact(
                run_label=self.run_label,
                run_id=self.run_id,
                timestamp=datetime.now(timezone.utc),
                snapshot_timestamp=record.snapshot.metadata.captured_at,
                context=record.target.context,
                label=record.target.label,
                cluster_id=record.snapshot.metadata.cluster_id,
                trigger_reasons=reasons,
                missing_evidence=tuple(record.assessment.missing_evidence if record.assessment else ()),
                evidence_summary=evidence.summary,
                affected_namespaces=evidence.affected_namespaces,
                affected_workloads=evidence.affected_workloads,
                warning_events=evidence.warning_events,
                non_running_pods=evidence.non_running_pods,
                pod_descriptions=evidence.pod_descriptions,
                rollout_status=evidence.rollouts,
                collection_timestamps=evidence.collection_timestamps,
            )
            path = directory / f"{self.run_id}-{record.target.label}-drilldown.json"
            _write_json(artifact.to_dict(), path)
            artifacts.append(artifact)
            self._collection_messages.append(
                f"Drilldown evidence collected for '{record.target.context}' -> {path}"
            )
        return artifacts

    def _determine_drilldown_reasons(
        self,
        record: HealthSnapshotRecord,
        previous_history: Dict[str, HealthHistoryEntry],
    ) -> Tuple[str, ...]:
        if not record.assessment:
            return ()
        reasons: List[str] = []
        normalized_context = normalize_ref(record.target.context)
        if normalized_context in self._manual_drilldown_contexts:
            reasons.append("manual_request")
        prev_entry = previous_history.get(record.snapshot.metadata.cluster_id)
        if (
            prev_entry
            and prev_entry.health_rating == HealthRating.HEALTHY
            and record.assessment.rating == HealthRating.DEGRADED
        ):
            reasons.append("health_regression")
        pod_counts = record.snapshot.health_signals.pod_counts
        if pod_counts.crash_loop_backoff > 0:
            reasons.append("CrashLoopBackOff")
        if pod_counts.image_pull_backoff > 0:
            reasons.append("ImagePullBackOff")
        warning_threshold = self.config.trigger_policy.warning_event_threshold
        warning_events = record.snapshot.health_signals.warning_events
        threshold_met = (
            len(warning_events) > 0
            if warning_threshold <= 0
            else len(warning_events) >= warning_threshold
        )
        if threshold_met:
            reasons.append("warning_event_threshold")
        if record.snapshot.health_signals.job_failures > 0:
            reasons.append("job_failures")
        unique_reasons = tuple(dict.fromkeys(reasons))
        return unique_reasons

    def _evaluate_triggers(
        self,
        records: List[HealthSnapshotRecord],
        history: Dict[str, HealthHistoryEntry],
        directories: Dict[str, Path],
    ) -> List[ComparisonTriggerArtifact]:
        triggers: List[ComparisonTriggerArtifact] = []
        if not self.config.peers:
            self._collection_messages.append(_HEALTH_ONLY_MESSAGE)
            return triggers
        record_lookup: Dict[str, HealthSnapshotRecord] = {}
        for record in records:
            primary_ref, label_ref = record.refs()
            record_lookup[primary_ref] = record
            record_lookup[label_ref] = record
        for peer in self.config.peers:
            primary_record = record_lookup.get(peer.source)
            if not primary_record:
                continue
            for secondary_ref in peer.peers:
                secondary_record = record_lookup.get(secondary_ref)
                if not secondary_record:
                    continue
                trigger_details = determine_pair_trigger_reasons(
                    primary_record,
                    secondary_record,
                    self.config.trigger_policy,
                    history,
                    self._manual_keys,
                    self.baseline_policy,
                )
                if not trigger_details:
                    continue
                comparison = self.comparison_fn(primary_record.snapshot, secondary_record.snapshot)
                summary = {key: len(value) for key, value in comparison.differences.items()}
                comparison_path = directories["comparisons"] / f"{self.run_id}-{primary_record.target.label}-vs-{secondary_record.target.label}-comparison.json"
                _write_json(
                    {
                        "differences": _serialize_value(comparison.differences),
                        "trigger_reasons": [detail.reason for detail in trigger_details],
                        "trigger_details": [detail.to_dict() for detail in trigger_details],
                    },
                    comparison_path,
                )
                artifact = ComparisonTriggerArtifact(
                    run_label=self.run_label,
                    run_id=self.run_id,
                    timestamp=datetime.now(timezone.utc),
                    primary=primary_record.target.context,
                    secondary=secondary_record.target.context,
                    primary_label=primary_record.target.label,
                    secondary_label=secondary_record.target.label,
                    trigger_reasons=tuple(detail.reason for detail in trigger_details),
                    comparison_summary=summary,
                    differences=_serialize_value(comparison.differences),
                    trigger_details=tuple(trigger_details),
                    notes="; ".join(detail.reason for detail in trigger_details),
                )
                triggers.append(artifact)
                trigger_path = directories["triggers"] / f"{self.run_id}-{primary_record.target.label}-vs-{secondary_record.target.label}-trigger.json"
                _write_json(artifact.to_dict(), trigger_path)
                self._collection_messages.append(
                    (
                        f"Triggered comparison {primary_record.target.label} vs {secondary_record.target.label}: "
                        f"{', '.join(detail.reason for detail in trigger_details)}"
                    )
                )
        return triggers

    def _load_history(self, history_path: Path) -> Dict[str, HealthHistoryEntry]:
        if not history_path.exists():
            return {}
        raw = json.loads(history_path.read_text(encoding="utf-8"))
        history: Dict[str, HealthHistoryEntry] = {}
        for cluster_id, entry in raw.items():
            if isinstance(entry, dict):
                history[cluster_id] = HealthHistoryEntry.from_dict(cluster_id, entry)
        return history

    def _persist_history(self, history: Dict[str, HealthHistoryEntry], history_path: Path) -> None:
        data = {cluster_id: entry.to_dict() for cluster_id, entry in history.items()}
        _write_json(data, history_path)

def _safe_int(value: Any | None) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_threshold(value: Any | None) -> int:
    if value is None:
        return 0
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, threshold)


def _parse_manual_triggers(values: Sequence[str]) -> List[ManualComparison]:
    manual: List[ManualComparison] = []
    for raw_value in values:
        if ":" not in raw_value:
            continue
        primary, secondary = raw_value.split(":", 1)
        manual.append(
            ManualComparison(primary=normalize_ref(primary), secondary=normalize_ref(secondary))
        )
    return manual


def run_health_loop(
    config_path: Path,
    manual_triggers: Sequence[str] | None = None,
    manual_drilldown_contexts: Sequence[str] | None = None,
    quiet: bool = False,
    drilldown_collector: DrilldownCollector | None = None,
) -> Tuple[
    int,
    List[HealthAssessmentArtifact],
    List[ComparisonTriggerArtifact],
    List[DrilldownArtifact],
] :
    try:
        config = HealthRunConfig.load(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load health config {config_path}: {exc}")
        return 1, [], [], []
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        print(f"Unable to discover kube contexts: {exc}")
        return 1, [], [], []
    manual_overrides = _parse_manual_triggers(manual_triggers or [])
    runner = HealthLoopRunner(
        config,
        contexts,
        manual_overrides=manual_overrides,
        manual_drilldown_contexts=manual_drilldown_contexts,
        quiet=quiet,
        drilldown_collector=drilldown_collector,
    )
    assessments, triggers, drilldowns = runner.execute()
    return 0, assessments, triggers, drilldowns


_HEALTH_LOCK_FILENAME = ".health-loop.lock"
_HEALTH_ONLY_MESSAGE = "No peer mappings configured; running health-only mode."


class HealthLoopScheduler:
    def __init__(
        self,
        config_path: Path,
        manual_triggers: Sequence[str],
        manual_drilldown_contexts: Sequence[str] | None,
        quiet: bool,
        interval_seconds: int | None,
        max_runs: int | None,
        run_once: bool,
        output_dir: Path,
    ) -> None:
        self._config_path = config_path
        self._manual_triggers = tuple(manual_triggers)
        self._manual_drilldown_contexts = tuple(manual_drilldown_contexts or [])
        self._quiet = quiet
        self._interval_seconds = interval_seconds
        self._max_runs = max_runs
        self._run_once = run_once
        self._lock_path = output_dir / "health" / _HEALTH_LOCK_FILENAME

    def run(self) -> int:
        executed_runs = 0
        last_exit = 0
        try:
            while True:
                if self._run_once and executed_runs >= 1:
                    break
                if self._max_runs is not None and executed_runs >= self._max_runs:
                    break
                run_executed = False
                if not self._acquire_lock():
                    timestamp = datetime.now(timezone.utc).isoformat()
                    print(
                        f"[{timestamp}] Health run skipped because {self._lock_path} is locked."
                    )
                else:
                    try:
                        exit_code, assessments, triggers, drilldowns = run_health_loop(
                            self._config_path,
                            manual_triggers=self._manual_triggers,
                            manual_drilldown_contexts=self._manual_drilldown_contexts,
                            quiet=self._quiet,
                        )
                        run_executed = True
                        last_exit = exit_code
                        if exit_code != 0:
                            return exit_code
                        executed_runs += 1
                        self._print_summary(assessments, triggers, drilldowns)
                    finally:
                        self._release_lock()
                if not run_executed and self._run_once:
                    break
                if self._run_once:
                    break
                if self._max_runs is not None and executed_runs >= self._max_runs:
                    break
                if not self._interval_seconds:
                    break
                time.sleep(self._interval_seconds)
        except KeyboardInterrupt:
            print("Health scheduler interrupted; exiting.")
            return 1
        return last_exit

    def _acquire_lock(self) -> bool:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._lock_path.open("x", encoding="utf-8") as handle:
                handle.write(
                    f"{datetime.now(timezone.utc).isoformat()} pid={os.getpid()}\n"
                )
            return True
        except FileExistsError:
            return False

    def _release_lock(self) -> None:
        try:
            if self._lock_path.exists():
                self._lock_path.unlink()
        except OSError:
            pass

    def _print_summary(
        self,
        assessments: List[HealthAssessmentArtifact],
        triggers: List[ComparisonTriggerArtifact],
        drilldowns: List[DrilldownArtifact],
    ) -> None:
        run_id = "<unknown>"
        if assessments:
            run_id = assessments[0].run_id
        elif triggers:
            run_id = triggers[0].run_id
        healthy = sum(
            1 for artifact in assessments if artifact.health_rating == HealthRating.HEALTHY
        )
        degraded = len(assessments) - healthy
        timestamp = datetime.now(timezone.utc).isoformat()
        print(
            f"[{timestamp}] Health run {run_id}: {len(assessments)} assessments "
            f"({healthy} healthy, {degraded} degraded), {len(triggers)} triggered comparison(s), {len(drilldowns)} drilldown artifact(s)."
        )


def schedule_health_loop(
    config_path: Path,
    manual_triggers: Sequence[str] | None = None,
    manual_drilldown_contexts: Sequence[str] | None = None,
    quiet: bool = False,
    *,
    interval_seconds: int | None = None,
    max_runs: int | None = None,
    run_once: bool = False,
) -> int:
    try:
        config = HealthRunConfig.load(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load health config {config_path}: {exc}")
        return 1
    scheduler = HealthLoopScheduler(
        config_path=config_path,
        manual_triggers=manual_triggers or [],
        manual_drilldown_contexts=manual_drilldown_contexts or [],
        quiet=quiet,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        run_once=run_once,
        output_dir=config.output_dir,
    )
    return scheduler.run()
