"""Per-cluster health assessment loop with trigger-aware comparisons."""
from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass
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


_LABEL_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_HISTORY_FILENAME = "history.json"


def _safe_label(value: str) -> str:
    cleaned = _LABEL_RE.sub("-", value or "")
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned.lower() or "entry"


def _normalize_ref(value: str) -> str:
    return value.strip().lower()


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


@dataclass
class HealthHistoryEntry:
    cluster_id: str
    node_count: int
    pod_count: Optional[int]
    control_plane_version: str
    health_rating: HealthRating
    missing_evidence: Tuple[str, ...]

    @classmethod
    def from_dict(cls, cluster_id: str, data: Dict[str, Any]) -> "HealthHistoryEntry":
        return cls(
            cluster_id=cluster_id,
            node_count=int(data.get("node_count", 0)),
            pod_count=data.get("pod_count"),
            control_plane_version=str(data.get("control_plane_version") or ""),
            health_rating=HealthRating(data.get("health_rating", "healthy")),
            missing_evidence=tuple(data.get("missing_evidence", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_count": self.node_count,
            "pod_count": self.pod_count,
            "control_plane_version": self.control_plane_version,
            "health_rating": self.health_rating.value,
            "missing_evidence": list(self.missing_evidence),
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
            references.add(_normalize_ref(target.context))
            references.add(_normalize_ref(target.label))

        peers_raw = raw.get("peer_mappings")
        if not isinstance(peers_raw, list):
            raise ValueError("`peer_mappings` must be a list")
        peers: List[ComparisonPeer] = []
        for entry in peers_raw:
            if not isinstance(entry, dict):
                continue
            source = entry.get("source")
            if not source:
                continue
            normalized_source = _normalize_ref(str(source))
            if normalized_source not in references:
                raise ValueError(f"Unknown peer source: {source}")
            peers_list = entry.get("peers")
            if not isinstance(peers_list, list):
                continue
            normalized_peers: List[str] = []
            for item in peers_list:
                if not item:
                    continue
                normalized_peer = _normalize_ref(str(item))
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
        if not peers:
            raise ValueError("`peer_mappings` must define at least one group")

        trigger_raw = raw.get("comparison_triggers") or {}
        trigger_policy = TriggerPolicy(
            control_plane_version=bool(trigger_raw.get("control_plane_version", True)),
            watched_helm_release=bool(trigger_raw.get("watched_helm_release", True)),
            watched_crd=bool(trigger_raw.get("watched_crd", True)),
            health_regression=bool(trigger_raw.get("health_regression", True)),
            missing_evidence=bool(trigger_raw.get("missing_evidence", True)),
            manual=bool(trigger_raw.get("manual", True)),
        )

        manual_raw = raw.get("manual_pairs") or []
        manual_pairs: List[ManualComparison] = []
        for entry in manual_raw:
            if not isinstance(entry, dict):
                continue
            primary = entry.get("primary")
            secondary = entry.get("secondary")
            if not primary or not secondary:
                continue
            normalized_primary = _normalize_ref(str(primary))
            normalized_secondary = _normalize_ref(str(secondary))
            if normalized_primary not in references or normalized_secondary not in references:
                raise ValueError("Manual pair references unknown cluster")
            manual_pairs.append(
                ManualComparison(primary=normalized_primary, secondary=normalized_secondary)
            )

        return cls(
            run_label=run_label,
            output_dir=output_dir,
            collector_version=collector_version,
            targets=tuple(targets),
            peers=tuple(peers),
            trigger_policy=trigger_policy,
            manual_pairs=tuple(manual_pairs),
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
) -> HealthAssessmentResult:
    generator = _SignalIdGenerator(target.label)
    signals: List[Signal] = []
    evidence_id = snapshot.metadata.cluster_id
    status = snapshot.collection_status
    missing = tuple(status.missing_evidence)
    issues_detected = False

    def add_signal(description: str, severity: str, layer: Layer) -> None:
        signals.append(
            Signal(
                id=generator.next_id(),
                description=description,
                layer=layer,
                evidence_id=evidence_id,
                severity=severity,
            )
        )

    add_signal("Snapshot captured with available telemetry.", "low", Layer.OBSERVABILITY)
    if status.helm_error:
        issues_detected = True
        add_signal(
            f"Helm collection reported an error ({status.helm_error}).",
            "high",
            Layer.OBSERVABILITY,
        )
    for missing_item in missing:
        issues_detected = True
        add_signal(
            f"Missing evidence: {missing_item}.",
            "medium",
            Layer.OBSERVABILITY,
        )
    control_plane_version = snapshot.metadata.control_plane_version or "unknown"
    if not control_plane_version.strip() or control_plane_version.lower() == "unknown":
        issues_detected = True
        add_signal(
            "Control plane version is missing or unknown.",
            "medium",
            Layer.ROLLOUT,
        )
    if previous and snapshot.metadata.node_count != previous.node_count:
        issues_detected = True
        add_signal(
            f"Node count changed from {previous.node_count} to {snapshot.metadata.node_count}.",
            "medium",
            Layer.NODE,
        )
    if (
        previous
        and snapshot.metadata.pod_count is not None
        and previous.pod_count is not None
        and snapshot.metadata.pod_count != previous.pod_count
    ):
        issues_detected = True
        add_signal(
            f"Pod count changed from {previous.pod_count} to {snapshot.metadata.pod_count}.",
            "medium",
            Layer.WORKLOAD,
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
    if issues_detected:
        hypotheses = [
            Hypothesis(
                id=generator.next_id(),
                description="Missing telemetry or version drift suggests the cluster may be unstable.",
                confidence=ConfidenceLevel.MEDIUM,
                probable_layer=dominant_layer,
                what_would_falsify="Telemetry gaps close and node/pod counts stabilize without Helm errors.",
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

    references: List[str] = []
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
        return (_normalize_ref(self.target.context), _normalize_ref(self.target.label))


def determine_pair_trigger_reasons(
    primary: HealthSnapshotRecord,
    secondary: HealthSnapshotRecord,
    policy: TriggerPolicy,
    history: Dict[str, HealthHistoryEntry],
    manual_keys: Set[Tuple[str, str]],
) -> List[str]:
    reasons: List[str] = []
    primary_ref, _ = primary.refs()
    secondary_ref, _ = secondary.refs()
    pair_key = (primary_ref, secondary_ref)
    if policy.manual and pair_key in manual_keys:
        reasons.append("manual comparison requested")
    if policy.control_plane_version:
        primary_version = primary.snapshot.metadata.control_plane_version or "unknown"
        secondary_version = secondary.snapshot.metadata.control_plane_version or "unknown"
        if primary_version != secondary_version:
            reasons.append(
                f"control plane version drift ({primary_version} vs {secondary_version})"
            )
    if policy.watched_helm_release:
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
            if primary_version != secondary_version:
                reasons.append(
                    f"watched Helm release {release_key} drift ({primary_version} vs {secondary_version})"
                )
    if policy.watched_crd:
        watched_crds = set(primary.target.watched_crd_families) | set(secondary.target.watched_crd_families)
        for crd_name in sorted(watched_crds):
            primary_crd = primary.snapshot.crds.get(crd_name)
            secondary_crd = secondary.snapshot.crds.get(crd_name)
            if not primary_crd and not secondary_crd:
                continue
            primary_storage = primary_crd.storage_version if primary_crd else "missing"
            secondary_storage = secondary_crd.storage_version if secondary_crd else "missing"
            if primary_storage != secondary_storage:
                reasons.append(
                    f"watched CRD {crd_name} storage drift ({primary_storage} vs {secondary_storage})"
                )
    if policy.health_regression:
        primary_prev = history.get(primary.snapshot.metadata.cluster_id)
        if (
            primary_prev
            and primary_prev.health_rating == HealthRating.HEALTHY
            and (primary.assessment and primary.assessment.rating == HealthRating.DEGRADED)
        ):
            reasons.append(
                f"health regression detected for {primary.target.label}"
            )
        secondary_prev = history.get(secondary.snapshot.metadata.cluster_id)
        if (
            secondary_prev
            and secondary_prev.health_rating == HealthRating.HEALTHY
            and (secondary.assessment and secondary.assessment.rating == HealthRating.DEGRADED)
        ):
            reasons.append(
                f"health regression detected for {secondary.target.label}"
            )
    if policy.missing_evidence:
        def _missing_delta(entry: HealthSnapshotRecord) -> None:
            prev = history.get(entry.snapshot.metadata.cluster_id)
            prev_missing = set(prev.missing_evidence) if prev else set()
            current_missing = set(entry.assessment.missing_evidence) if entry.assessment else set()
            new_missing = current_missing - prev_missing
            if new_missing:
                reasons.append(
                    f"missing evidence anomaly for {entry.target.label}: {', '.join(sorted(new_missing))}"
                )

        _missing_delta(primary)
        _missing_delta(secondary)
    return reasons


class HealthLoopRunner:
    def __init__(
        self,
        config: HealthRunConfig,
        available_contexts: Iterable[str],
        manual_overrides: Sequence[ManualComparison] | None = None,
        snapshot_collector: Callable[[str], ClusterSnapshot] = collect_cluster_snapshot,
        comparison_fn: Callable[[ClusterSnapshot, ClusterSnapshot], ClusterComparison] = compare_snapshots,
        quiet: bool = False,
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
        self.run_label = config.run_label
        self.run_id = _build_runtime_run_id(self.run_label)

    def execute(
        self,
    ) -> Tuple[List[HealthAssessmentArtifact], List[ComparisonTriggerArtifact]]:
        directories = self._ensure_directories()
        history = self._load_history(directories["history"])
        previous_history = {key: entry for key, entry in history.items()}
        records = self._collect_snapshots(directories["snapshots"])
        assessments = self._build_assessments(records, history, directories["assessments"])
        triggers = self._evaluate_triggers(records, previous_history, directories)
        self._persist_history(history, directories["history"])
        if not self.quiet:
            print(
                f"Health run '{self.run_label}' ({self.run_id}) produced {len(assessments)} assessments and {len(triggers)} triggered comparison(s)."
            )
            for message in self._collection_messages:
                print(message)
        return assessments, triggers

    def _ensure_directories(self) -> Dict[str, Path]:
        root = self.config.output_dir / "health"
        subdirs = {
            "root": root,
            "snapshots": root / "snapshots",
            "assessments": root / "assessments",
            "comparisons": root / "comparisons",
            "triggers": root / "triggers",
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
            assessment_result: Optional[HealthAssessmentResult] = None
            if record.target.monitor_health:
                assessment_result = build_health_assessment(record.snapshot, record.target, previous)
                record.assessment = assessment_result
                assessment_path = assessment_dir / f"{self.run_id}-{record.target.label}-assessment.json"
                _write_json(assessment_to_dict(assessment_result.assessment), assessment_path)
                artifacts.append(
                    HealthAssessmentArtifact(
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
                )
            history[cluster_id] = HealthHistoryEntry(
                cluster_id=cluster_id,
                node_count=record.snapshot.metadata.node_count,
                pod_count=record.snapshot.metadata.pod_count,
                control_plane_version=record.snapshot.metadata.control_plane_version or "",
                health_rating=assessment_result.rating if assessment_result else HealthRating.HEALTHY,
                missing_evidence=assessment_result.missing_evidence if assessment_result else (),
            )
        return artifacts

    def _evaluate_triggers(
        self,
        records: List[HealthSnapshotRecord],
        history: Dict[str, HealthHistoryEntry],
        directories: Dict[str, Path],
    ) -> List[ComparisonTriggerArtifact]:
        triggers: List[ComparisonTriggerArtifact] = []
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
                reasons = determine_pair_trigger_reasons(
                    primary_record,
                    secondary_record,
                    self.config.trigger_policy,
                    history,
                    self._manual_keys,
                )
                if not reasons:
                    continue
                comparison = self.comparison_fn(primary_record.snapshot, secondary_record.snapshot)
                summary = {key: len(value) for key, value in comparison.differences.items()}
                comparison_path = directories["comparisons"] / f"{self.run_id}-{primary_record.target.label}-vs-{secondary_record.target.label}-comparison.json"
                _write_json(
                    {
                        "differences": _serialize_value(comparison.differences),
                        "trigger_reasons": reasons,
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
                    trigger_reasons=tuple(reasons),
                    comparison_summary=summary,
                    differences=_serialize_value(comparison.differences),
                )
                triggers.append(artifact)
                trigger_path = directories["triggers"] / f"{self.run_id}-{primary_record.target.label}-vs-{secondary_record.target.label}-trigger.json"
                _write_json(artifact.to_dict(), trigger_path)
                self._collection_messages.append(
                    f"Triggered comparison {primary_record.target.label} vs {secondary_record.target.label}: {', '.join(reasons)}"
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


def _parse_manual_triggers(values: Sequence[str]) -> List[ManualComparison]:
    manual: List[ManualComparison] = []
    for raw_value in values:
        if ":" not in raw_value:
            continue
        primary, secondary = raw_value.split(":", 1)
        manual.append(
            ManualComparison(primary=_normalize_ref(primary), secondary=_normalize_ref(secondary))
        )
    return manual


def run_health_loop(
    config_path: Path,
    manual_triggers: Sequence[str] | None = None,
    quiet: bool = False,
) -> Tuple[int, List[HealthAssessmentArtifact], List[ComparisonTriggerArtifact]]:
    try:
        config = HealthRunConfig.load(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Unable to load health config {config_path}: {exc}")
        return 1, [], []
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        print(f"Unable to discover kube contexts: {exc}")
        return 1, [], []
    manual_overrides = _parse_manual_triggers(manual_triggers or [])
    runner = HealthLoopRunner(
        config,
        contexts,
        manual_overrides=manual_overrides,
        quiet=quiet,
    )
    assessments, triggers = runner.execute()
    return 0, assessments, triggers
