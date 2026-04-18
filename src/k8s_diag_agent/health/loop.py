"""Per-cluster health assessment loop with trigger-aware comparisons."""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..collect.cluster_snapshot import ClusterSnapshot, WarningEventSummary
from ..collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from ..compare.two_cluster import ClusterComparison, compare_snapshots
from ..external_analysis.adapter import ExternalAnalysisRequest, build_external_analysis_adapters
from ..external_analysis.alertmanager_artifact import write_alertmanager_sources
from ..external_analysis.alertmanager_discovery import (
    AlertmanagerSourceInventory,
    AlertmanagerSourceOrigin,
    AlertmanagerSourceState,
    discover_alertmanagers,
    merge_deduplicate_inventory,
)
from ..external_analysis.artifact import (
    ExternalAnalysisArtifact,
    ExternalAnalysisPurpose,
    ExternalAnalysisStatus,
    write_external_analysis_artifact,
)
from ..external_analysis.config import ExternalAnalysisSettings, parse_external_analysis_settings
from ..external_analysis.next_check_planner import plan_next_checks
from ..external_analysis.review_schema import classify_review_enrichment_shape
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
from ..structured_logging import DEFAULT_HEALTH_LOG, emit_structured_log
from .adaptation import (
    HealthProposal,
    collect_trigger_details,
    generate_proposals_from_review,
)
from .baseline import (
    BaselineDriftCategory,
    BaselinePolicy,
    _str_or_none,
    resolve_baseline_policy_path,
)
from .drilldown import DrilldownArtifact, DrilldownCollector
from .drilldown_assessor import assess_drilldown_artifact
from .freshness import freshness_status
from .image_pull_secret import (
    BROKEN_IMAGE_PULL_SECRET_REASON,
    ImagePullSecretInsight,
    ImagePullSecretInspector,
)
from .notifications import (
    NotificationArtifact,
    build_degraded_health_notification,
    build_external_analysis_notification,
    build_proposal_created_notification,
    build_suspicious_comparison_notification,
    write_notification_artifact,
)
from .review_feedback import build_health_review
from .ui import (
    _build_provider_execution,
    _serialize_review_enrichment_policy,
    write_health_ui_index,
)
from .utils import normalize_ref
from .validators import (
    ComparisonDecisionValidator,
    DrilldownArtifactValidator,
    HealthAssessmentValidator,
    HealthProposalValidator,
)

_LABEL_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_HISTORY_FILENAME = "history.json"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "y", "on"}


def _safe_label(value: str) -> str:
    cleaned = _LABEL_RE.sub("-", value or "")
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = cleaned.strip("-")
    return cleaned.lower() or "entry"


def _env_is_truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in _TRUTHY_ENV_VALUES



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
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{component}-{timestamp}"


def _watched_release_versions(
    snapshot: ClusterSnapshot, watched: Iterable[str]
) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for release_key in watched:
        release = snapshot.helm_releases.get(release_key)
        versions[release_key] = release.chart_version if release else None
    return versions


def _watched_crd_versions(
    snapshot: ClusterSnapshot, watched: Iterable[str]
) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for crd_name in watched:
        crd = snapshot.crds.get(crd_name)
        versions[crd_name] = crd.storage_version if crd else None
    return versions


def _normalize_category_list(value: Any | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        normalized = _str_or_none(value)
        return (normalized,) if normalized else ()
    if isinstance(value, Sequence):
        categories: list[str] = []
        for item in value:
            normalized = _str_or_none(item)
            if normalized:
                categories.append(normalized)
        return tuple(dict.fromkeys(categories))
    return ()


def _load_baseline_policy_from_path(
    path: Path, cache: dict[Path, BaselinePolicy]
) -> BaselinePolicy:
    if path in cache:
        return cache[path]
    policy = BaselinePolicy.load_from_file(path)
    cache[path] = policy
    return policy


def _parse_cohort_baselines(
    raw: Any | None,
    directory: Path,
    cache: dict[Path, BaselinePolicy],
) -> dict[str, tuple[BaselinePolicy, Path]]:
    cohort_map: dict[str, tuple[BaselinePolicy, Path]] = {}
    if not raw:
        return cohort_map
    entries: list[tuple[str, str]] = []
    if isinstance(raw, Mapping):
        for cohort, value in raw.items():
            cohort_name = _str_or_none(cohort if isinstance(cohort, str) else str(cohort))
            path_value = _str_or_none(value if isinstance(value, str) else str(value))
            if cohort_name and path_value:
                entries.append((cohort_name, path_value))
    elif isinstance(raw, Sequence):
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            cohort_name = _str_or_none(item.get("cohort")) or _str_or_none(item.get("name"))
            path_value = _str_or_none(item.get("path")) or _str_or_none(item.get("baseline_policy_path"))
            if cohort_name and path_value:
                entries.append((cohort_name, path_value))
    for cohort_name, path_value in entries:
        resolved = resolve_baseline_policy_path(directory, path_value)
        policy = _load_baseline_policy_from_path(resolved, cache)
        cohort_map[cohort_name] = (policy, resolved)
    return cohort_map


def _resolve_target_baseline_path(
    directory: Path,
    explicit: str | None,
    cohort: str | None,
    cohort_map: dict[str, tuple[BaselinePolicy, Path]],
    default_path: Path | None,
) -> Path | None:
    if explicit:
        return resolve_baseline_policy_path(directory, explicit)
    if cohort and cohort in cohort_map:
        return cohort_map[cohort][1]
    return default_path


def _policy_for_target(
    baseline_path_str: str | None,
    cohort: str | None,
    default_policy: BaselinePolicy,
    default_path: Path | None,
    cohort_map: dict[str, tuple[BaselinePolicy, Path]],
    cache: dict[Path, BaselinePolicy],
) -> tuple[BaselinePolicy, Path | None]:
    if baseline_path_str:
        resolved_path = Path(baseline_path_str)
        policy = _load_baseline_policy_from_path(resolved_path, cache)
        return policy, resolved_path
    if cohort and cohort in cohort_map:
        return cohort_map[cohort]
    return default_policy, default_path

class HealthRating(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class HealthTarget:
    context: str
    label: str
    monitor_health: bool
    watched_helm_releases: tuple[str, ...]
    watched_crd_families: tuple[str, ...]
    cluster_class: str | None = None
    cluster_role: str | None = None
    baseline_cohort: str | None = None
    baseline_policy_path: str | None = None


@dataclass(frozen=True)
class ComparisonPeer:
    primary: str
    secondary: str
    intent: ComparisonIntent
    expected_drift_categories: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None


class ComparisonIntent(StrEnum):
    EXPECTED_DRIFT = "expected-drift"
    SUSPICIOUS_DRIFT = "suspicious-drift"
    IRRELEVANT_DRIFT = "irrelevant-drift"

    def label(self) -> str:
        if self == ComparisonIntent.EXPECTED_DRIFT:
            return "expected drift"
        if self == ComparisonIntent.SUSPICIOUS_DRIFT:
            return "suspicious drift"
        if self == ComparisonIntent.IRRELEVANT_DRIFT:
            return "irrelevant drift"
        return str(self)


@dataclass(frozen=True)
class ManualComparison:
    primary: str
    secondary: str


@dataclass(frozen=True)
class ManualExternalAnalysisRequest:
    tool: str
    target: str


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
    pod_count: int | None
    control_plane_version: str
    health_rating: HealthRating
    missing_evidence: tuple[str, ...]
    watched_helm_releases: dict[str, str | None] = field(default_factory=dict)
    watched_crd_families: dict[str, str | None] = field(default_factory=dict)
    node_conditions: dict[str, int] = field(default_factory=dict)
    pod_counts: dict[str, int] = field(default_factory=dict)
    job_failures: int = 0
    warning_event_count: int = 0
    cluster_class: str | None = None
    cluster_role: str | None = None
    baseline_cohort: str | None = None
    baseline_policy_path: str | None = None

    @classmethod
    def from_dict(cls, cluster_id: str, data: dict[str, Any]) -> HealthHistoryEntry:
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
            cluster_class=_str_or_none(data.get("cluster_class")),
            cluster_role=_str_or_none(data.get("cluster_role")),
            baseline_cohort=_str_or_none(data.get("baseline_cohort") or data.get("platform_generation")),
            baseline_policy_path=_str_or_none(data.get("baseline_policy_path")),
        )

    def to_dict(self) -> dict[str, Any]:
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
            "cluster_class": self.cluster_class,
            "cluster_role": self.cluster_role,
            "baseline_cohort": self.baseline_cohort,
            "baseline_policy_path": self.baseline_policy_path,
        }


@dataclass
class HealthAssessmentResult:
    assessment: Assessment
    rating: HealthRating
    missing_evidence: tuple[str, ...]
    node_count: int
    pod_count: int | None
    control_plane_version: str
    pattern_reasons: tuple[str, ...] = field(default_factory=tuple)
    pattern_metadata: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass
class HealthAssessmentArtifact:
    run_label: str
    run_id: str
    timestamp: datetime
    context: str
    label: str
    cluster_id: str
    snapshot_path: str
    assessment: dict[str, Any]
    missing_evidence: tuple[str, ...]
    health_rating: HealthRating
    notes: str | None = None
    artifact_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
        if self.artifact_path:
            data["artifact_path"] = self.artifact_path
        return data


@dataclass(frozen=True)
class TriggerDetail:
    type: str
    reason: str
    baseline_expectation: str | None
    actual_value: str
    previous_run_value: str | None
    why: str
    next_check: str | None
    peer_roles: str | None = None
    classification: str | None = None

    def to_dict(self) -> dict[str, Any]:
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
        if self.classification:
            data["classification"] = self.classification
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
    trigger_reasons: tuple[str, ...]
    comparison_summary: dict[str, int]
    differences: dict[str, dict[str, Any]]
    trigger_details: tuple[TriggerDetail, ...]
    comparison_intent: str
    expected_drift_categories: tuple[str, ...]
    ignored_drift_categories: tuple[str, ...]
    peer_notes: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
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
            "comparison_intent": self.comparison_intent,
            "expected_drift_categories": list(self.expected_drift_categories),
            "ignored_drift_categories": list(self.ignored_drift_categories),
            "peer_notes": self.peer_notes,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ComparisonDecision:
    primary_label: str
    secondary_label: str
    policy_eligible: bool
    triggered: bool
    comparison_intent: str
    reason: str
    primary_class: str | None
    secondary_class: str | None
    primary_role: str | None
    secondary_role: str | None
    primary_cohort: str | None
    secondary_cohort: str | None
    expected_drift_categories: tuple[str, ...]
    ignored_drift_categories: tuple[str, ...]
    notes: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_label": self.primary_label,
            "secondary_label": self.secondary_label,
            "policy_eligible": self.policy_eligible,
            "triggered": self.triggered,
            "comparison_intent": self.comparison_intent,
            "reason": self.reason,
            "primary_class": self.primary_class,
            "secondary_class": self.secondary_class,
            "primary_role": self.primary_role,
            "secondary_role": self.secondary_role,
            "primary_cohort": self.primary_cohort,
            "secondary_cohort": self.secondary_cohort,
            "expected_drift_categories": list(self.expected_drift_categories),
            "ignored_drift_categories": list(self.ignored_drift_categories),
            "notes": self.notes,
        }


@dataclass
class HealthRunConfig:
    run_label: str
    output_dir: Path
    collector_version: str
    targets: tuple[HealthTarget, ...]
    peers: tuple[ComparisonPeer, ...]
    trigger_policy: TriggerPolicy
    manual_pairs: tuple[ManualComparison, ...]
    baseline_policy: BaselinePolicy
    baseline_policy_path: Path | None = None
    cohort_baselines: dict[str, tuple[BaselinePolicy, Path]] = field(default_factory=dict)
    target_baselines: dict[str, tuple[BaselinePolicy, Path | None]] = field(default_factory=dict)
    external_analysis: ExternalAnalysisSettings = field(default_factory=ExternalAnalysisSettings)

    @classmethod
    def load(cls, path: Path) -> HealthRunConfig:
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

        base_dir = path.parent
        policy_cache: dict[Path, BaselinePolicy] = {}
        baseline_policy_path: Path | None = None
        baseline_policy: BaselinePolicy = BaselinePolicy.empty()
        baseline_raw = raw.get("baseline_policy_path")
        explicit_baseline = str(baseline_raw) if baseline_raw else None
        try:
            resolved_default = resolve_baseline_policy_path(base_dir, explicit_baseline)
        except FileNotFoundError as exc:
            if explicit_baseline:
                raise ValueError(f"Unable to locate baseline policy near {base_dir}: {exc}")
        else:
            baseline_policy_path = resolved_default
            baseline_policy = _load_baseline_policy_from_path(resolved_default, policy_cache)

        cohort_baselines = _parse_cohort_baselines(raw.get("baseline_policies"), base_dir, policy_cache)

        targets_raw = raw.get("targets")
        if not isinstance(targets_raw, list):
            raise ValueError("`targets` must be a list")
        targets: list[HealthTarget] = []
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
            cluster_class = _str_or_none(entry.get("cluster_class"))
            cluster_role = _str_or_none(entry.get("cluster_role"))
            cohort_value = entry.get("baseline_cohort") or entry.get("platform_generation")
            baseline_cohort = _str_or_none(cohort_value)
            missing_metadata: list[str] = []
            if not cluster_class:
                missing_metadata.append("cluster_class")
            if not cluster_role:
                missing_metadata.append("cluster_role")
            if not baseline_cohort:
                missing_metadata.append("baseline_cohort/platform_generation")
            if missing_metadata:
                raise ValueError(
                    f"Target '{label}' missing required metadata: {', '.join(missing_metadata)}"
                )
            baseline_override = _str_or_none(entry.get("baseline_policy_path"))
            try:
                resolved_path = _resolve_target_baseline_path(
                    base_dir,
                    baseline_override,
                    baseline_cohort,
                    cohort_baselines,
                    baseline_policy_path,
                )
            except FileNotFoundError as exc:
                raise ValueError(
                    f"Unable to locate baseline policy for target '{label}': {exc}"
                )
            if resolved_path is None:
                raise ValueError(
                    f"Target '{label}' cannot resolve a baseline policy; declare baseline_policy_path or register its cohort in baseline_policies."
                )
            targets.append(
                HealthTarget(
                    context=str(context),
                    label=label,
                    monitor_health=monitor_health,
                    watched_helm_releases=watched_helm,
                    watched_crd_families=watched_crd,
                    cluster_class=cluster_class,
                    cluster_role=cluster_role,
                    baseline_cohort=baseline_cohort,
                    baseline_policy_path=str(resolved_path),
                )
            )
        if not targets:
            raise ValueError("`targets` must include at least one entry")

        target_lookup: dict[str, HealthTarget] = {}
        for target in targets:
            target_lookup[normalize_ref(target.context)] = target
            target_lookup[normalize_ref(target.label)] = target
        references: set[str] = set(target_lookup.keys())

        manual_raw = raw.get("manual_pairs") or []
        manual_pairs: list[ManualComparison] = []
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
        peers: list[ComparisonPeer] = []
        for entry in peers_raw:
            if not isinstance(entry, dict):
                continue
            primary_value = entry.get("primary") or entry.get("source")
            secondary_value = entry.get("secondary") or entry.get("peer")
            peer_list = entry.get("peers")
            if not primary_value:
                continue
            candidates: list[str] = []
            if secondary_value:
                candidates.append(secondary_value)
            if isinstance(peer_list, list):
                for item in peer_list:
                    if not item:
                        continue
                    candidates.append(item)
            if len(candidates) != 1:
                raise ValueError("Each peer mapping must target exactly one secondary cluster")
            normalized_primary = normalize_ref(str(primary_value))
            if normalized_primary not in references:
                raise ValueError(f"Unknown peer source: {primary_value}")
            normalized_secondary = normalize_ref(str(candidates[0]))
            if normalized_secondary not in references:
                raise ValueError(f"Unknown peer target: {candidates[0]}")
            intent_value = _parse_comparison_intent(entry.get("intent"))
            expected_categories = _normalize_category_list(entry.get("expected_drift_categories"))
            notes = _str_or_none(entry.get("notes"))
            peers.append(
                ComparisonPeer(
                    primary=normalized_primary,
                    secondary=normalized_secondary,
                    intent=intent_value,
                    expected_drift_categories=expected_categories,
                    notes=notes,
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

        external_analysis_settings = parse_external_analysis_settings(raw.get("external_analysis"))

        target_baselines: dict[str, tuple[BaselinePolicy, Path | None]] = {}
        for target in targets:
            policy, resolved_path = _policy_for_target(
                target.baseline_policy_path,
                target.baseline_cohort,
                baseline_policy,
                baseline_policy_path,
                cohort_baselines,
                policy_cache,
            )
            target_baselines[target.label] = (policy, resolved_path)

        _validate_suspicious_pairs(peers, target_lookup, baseline_policy)

        return cls(
            run_label=run_label,
            output_dir=output_dir,
            collector_version=collector_version,
            targets=tuple(targets),
            peers=tuple(peers),
            trigger_policy=trigger_policy,
            manual_pairs=tuple(manual_pairs),
            cohort_baselines=cohort_baselines,
            target_baselines=target_baselines,
            baseline_policy=baseline_policy,
            baseline_policy_path=baseline_policy_path,
            external_analysis=external_analysis_settings,
        )

    def baseline_for_target(self, target: HealthTarget) -> tuple[BaselinePolicy, Path | None]:
        return self.target_baselines.get(
            target.label, (self.baseline_policy, self.baseline_policy_path)
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
    previous: HealthHistoryEntry | None,
    baseline: BaselinePolicy,
    warning_event_threshold: int = 0,
    image_pull_secret_insight: ImagePullSecretInsight | None = None,
) -> HealthAssessmentResult:
    generator = _SignalIdGenerator(target.label)
    signals: list[Signal] = []
    evidence_id = snapshot.metadata.cluster_id
    status = snapshot.collection_status
    missing = tuple(status.missing_evidence)
    issues_detected = False
    issue_findings: list[Finding] = []
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
    missing_signal_ids: list[str] = []
    missing_signal_map: dict[str, str] = {}
    baseline_next_checks: list[NextCheck] = []
    baseline_reasons: list[str] = []
    image_pull_secret_next_checks: list[NextCheck] = []
    references: list[str] = []
    insight_hypothesis: Hypothesis | None = None
    pattern_reasons: list[str] = []
    pattern_metadata: dict[str, tuple[str, ...]] = {}
    pattern_next_checks: list[NextCheck] = []
    pattern_refs: list[str] = []
    pattern_hypotheses: list[Hypothesis] = []
    matched_event_ids: set[int] = set()
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
            release_current_version: str | None = watched_release_versions.get(release_key)
            release_previous_version: str | None = previous_release_versions.get(release_key)
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
            crd_current_version: str | None = watched_crd_versions.get(crd_key)
            crd_previous_version: str | None = previous_crd_versions.get(crd_key)
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
    node_components: list[str] = []
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
        if image_pull_secret_insight and image_pull_secret_insight.external_secrets:
            details = image_pull_secret_insight
            target_status = details.target_secret_status
            primary_external = details.external_secrets[0]
            issues_detected = True
            signal = add_signal(
                (
                    f"Registry image pull secret {details.secret_name} supply chain is broken in "
                    f"{details.namespace}."
                ),
                "high",
                Layer.WORKLOAD,
            )
            record_finding(
                (
                    f"ExternalSecret {primary_external.name} reports {primary_external.status_reason}: "
                    f"{primary_external.status_message or 'missing secret'} for {details.secret_name}."
                ),
                Layer.WORKLOAD,
                [signal.id],
            )
            image_pull_secret_next_checks.append(
                NextCheck(
                    description="Review the ExternalSecret and backing Kubernetes secret for the failing image pull secret.",
                    owner="platform engineer",
                    method="kubectl",
                    evidence_needed=[
                        f"kubectl describe externalsecret {primary_external.name} -n {details.namespace}",
                        f"kubectl describe secret {details.secret_name} -n {details.namespace}",
                    ],
                )
            )
            insight_hypothesis = Hypothesis(
                id=generator.next_id(),
                description=(
                    f"Image pull secret {details.secret_name} is missing because ExternalSecret {primary_external.name} failed to update the secret ({primary_external.status_reason})."
                ),
                confidence=ConfidenceLevel.MEDIUM,
                probable_layer=Layer.WORKLOAD,
                what_would_falsify=(
                    f"ExternalSecret {primary_external.name} reports Ready and secret {target_status.name or details.secret_name} exists."
                ),
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

    def _unused_warning_events() -> list[WarningEventSummary]:
        return [event for event in warning_events if id(event) not in matched_event_ids]

    def _capture_namespaces(events: Sequence[WarningEventSummary]) -> tuple[str, ...]:
        seen: list[str] = []
        for event in events:
            namespace = (event.namespace or "").strip()
            if namespace and namespace not in seen:
                seen.append(namespace)
        return tuple(seen)

    def _record_pattern(
        reason_tag: str,
        signal_desc: str,
        severity: str,
        layer: Layer,
        hypothesis_desc: str,
        hypothesis_confidence: ConfidenceLevel,
        probable_layer: Layer,
        falsify: str,
        next_check_desc: str,
        evidence_needed: Sequence[str],
        namespaces: Sequence[str],
        reference_label: str,
    ) -> None:
        nonlocal issues_detected
        issues_detected = True
        signal = add_signal(signal_desc, severity, layer)
        record_finding(signal_desc, layer, [signal.id])
        pattern_reasons.append(reason_tag)
        namespace_tuple = tuple(dict.fromkeys(item for item in namespaces if item))
        pattern_metadata[reason_tag] = namespace_tuple
        pattern_refs.append(reference_label)
        pattern_next_checks.append(
            NextCheck(
                description=next_check_desc,
                owner="platform engineer",
                method="kubectl",
                evidence_needed=list(evidence_needed),
            )
        )
        pattern_hypotheses.append(
            Hypothesis(
                id=generator.next_id(),
                description=hypothesis_desc,
                confidence=hypothesis_confidence,
                probable_layer=probable_layer,
                what_would_falsify=falsify,
            )
        )

    def _mark_events(events: Sequence[WarningEventSummary]) -> None:
        for event in events:
            matched_event_ids.add(id(event))

    def _describe_namespace(namespace_list: Sequence[str], fallback: str) -> str:
        for namespace in namespace_list:
            if namespace:
                return namespace
        return fallback

    def _match_probe_events() -> None:
        candidates = [event for event in _unused_warning_events() if "readiness probe" in (event.message or "").lower() or "liveness probe" in (event.message or "").lower()]
        if not candidates:
            return
        _mark_events(candidates)
        namespace = _describe_namespace(_capture_namespaces(candidates), "default")
        signal_desc = f"Readiness/liveness probe failures recorded in {namespace}."
        _record_pattern(
            reason_tag="probe_failure",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.WORKLOAD,
            hypothesis_desc=(
                "A recent rollout or configuration change is likely hitting the probe endpoint before readiness/liveness succeeds; pods stay unready."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.WORKLOAD,
            falsify="Pods start reporting Ready and probe failures stop appearing.",
            next_check_desc=f"Inspect pods in {namespace} that are failing probes and review the rollout history.",
            evidence_needed=[
                f"kubectl describe pods -n {namespace}",
                f"kubectl logs -n {namespace} <pod> --previous",
                f"kubectl rollout status deployment -n {namespace}",
            ],
            namespaces=[namespace],
            reference_label="probe failure pattern",
        )

    def _match_scheduling_events() -> None:
        def _scheduling_cause(event: WarningEventSummary) -> str | None:
            msg = (event.message or "").lower()
            if "untolerated taint" in msg:
                return "node taints"
            if "affinity" in msg:
                return "node affinity"
            if "insufficient" in msg:
                return "resource shortage"
            return None

        matches: list[tuple[WarningEventSummary, str]] = []
        for event in _unused_warning_events():
            if event.reason != "FailedScheduling":
                continue
            cause = _scheduling_cause(event)
            if not cause:
                continue
            matches.append((event, cause))
        if not matches:
            return
        events, causes = zip(*matches)
        _mark_events(events)
        namespace = _describe_namespace(_capture_namespaces(events), "default")
        cause_label = causes[0]
        signal_desc = f"Pods remain Pending in {namespace} because scheduling is blocked by {cause_label}."
        _record_pattern(
            reason_tag="failed_scheduling",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.WORKLOAD,
            hypothesis_desc=(
                f"Scheduling is prevented by {cause_label}, so pods cannot land on nodes; node taints, affinity, or capacity must be rechecked."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.NODE,
            falsify="Pods eventually schedule once nodes match the requested taints/affinity and available resources.",
            next_check_desc=f"Describe Pending pods and node taints/affinity in {namespace} to confirm the scheduling block.",
            evidence_needed=[
                f"kubectl describe pods -n {namespace} --field-selector=status.phase=Pending",
                "kubectl describe nodes",
            ],
            namespaces=[namespace],
            reference_label="scheduling block pattern",
        )

    def _match_metrics_events() -> None:
        matches = [event for event in _unused_warning_events() if event.reason == "FailedGetResourceMetric" or "metrics-server" in (event.message or "").lower()]
        if not matches:
            return
        _mark_events(matches)
        namespace = _describe_namespace(_capture_namespaces(matches), "default")
        signal_desc = f"HPA resource metrics are unavailable in {namespace}; metrics-server may be offline."
        _record_pattern(
            reason_tag="missing_metrics",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.OBSERVABILITY,
            hypothesis_desc=(
                "The metrics-server endpoint or HPA resource metric API is unreachable, so scaling decisions cannot proceed."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.OBSERVABILITY,
            falsify="Metrics-server becomes healthy and resource metrics are present for the HPA.",
            next_check_desc=f"Collect HPA and metrics-server status in {namespace} to see what is missing.",
            evidence_needed=[
                f"kubectl describe hpa -n {namespace}",
                "kubectl get deployment metrics-server -n kube-system",
            ],
            namespaces=[namespace],
            reference_label="metrics-server pattern",
        )

    def _match_pvc_events() -> None:
        matches = [event for event in _unused_warning_events() if event.reason in {"ProvisioningFailed", "VolumeBindingFailed"} or "persistentvolumeclaim" in (event.message or "").lower()]
        if not matches:
            return
        _mark_events(matches)
        namespace = _describe_namespace(_capture_namespaces(matches), "default")
        signal_desc = f"PersistentVolumeClaims in {namespace} remain Pending because provisioning failed."
        _record_pattern(
            reason_tag="pvc_pending",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.STORAGE,
            hypothesis_desc=(
                "The storage class or provisioner cannot satisfy the PVC request, leaving volumes unbound."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.STORAGE,
            falsify="PVCs bind and PVs attach without provisioning errors.",
            next_check_desc=f"Describe PVCs and related storageclasses in {namespace} to examine the provisioning failure.",
            evidence_needed=[
                f"kubectl describe pvc -n {namespace}",
                "kubectl get storageclass",
            ],
            namespaces=[namespace],
            reference_label="PVC provisioning pattern",
        )

    def _match_ingress_events() -> None:
        matches = [event for event in _unused_warning_events() if event.reason in {"Unhealthy", "Failed", "BackendTimeout"}]
        matches = [event for event in matches if any(keyword in (event.message or "").lower() for keyword in ("backend", "endpoint", "timeout", "connection refused", "503"))]
        matches = [event for event in matches if "probe" not in (event.message or "").lower()]
        if not matches:
            return
        _mark_events(matches)
        namespace = _describe_namespace(_capture_namespaces(matches), "default")
        signal_desc = f"Ingress/backend timeouts detected in {namespace}."
        _record_pattern(
            reason_tag="ingress_timeout",
            signal_desc=signal_desc,
            severity="medium",
            layer=Layer.NETWORK,
            hypothesis_desc=(
                "Ingress or service endpoints are missing/unhealthy, leading to backend timeouts at the gateway."
            ),
            hypothesis_confidence=ConfidenceLevel.MEDIUM,
            probable_layer=Layer.NETWORK,
            falsify="Endpoints report Ready and timeouts disappear when traffic reaches backends.",
            next_check_desc=f"Inspect ingress endpoints and services in {namespace} to verify backend availability.",
            evidence_needed=[
                f"kubectl get ingress -n {namespace}",
                f"kubectl get endpoints -n {namespace}",
                f"kubectl describe svc -n {namespace}",
            ],
            namespaces=[namespace],
            reference_label="ingress timeout pattern",
        )

    _match_probe_events()
    _match_scheduling_events()
    _match_metrics_events()
    _match_pvc_events()
    _match_ingress_events()

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
        base_hypothesis = Hypothesis(
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
        detailed_hypotheses: list[Hypothesis] = []
        detailed_hypotheses.extend(pattern_hypotheses)
        if insight_hypothesis:
            detailed_hypotheses.append(insight_hypothesis)
        hypotheses = detailed_hypotheses + [base_hypothesis]
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

    next_checks: list[NextCheck] = []
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
    next_checks.extend(pattern_next_checks)
    next_checks.extend(baseline_next_checks)
    next_checks.extend(image_pull_secret_next_checks)

    if status.helm_error:
        references.append("helm collection error")
    if missing:
        references.append("missing evidence")
    if image_pull_secret_insight:
        references.append("image pull secret supply chain")
    references.extend(pattern_refs)
    if not references:
        references.append("routine health monitoring")
    references = list(dict.fromkeys(references))

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
        pattern_reasons=tuple(dict.fromkeys(pattern_reasons)),
        pattern_metadata={key: tuple(pattern_metadata.get(key, ())) for key in pattern_metadata},
    )


@dataclass
class HealthSnapshotRecord:
    target: HealthTarget
    snapshot: ClusterSnapshot
    path: Path
    baseline_policy: BaselinePolicy
    baseline_policy_path: str | None = None
    assessment: HealthAssessmentResult | None = None
    pattern_reasons: tuple[str, ...] = field(default_factory=tuple)
    pattern_metadata: dict[str, tuple[str, ...]] = field(default_factory=dict)
    image_pull_secret_insight: ImagePullSecretInsight | None = None

    def refs(self) -> tuple[str, str]:
        return (normalize_ref(self.target.context), normalize_ref(self.target.label))


def determine_pair_trigger_reasons(
    primary: HealthSnapshotRecord,
    secondary: HealthSnapshotRecord,
    policy: TriggerPolicy,
    history: dict[str, HealthHistoryEntry],
    manual_keys: set[tuple[str, str]],
    baseline_policy: BaselinePolicy,
    baseline_registry: BaselineRegistry | None,
    classification: str | None = None,
) -> list[TriggerDetail]:
    details: list[TriggerDetail] = []
    primary_ref, _ = primary.refs()
    secondary_ref, _ = secondary.refs()
    pair_key = (primary_ref, secondary_ref)

    def _peer_role_summary() -> str | None:
        primary_role = baseline_registry.role_for(primary_ref) if baseline_registry else None
        if not primary_role:
            primary_role = baseline_registry.role_for(primary.target.label) if baseline_registry else None
        secondary_role = baseline_registry.role_for(secondary_ref) if baseline_registry else None
        if not secondary_role:
            secondary_role = baseline_registry.role_for(secondary.target.label) if baseline_registry else None
        if not primary_role and not secondary_role:
            return None
        summary_parts: list[str] = []
        summary_parts.append(
            f"{primary.target.label} ({primary_role})" if primary_role else primary.target.label
        )
        summary_parts.append(
            f"{secondary.target.label} ({secondary_role})" if secondary_role else secondary.target.label
        )
        return " vs ".join(summary_parts)

    role_summary = _peer_role_summary()
    def _path_label(record: HealthSnapshotRecord) -> str:
        return record.baseline_policy_path or "<default>"
    primary_path = _path_label(primary)
    secondary_path = _path_label(secondary)
    if primary_path != secondary_path:
        details.append(
            TriggerDetail(
                type="baseline_mismatch",
                reason=(
                    f"baseline mismatch ({primary_path} vs {secondary_path})"
                    if primary_path and secondary_path
                    else "baseline mismatch"
                ),
                baseline_expectation=None,
                actual_value=f"{primary_path} vs {secondary_path}",
                previous_run_value=None,
                why=(
                    "Targets rely on different baseline policies, so expected parity between them may not hold."
                ),
                next_check="Confirm the cohorts and baseline policies align before treating drift as actionable.",
                peer_roles=role_summary,
                classification=classification,
            )
        )

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
                classification=classification,
            )
        )
    if policy.control_plane_version and not baseline_policy.is_drift_allowed(
        BaselineDriftCategory.CONTROL_PLANE_VERSION
    ):
        primary_version = primary.snapshot.metadata.control_plane_version or "unknown"
        secondary_version = secondary.snapshot.metadata.control_plane_version or "unknown"
        if primary_version != secondary_version:
            expectation = baseline_policy.control_plane_expectation
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
                    classification=classification,
                )
            )
    if policy.watched_helm_release and not baseline_policy.is_drift_allowed(
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
            release_policy = baseline_policy.release_policy(release_key)
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
                    classification=classification,
                )
            )
    if policy.watched_crd and not baseline_policy.is_drift_allowed(
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
            crd_policy = baseline_policy.crd_policy(crd_name)
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
                    classification=classification,
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
                    classification=classification,
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
                    classification=classification,
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
                        classification=classification,
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
        manual_external_analysis: Sequence[ManualExternalAnalysisRequest] | None = None,
        snapshot_collector: Callable[[str], ClusterSnapshot] = collect_cluster_snapshot,
        comparison_fn: Callable[[ClusterSnapshot, ClusterSnapshot], ClusterComparison] = compare_snapshots,
        drilldown_collector: DrilldownCollector | None = None,
        image_pull_secret_inspector: ImagePullSecretInspector | None = None,
        quiet: bool = False,
        expected_scheduler_interval_seconds: int | None = None,
        run_id: str | None = None,
    ) -> None:
        self.config = config
        self.available_contexts = set(available_contexts)
        self.snapshot_collector = snapshot_collector
        self.comparison_fn = comparison_fn
        self.quiet = quiet
        manual_items = list(config.manual_pairs)
        if manual_overrides:
            manual_items.extend(manual_overrides)
        self._manual_keys: set[tuple[str, str]] = {
            (item.primary, item.secondary) for item in manual_items
        }
        self._manual_drilldown_contexts: set[str] = {
            normalize_ref(value) for value in (manual_drilldown_contexts or []) if value
        }
        self.run_label = config.run_label
        self.run_id = run_id or _build_runtime_run_id(self.run_label)
        self.baseline_policy = config.baseline_policy
        self.baseline_registry = BaselineRegistry([self.baseline_policy])
        for policy, _ in config.target_baselines.values():
            self.baseline_registry.add(policy)
        self._drilldown_collector = drilldown_collector
        self._image_pull_secret_inspector = image_pull_secret_inspector or ImagePullSecretInspector()
        self._log_path = config.output_dir / "health" / "health.log"
        self._analysis_policy = config.external_analysis.policy
        self._analysis_adapters = build_external_analysis_adapters(
            config.external_analysis.adapters,
            settings=config.external_analysis,
        )
        manual_analysis = manual_external_analysis or []
        self._manual_external_analysis_requests = tuple(manual_analysis)
        self._latest_external_artifacts: list[ExternalAnalysisArtifact] = []
        self._notification_records: list[tuple[NotificationArtifact, Path]] = []
        self._expected_scheduler_interval_seconds = expected_scheduler_interval_seconds

    def _log_event(self, component: str, severity: str, message: str, **metadata: Any) -> None:
        emit_structured_log(
            component=component,
            message=message,
            severity=severity,
            run_label=self.run_label,
            run_id=self.run_id,
            log_path=self._log_path,
            metadata=metadata or None,
        )

    def _record_notification(self, directory: Path, artifact: NotificationArtifact) -> Path:
        artifact_path = write_notification_artifact(directory, artifact)
        self._notification_records.append((artifact, artifact_path))
        return artifact_path

    @property
    def latest_external_artifacts(self) -> list[ExternalAnalysisArtifact]:
        return list(self._latest_external_artifacts)

    def execute(
        self,
    ) -> tuple[
        list[HealthAssessmentArtifact],
        list[ComparisonTriggerArtifact],
        list[DrilldownArtifact],
    ]:
        self._log_event("health-loop", "INFO", "Health run started", event="start")
        self._notification_records = []
        directories = self._ensure_directories()
        history = self._load_history(directories["history"])
        previous_history = {key: entry for key, entry in history.items()}
        records = self._collect_snapshots(directories["snapshots"])
        self._run_alertmanager_discovery(records, directories)
        assessments = self._build_assessments(
            records,
            history,
            directories["assessments"],
            directories["root"],
            directories["notifications"],
        )
        triggers = self._evaluate_triggers(records, previous_history, directories)
        drilldowns = self._build_drilldowns(records, previous_history, directories["drilldowns"])
        auto_artifacts = self._run_auto_drilldown_analysis(drilldowns, directories)
        manual_artifacts = self._run_external_analysis(records, directories)
        external_artifacts = [*auto_artifacts, *manual_artifacts]
        self._persist_history(history, directories["history"])
        review_path, proposals = self._write_review_artifact(assessments, drilldowns, directories)
        enrichment_artifact = self._run_review_enrichment(review_path, directories)
        if enrichment_artifact:
            external_artifacts.append(enrichment_artifact)
        plan_artifact = self._run_next_check_planning(review_path, enrichment_artifact, directories)
        if plan_artifact:
            external_artifacts.append(plan_artifact)
        healthy_count = sum(
            1 for artifact in assessments if artifact.health_rating == HealthRating.HEALTHY
        )
        degraded_count = len(assessments) - healthy_count
        self._log_event(
            "health-loop",
            "INFO",
            "Health run completed",
            event="complete",
            assessment_count=len(assessments),
            healthy_count=healthy_count,
            degraded_count=degraded_count,
            trigger_count=len(triggers),
            drilldown_count=len(drilldowns),
            external_analysis_count=len(external_artifacts),
        )
        self._prune_external_analysis_history(directories["external_analysis"])
        try:
            ui_index_path = write_health_ui_index(
                directories["root"],
                self.run_id,
                self.run_label,
                self.config.collector_version,
                records,
                assessments,
                drilldowns,
                proposals,
                external_artifacts,
                self._notification_records,
                external_analysis_settings=self.config.external_analysis,
                available_adapters=self._analysis_adapters.keys(),
                expected_scheduler_interval_seconds=self._expected_scheduler_interval_seconds,
            )
            self._log_event(
                "health-loop",
                "INFO",
                "UI index generated",
                artifact_path=str(ui_index_path),
                assessment_count=len(assessments),
                trigger_count=len(triggers),
                drilldown_count=len(drilldowns),
                proposal_count=len(proposals),
                external_analysis_count=len(external_artifacts),
                event="ui-index-generated",
            )
        except Exception as exc:
            self._log_event(
                "health-loop",
                "ERROR",
                "UI artifact generation failed",
                severity_reason=str(exc),
                event="ui-index-failed",
            )
        self._latest_external_artifacts = external_artifacts
        return assessments, triggers, drilldowns

    def _ensure_directories(self) -> dict[str, Path]:
        root = self.config.output_dir / "health"
        subdirs = {
            "root": root,
            "snapshots": root / "snapshots",
            "assessments": root / "assessments",
            "comparisons": root / "comparisons",
            "triggers": root / "triggers",
            "drilldowns": root / "drilldowns",
            "reviews": root / "reviews",
            "proposals": root / "proposals",
            "notifications": root / "notifications",
            "history": root / _HISTORY_FILENAME,
            "external_analysis": root / "external-analysis",
        }
        for key, path in subdirs.items():
            if key == "history":
                continue
            path.mkdir(parents=True, exist_ok=True)
        return subdirs

    def _prune_external_analysis_history(self, directory: Path) -> None:
        retention = self.config.external_analysis.retention
        if retention.max_artifacts is None and retention.max_age_days is None:
            return
        files: list[tuple[Path, float]] = []
        prefix = f"{self.run_id}-"
        for path in directory.glob("*.json"):
            if not path.is_file() or path.name.startswith(prefix):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            files.append((path, mtime))
        if not files:
            return
        files.sort(key=lambda item: item[1])
        now = datetime.now(UTC)
        candidates = files.copy()
        to_delete: list[Path] = []
        if retention.max_age_days is not None:
            threshold_seconds = retention.max_age_days * 86400
            survivors: list[tuple[Path, float]] = []
            for path, mtime in candidates:
                age_seconds = (now - datetime.fromtimestamp(mtime, UTC)).total_seconds()
                if age_seconds > threshold_seconds:
                    to_delete.append(path)
                else:
                    survivors.append((path, mtime))
            candidates = survivors
        if retention.max_artifacts is not None and len(candidates) > retention.max_artifacts:
            excess = len(candidates) - retention.max_artifacts
            to_delete.extend(path for path, _ in candidates[:excess])
            candidates = candidates[excess:]
        deleted: list[str] = []
        for path in to_delete:
            try:
                path.unlink()
                deleted.append(path.name)
            except OSError as exc:
                self._log_event(
                    "health-loop",
                    "WARNING",
                    "Failed to remove retained external analysis artifact",
                    artifact_path=str(path),
                    severity_reason=str(exc),
                    event="external-analysis-retention-failed",
                )
        if deleted:
            metadata = {
                "deleted_count": len(deleted),
                "deleted_paths": deleted[:5],
                "retention_policy": {
                    "max_artifacts": retention.max_artifacts,
                    "max_age_days": retention.max_age_days,
                },
            }
            self._log_event(
                "health-loop",
                "INFO",
                "External analysis retention pruned old artifacts",
                event="external-analysis-retention",
                **metadata,
            )

    def _collect_snapshots(self, directory: Path) -> list[HealthSnapshotRecord]:
        records: list[HealthSnapshotRecord] = []
        for target in self.config.targets:
            if target.context not in self.available_contexts:
                self._log_event(
                    "health-loop",
                    "WARNING",
                    "Context not available for snapshot collection",
                    cluster_label=target.label,
                    cluster_context=target.context,
                    reason="context-unavailable",
                )
                continue
            try:
                snapshot = self.snapshot_collector(target.context)
            except RuntimeError as exc:
                self._log_event(
                    "health-loop",
                    "WARNING",
                    "Snapshot collection failed",
                    cluster_label=target.label,
                    cluster_context=target.context,
                    severity_reason=str(exc),
                    reason="collection-error",
                )
                continue
            filename = _format_snapshot_filename(
                self.run_id, target.label, snapshot.metadata.captured_at
            )
            path = directory / filename
            _write_json(snapshot.to_dict(), path)
            self._log_event(
                "health-loop",
                "INFO",
                "Snapshot collected",
                cluster_label=target.label,
                cluster_context=target.context,
                artifact_path=str(path),
                event="snapshot",
            )
            baseline_policy, baseline_path = self.config.baseline_for_target(target)
            records.append(
                HealthSnapshotRecord(
                    target=target,
                    snapshot=snapshot,
                    path=path,
                    baseline_policy=baseline_policy,
                    baseline_policy_path=str(baseline_path) if baseline_path else None,
                )
            )
        return records

    def _build_assessments(
        self,
        records: list[HealthSnapshotRecord],
        history: dict[str, HealthHistoryEntry],
        assessment_dir: Path,
        root_dir: Path,
        notification_dir: Path,
    ) -> list[HealthAssessmentArtifact]:
        artifacts: list[HealthAssessmentArtifact] = []
        for record in records:
            cluster_id = record.snapshot.metadata.cluster_id
            previous = history.get(cluster_id)
            watched_release_versions = _watched_release_versions(
                record.snapshot, record.target.watched_helm_releases
            )
            watched_crd_versions = _watched_crd_versions(
                record.snapshot, record.target.watched_crd_families
            )
            assessment_result: HealthAssessmentResult | None = None
            insight: ImagePullSecretInsight | None = None
            pod_counts = record.snapshot.health_signals.pod_counts
            if record.target.monitor_health and pod_counts.image_pull_backoff > 0:
                try:
                    insight = self._image_pull_secret_inspector.inspect(
                        record.target.context,
                        (),
                        record.snapshot.health_signals.warning_events,
                    )
                except Exception as exc:
                    self._log_event(
                        "health-loop",
                        "WARNING",
                        "Image pull secret inspection failed",
                        cluster_label=record.target.label,
                        cluster_context=record.target.context,
                        severity_reason=str(exc),
                        event="image-pull-secret-inspection",
                    )
            if record.target.monitor_health:
                assessment_result = build_health_assessment(
                    record.snapshot,
                    record.target,
                    previous,
                    record.baseline_policy,
                    self.config.trigger_policy.warning_event_threshold,
                    image_pull_secret_insight=insight,
                )
                record.assessment = assessment_result
                record.pattern_reasons = assessment_result.pattern_reasons
                record.pattern_metadata = assessment_result.pattern_metadata
                assessment_path = assessment_dir / f"{self.run_id}-{record.target.label}-assessment.json"
                artifact = HealthAssessmentArtifact(
                    run_label=self.run_label,
                    run_id=self.run_id,
                    timestamp=datetime.now(UTC),
                    context=record.target.context,
                    label=record.target.label,
                    cluster_id=cluster_id,
                    snapshot_path=str(record.path),
                    assessment=assessment_to_dict(assessment_result.assessment),
                    missing_evidence=assessment_result.missing_evidence,
                    health_rating=assessment_result.rating,
                    artifact_path=str(assessment_path),
                )
                HealthAssessmentValidator.validate(artifact.to_dict())
                _write_json(artifact.to_dict(), assessment_path)
                artifacts.append(artifact)
                if artifact.health_rating == HealthRating.DEGRADED:
                    notification = build_degraded_health_notification(
                        self.run_id, record, artifact
                    )
                    self._record_notification(notification_dir, notification)
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
                cluster_class=record.target.cluster_class,
                cluster_role=record.target.cluster_role,
                baseline_cohort=record.target.baseline_cohort,
                baseline_policy_path=record.baseline_policy_path,
            )
            record.image_pull_secret_insight = insight
        return artifacts

    def _build_drilldowns(
        self,
        records: list[HealthSnapshotRecord],
        previous_history: dict[str, HealthHistoryEntry],
        directory: Path,
    ) -> list[DrilldownArtifact]:
        collector = self._drilldown_collector or DrilldownCollector()
        artifacts: list[DrilldownArtifact] = []
        for record in records:
            reasons = self._determine_drilldown_reasons(record, previous_history)
            if not reasons:
                continue
            try:
                evidence = collector.collect(
                    record.target.context,
                    (record.target.context,),
                    record.image_pull_secret_insight,
                    pattern_reasons=record.pattern_reasons,
                    pattern_metadata=record.pattern_metadata,
                )
            except RuntimeError as exc:
                self._log_event(
                    "drilldown-collector",
                    "WARNING",
                    "Drilldown collection failed",
                    cluster_label=record.target.label,
                    cluster_context=record.target.context,
                    severity_reason=str(exc),
                    event="drilldown-failed",
                )
                continue
            path = directory / f"{self.run_id}-{record.target.label}-drilldown.json"
            artifact = DrilldownArtifact(
                run_label=self.run_label,
                run_id=self.run_id,
                timestamp=datetime.now(UTC),
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
                pattern_details=evidence.pattern_details,
                artifact_path=str(path),
            )
            DrilldownArtifactValidator.validate(artifact.to_dict())
            _write_json(artifact.to_dict(), path)
            artifacts.append(artifact)
            self._log_event(
                "drilldown-collector",
                "INFO",
                "Drilldown artifact created",
                cluster_label=record.target.label,
                artifact_path=str(path),
                event="drilldown",
            )
        return artifacts

    def _run_external_analysis(
        self, records: list[HealthSnapshotRecord], directories: dict[str, Path]
    ) -> list[ExternalAnalysisArtifact]:
        artifacts: list[ExternalAnalysisArtifact] = []
        if not self._analysis_adapters:
            return artifacts
        if not self._manual_external_analysis_requests:
            return artifacts
        if not self._analysis_policy.manual:
            self._log_event(
                "external-analysis",
                "INFO",
                "Manual external analysis ignored",
                event="manual-disabled",
                manual_request_count=len(self._manual_external_analysis_requests),
            )
            return artifacts
        record_lookup = {
            normalize_ref(record.target.label): record for record in records
        }
        for request in self._manual_external_analysis_requests:
            adapter = self._analysis_adapters.get(request.tool)
            if not adapter:
                self._log_event(
                    "external-analysis",
                    "WARNING",
                    "External analysis adapter unavailable",
                    tool=request.tool,
                    cluster_label=request.target,
                )
                continue
            record = record_lookup.get(request.target)
            if not record:
                self._log_event(
                    "external-analysis",
                    "WARNING",
                    "External analysis target missing",
                    tool=request.tool,
                    cluster_label=request.target,
                )
                continue
            source_artifact = (
                record.assessment.artifact_path if record.assessment else str(record.path)
            )
            analysis_request = ExternalAnalysisRequest(
                run_id=self.run_id,
                cluster_label=record.target.label,
                source_artifact=source_artifact,
            )
            artifact = adapter.run(analysis_request)
            artifact_path = directories["external_analysis"] / (
                f"{self.run_id}-{record.target.label}-{adapter.name}.json"
            )
            artifact_with_path = replace(artifact, artifact_path=str(artifact_path))
            write_external_analysis_artifact(artifact_path, artifact_with_path)
            if artifact_with_path.status == ExternalAnalysisStatus.SUCCESS:
                severity = "INFO"
            elif artifact_with_path.status == ExternalAnalysisStatus.FAILED:
                severity = "ERROR"
            else:
                severity = "WARNING"
            self._log_event(
                "external-analysis",
                severity,
                "External analysis result recorded",
                tool=adapter.name,
                cluster_label=record.target.label,
                status=artifact_with_path.status.value,
                artifact_path=str(artifact_path),
            )
            notification = build_external_analysis_notification(artifact_with_path)
            self._record_notification(directories["notifications"], notification)
            artifacts.append(artifact_with_path)
        return artifacts

    def _run_auto_drilldown_analysis(
        self, drilldowns: list[DrilldownArtifact], directories: dict[str, Path]
    ) -> list[ExternalAnalysisArtifact]:
        policy = self.config.external_analysis.auto_drilldown
        if not policy.enabled or policy.max_per_run <= 0 or not drilldowns:
            return []
        provider_name = policy.provider or "default"
        artifacts: list[ExternalAnalysisArtifact] = []
        attempts = 0
        for drilldown in drilldowns:
            if attempts >= policy.max_per_run:
                break
            attempts += 1
            artifact_path = directories["external_analysis"] / (
                f"{self.run_id}-{drilldown.label}-auto-{provider_name}.json"
            )
            start = time.perf_counter()
            status = ExternalAnalysisStatus.FAILED
            summary: str | None = None
            findings: tuple[str, ...] = ()
            next_checks: tuple[str, ...] = ()
            payload: dict[str, object] | None = None
            error_summary: str | None = None
            skip_reason: str | None = None
            try:
                assessment = assess_drilldown_artifact(drilldown, provider_name=provider_name)
                payload = assessment.to_dict()
                summary = (
                    assessment.recommended_action.description
                    if assessment.recommended_action
                    else (assessment.hypotheses[0].description if assessment.hypotheses else "Auto drilldown interpretation")
                )
                findings = tuple(entry.description for entry in assessment.findings)
                next_checks = tuple(entry.description for entry in assessment.next_evidence_to_collect)
                status = ExternalAnalysisStatus.SUCCESS
            except ValueError as exc:
                status = ExternalAnalysisStatus.SKIPPED
                summary = str(exc)
                skip_reason = str(exc)
                error_summary = None
                payload = None
            except Exception as exc:
                status = ExternalAnalysisStatus.FAILED
                summary = str(exc)
                error_summary = str(exc)
                payload = None
            duration_ms = int((time.perf_counter() - start) * 1000)
            artifact = ExternalAnalysisArtifact(
                tool_name="llm-autodrilldown",
                run_id=self.run_id,
                cluster_label=drilldown.label,
                run_label=self.run_label,
                source_artifact=drilldown.artifact_path,
                summary=summary,
                findings=findings,
                suggested_next_checks=next_checks,
                status=status,
                raw_output=None,
                timestamp=datetime.now(UTC),
                artifact_path=str(artifact_path),
                provider=provider_name,
                duration_ms=duration_ms,
                purpose=ExternalAnalysisPurpose.AUTO_DRILLDOWN,
                payload=payload,
                error_summary=error_summary,
                skip_reason=skip_reason,
            )
            write_external_analysis_artifact(artifact_path, artifact)
            severity = (
                "INFO"
                if status == ExternalAnalysisStatus.SUCCESS
                else "WARNING"
                if status == ExternalAnalysisStatus.SKIPPED
                else "ERROR"
            )
            self._log_event(
                "external-analysis",
                severity,
                "Auto drilldown interpretation recorded",
                tool=provider_name,
                cluster_label=drilldown.label,
                status=status.value,
                artifact_path=str(artifact_path),
                event="auto-drilldown",
            )
            artifacts.append(artifact)
            if status == ExternalAnalysisStatus.SKIPPED and skip_reason:
                break
        return artifacts

    def _run_review_enrichment(
        self, review_path: Path | None, directories: dict[str, Path]
    ) -> ExternalAnalysisArtifact | None:
        policy = self.config.external_analysis.review_enrichment
        if not policy.enabled or not review_path:
            return None
        provider = (policy.provider or "").strip()
        provider_segment = _safe_label(provider) if provider else "review-enrichment"
        artifact_path = directories["external_analysis"] / (
            f"{self.run_id}-review-enrichment-{provider_segment}.json"
        )
        start = time.perf_counter()
        try:
            if not provider:
                raise ValueError("No review enrichment provider configured")
            adapter = self._analysis_adapters.get(provider) or self._analysis_adapters.get(
                provider.lower()
            )
            if not adapter:
                raise ValueError(f"Adapter '{provider}' is not registered for review enrichment")
            request = ExternalAnalysisRequest(
                run_id=self.run_id,
                cluster_label=self.run_label,
                source_artifact=str(review_path),
            )
            artifact = adapter.run(request)
            duration_ms = int((time.perf_counter() - start) * 1000)
            artifact = replace(
                artifact,
                run_id=self.run_id,
                artifact_path=str(artifact_path),
                provider=provider,
                duration_ms=duration_ms,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            )
        except ValueError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            artifact = ExternalAnalysisArtifact(
                tool_name=provider or "review-enrichment",
                run_id=self.run_id,
                cluster_label=self.run_label,
                run_label=self.run_label,
                source_artifact=str(review_path),
                summary=str(exc),
                status=ExternalAnalysisStatus.SKIPPED,
                timestamp=datetime.now(UTC),
                artifact_path=str(artifact_path),
                provider=provider or None,
                duration_ms=duration_ms,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
                skip_reason=str(exc),
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            artifact = ExternalAnalysisArtifact(
                tool_name=provider or "review-enrichment",
                run_id=self.run_id,
                cluster_label=self.run_label,
                run_label=self.run_label,
                source_artifact=str(review_path),
                summary=str(exc),
                status=ExternalAnalysisStatus.FAILED,
                timestamp=datetime.now(UTC),
                artifact_path=str(artifact_path),
                provider=provider,
                duration_ms=duration_ms,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
                error_summary=str(exc),
            )
        write_external_analysis_artifact(artifact_path, artifact)
        severity = (
            "INFO"
            if artifact.status == ExternalAnalysisStatus.SUCCESS
            else "WARNING"
            if artifact.status == ExternalAnalysisStatus.SKIPPED
            else "ERROR"
        )
        message = (
            "Review enrichment recorded"
            if artifact.status == ExternalAnalysisStatus.SUCCESS
            else "Review enrichment skipped"
            if artifact.status == ExternalAnalysisStatus.SKIPPED
            else "Review enrichment failed"
        )
        # Extract nextChecks from the enrichment payload for structured logging
        next_checks_count = 0
        enrichment_payload = artifact.payload if isinstance(artifact.payload, dict) else {}
        if enrichment_payload:
            next_checks = enrichment_payload.get("nextChecks") or enrichment_payload.get("next_checks")
            if isinstance(next_checks, list):
                next_checks_count = len(next_checks)

        # Classify the payload shape for observability
        shape_analysis = classify_review_enrichment_shape(enrichment_payload)

        # Emit shape classification log
        self._log_event(
            "review-enrichment",
            "INFO",
            f"Review enrichment payload shape: {shape_analysis.classification.value}",
            run_label=self.run_label,
            run_id=self.run_id,
            provider=provider or "unspecified",
            artifact_path=str(artifact_path),
            status=artifact.status.value,
            shape_classification=shape_analysis.classification.value,
            reason=shape_analysis.reason,
            raw_payload_keys=list(shape_analysis.raw_payload_keys)[:10],  # Limit to first 10 keys
            summary_present=shape_analysis.summary_present,
            triage_order_count=shape_analysis.triage_order_count,
            top_concerns_count=shape_analysis.top_concerns_count,
            evidence_gaps_count=shape_analysis.evidence_gaps_count,
            next_checks_count=shape_analysis.next_checks_count,
            focus_notes_count=shape_analysis.focus_notes_count,
            event="review-enrichment-shape",
        )

        # Build error_summary or skip_reason for structured logging
        error_summary = artifact.error_summary
        skip_reason = artifact.skip_reason

        self._log_event(
            "review-enrichment",
            severity,
            message,
            run_label=self.run_label,
            run_id=self.run_id,
            provider=provider or "unspecified",
            artifact_path=str(artifact_path),
            status=artifact.status.value,
            next_checks_count=next_checks_count,
            error_summary=error_summary,
            skip_reason=skip_reason,
            event="review-enrichment-result",
        )
        return artifact

    def _run_next_check_planning(
        self,
        review_path: Path | None,
        enrichment_artifact: ExternalAnalysisArtifact | None,
        directories: dict[str, Path],
    ) -> ExternalAnalysisArtifact | None:
        if not review_path or not enrichment_artifact:
            # Log that planner was skipped because no enrichment artifact
            self._log_event(
                "next-check-planner",
                "DEBUG",
                "Next-check planner skipped",
                run_label=self.run_label,
                run_id=self.run_id,
                source_enrichment_artifact_path=str(enrichment_artifact.artifact_path) if enrichment_artifact else None,
                reason="no_enrichment_artifact",
                event="next-check-planning-skipped",
            )
            return None
        plan = plan_next_checks(review_path, self.run_id, enrichment_artifact)
        if not plan:
            # Log that planner produced no candidates
            self._log_event(
                "next-check-planner",
                "INFO",
                "Next-check planner produced no candidates",
                run_label=self.run_label,
                run_id=self.run_id,
                source_enrichment_artifact_path=str(enrichment_artifact.artifact_path),
                source_next_checks_count=len(enrichment_artifact.suggested_next_checks) if enrichment_artifact.suggested_next_checks else 0,
                candidate_count=0,
                reason="no_candidates_from_planner",
                event="next-check-planning-no-candidates",
            )
            return None
        artifact_path = directories["external_analysis"] / (
            f"{self.run_id}-next-check-plan.json"
        )
        candidate_count = len(plan.candidates)
        summary = (
            f"Planned {candidate_count} next-check candidate(s)"
            if candidate_count
            else "No actionable next checks"
        )
        artifact = ExternalAnalysisArtifact(
            tool_name="next-check-planner",
            run_id=self.run_id,
            cluster_label=self.run_label,
            run_label=self.run_label,
            source_artifact=str(review_path),
            summary=summary,
            findings=(),
            suggested_next_checks=(),
            status=ExternalAnalysisStatus.SUCCESS,
            raw_output=None,
            timestamp=datetime.now(UTC),
            artifact_path=str(artifact_path),
            provider=enrichment_artifact.provider,
            duration_ms=0,
            purpose=ExternalAnalysisPurpose.NEXT_CHECK_PLANNING,
            payload=plan.to_payload(),
        )
        write_external_analysis_artifact(artifact_path, artifact)
        self._log_event(
            "next-check-planner",
            "INFO",
            "Next-check plan recorded",
            run_label=self.run_label,
            run_id=self.run_id,
            source_enrichment_artifact_path=str(enrichment_artifact.artifact_path),
            source_next_checks_count=len(enrichment_artifact.suggested_next_checks) if enrichment_artifact.suggested_next_checks else 0,
            candidate_count=candidate_count,
            plan_artifact_path=str(artifact_path),
            reason="plan_recorded" if candidate_count > 0 else "no_candidates",
            event="next-check-planning",
        )
        return artifact

    def _write_review_artifact(
        self,
        assessments: list[HealthAssessmentArtifact],
        drilldowns: list[DrilldownArtifact],
        directories: dict[str, Path],
    ) -> tuple[Path | None, tuple[HealthProposal, ...]]:
        directory = directories["reviews"]
        proposal_records: list[HealthProposal] = []
        try:
            review = build_health_review(
                run_id=self.run_id,
                assessments=assessments,
                drilldowns=drilldowns,
                warning_threshold=self.config.trigger_policy.warning_event_threshold,
            )
        except Exception as exc:
            self._log_event(
                "review-assessment",
                "ERROR",
                "Health review generation failed",
                severity_reason=str(exc),
                event="review-failed",
            )
            return None, ()
        path = directory / f"{self.run_id}-review.json"
        _write_json(review.to_dict(), path)
        self._log_event(
            "review-assessment",
            "INFO",
            "Health review written",
            artifact_path=str(path),
            assessment_count=len(assessments),
            drilldown_count=len(drilldowns),
            event="review-created",
        )
        try:
            trigger_details = collect_trigger_details(directories["triggers"], self.run_id)
            proposals = generate_proposals_from_review(
                review=review,
                review_path=path,
                run_id=self.run_id,
                warning_threshold=self.config.trigger_policy.warning_event_threshold,
                baseline_policy=self.config.baseline_policy,
                trigger_details=trigger_details,
            )
            for proposal in proposals:
                proposal_path = directories["proposals"] / f"{proposal.proposal_id}.json"
                HealthProposalValidator.validate(proposal.to_dict())
                _write_json(proposal.to_dict(), proposal_path)
                self._log_event(
                    "proposal-promotion",
                    "INFO",
                    "Health proposal written",
                    proposal_id=proposal.proposal_id,
                    artifact_path=str(proposal_path),
                    event="proposal-generated",
                )
                proposal_with_path = replace(proposal, artifact_path=str(proposal_path))
                proposal_records.append(proposal_with_path)
                notification = build_proposal_created_notification(self.run_id, proposal)
                self._record_notification(directories["notifications"], notification)
        except Exception as exc:
            self._log_event(
                "proposal-promotion",
                "ERROR",
                "Health proposal generation failed",
                severity_reason=str(exc),
                event="proposal-failed",
            )
        return path, tuple(proposal_records)

    def _determine_drilldown_reasons(
        self,
        record: HealthSnapshotRecord,
        previous_history: dict[str, HealthHistoryEntry],
    ) -> tuple[str, ...]:
        if not record.assessment:
            return ()
        reasons: list[str] = []
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
        if record.image_pull_secret_insight:
            reasons.append(BROKEN_IMAGE_PULL_SECRET_REASON)
        reasons.extend(record.pattern_reasons)
        unique_reasons = tuple(dict.fromkeys(reasons))
        return unique_reasons

    def _evaluate_triggers(
        self,
        records: list[HealthSnapshotRecord],
        history: dict[str, HealthHistoryEntry],
        directories: dict[str, Path],
    ) -> list[ComparisonTriggerArtifact]:
        triggers: list[ComparisonTriggerArtifact] = []
        decisions: list[ComparisonDecision] = []
        if not self.config.peers:
            self._log_event(
                "health-loop",
                "INFO",
                _HEALTH_ONLY_MESSAGE,
                event="health-only",
            )
            return triggers
        record_lookup: dict[str, HealthSnapshotRecord] = {}
        for record in records:
            primary_ref, label_ref = record.refs()
            record_lookup[primary_ref] = record
            record_lookup[label_ref] = record
        for peer in self.config.peers:
            primary_record = record_lookup.get(peer.primary)
            if not primary_record:
                continue
            secondary_record = record_lookup.get(peer.secondary)
            if not secondary_record:
                continue
            expected_categories = tuple(sorted(peer.expected_drift_categories))
            ignored_categories = tuple(
                sorted(
                    set(primary_record.baseline_policy.ignored_drift_categories)
                    | set(secondary_record.baseline_policy.ignored_drift_categories)
                )
            )
            peer_notes = peer.notes
            (
                policy_eligible,
                policy_reason,
                primary_class,
                secondary_class,
                primary_role,
                secondary_role,
                primary_cohort,
                secondary_cohort,
            ) = _policy_eligible_pair(
                primary_record,
                secondary_record,
                peer.intent,
                self.baseline_registry,
            )
            classification_label = peer.intent.label()
            trigger_details: list[TriggerDetail] = []
            if policy_eligible:
                trigger_details = determine_pair_trigger_reasons(
                    primary_record,
                    secondary_record,
                    self.config.trigger_policy,
                    history,
                    self._manual_keys,
                    primary_record.baseline_policy,
                    self.baseline_registry,
                    classification_label,
                )
            triggered = bool(trigger_details)
            if not policy_eligible:
                self._log_event(
                    "health-loop",
                    "INFO",
                    "Comparison skipped",
                    cluster_label=primary_record.target.label,
                    comparison_target=secondary_record.target.label,
                    comparison_intent=classification_label,
                    policy_eligible=False,
                    severity_reason=policy_reason,
                    primary_class=primary_class,
                    secondary_class=secondary_class,
                    primary_role=primary_role,
                    secondary_role=secondary_role,
                    primary_cohort=primary_cohort,
                    secondary_cohort=secondary_cohort,
                    expected_drift_categories=list(expected_categories),
                    ignored_drift_categories=list(ignored_categories),
                    event="comparison-skip",
                )
            decision_reason = (
                policy_reason
                if not policy_eligible
                else "; ".join(detail.reason for detail in trigger_details) if triggered else "policy compatible but no triggers fired"
            )
            decisions.append(
                ComparisonDecision(
                    primary_label=primary_record.target.label,
                    secondary_label=secondary_record.target.label,
                    policy_eligible=policy_eligible,
                    triggered=triggered,
                    comparison_intent=classification_label,
                    reason=decision_reason,
                    primary_class=primary_class,
                    secondary_class=secondary_class,
                    primary_role=primary_role,
                    secondary_role=secondary_role,
                    primary_cohort=primary_cohort,
                    secondary_cohort=secondary_cohort,
                    expected_drift_categories=expected_categories,
                    ignored_drift_categories=ignored_categories,
                    notes=peer_notes,
                )
            )
            if not policy_eligible or not triggered:
                continue
            comparison = self.comparison_fn(primary_record.snapshot, secondary_record.snapshot)
            summary = {key: len(value) for key, value in comparison.differences.items()}
            comparison_path = directories["comparisons"] / f"{self.run_id}-{primary_record.target.label}-vs-{secondary_record.target.label}-comparison.json"
            _write_json(
                {
                    "differences": _serialize_value(comparison.differences),
                    "trigger_reasons": [detail.reason for detail in trigger_details],
                    "trigger_details": [detail.to_dict() for detail in trigger_details],
                    "comparison_intent": classification_label,
                    "expected_drift_categories": list(expected_categories),
                    "ignored_drift_categories": list(ignored_categories),
                    "peer_notes": peer_notes,
                },
                comparison_path,
            )
            artifact = ComparisonTriggerArtifact(
                run_label=self.run_label,
                run_id=self.run_id,
                timestamp=datetime.now(UTC),
                primary=primary_record.target.context,
                secondary=secondary_record.target.context,
                primary_label=primary_record.target.label,
                secondary_label=secondary_record.target.label,
                trigger_reasons=tuple(detail.reason for detail in trigger_details),
                comparison_summary=summary,
                differences=_serialize_value(comparison.differences),
                trigger_details=tuple(trigger_details),
                comparison_intent=classification_label,
                expected_drift_categories=expected_categories,
                ignored_drift_categories=ignored_categories,
                peer_notes=peer_notes,
                notes="; ".join(detail.reason for detail in trigger_details),
            )
            triggers.append(artifact)
            trigger_path = directories["triggers"] / f"{self.run_id}-{primary_record.target.label}-vs-{secondary_record.target.label}-trigger.json"
            _write_json(artifact.to_dict(), trigger_path)
            self._log_event(
                "health-loop",
                "INFO",
                "Comparison trigger artifact recorded",
                cluster_label=primary_record.target.label,
                comparison_target=secondary_record.target.label,
                artifact_path=str(trigger_path),
                event="comparison-trigger",
                severity_reason="; ".join(detail.reason for detail in trigger_details),
            )
            if triggered and peer.intent == ComparisonIntent.SUSPICIOUS_DRIFT:
                notification = build_suspicious_comparison_notification(artifact)
                self._record_notification(directories["notifications"], notification)
        decision_path = directories["root"] / f"{self.run_id}-comparison-decisions.json"
        for decision in decisions:
            ComparisonDecisionValidator.validate(decision.to_dict())
        _write_json([decision.to_dict() for decision in decisions], decision_path)
        return triggers

    def _load_history(self, history_path: Path) -> dict[str, HealthHistoryEntry]:
        if not history_path.exists():
            return {}
        raw = json.loads(history_path.read_text(encoding="utf-8"))
        history: dict[str, HealthHistoryEntry] = {}
        for cluster_id, entry in raw.items():
            if isinstance(entry, dict):
                history[cluster_id] = HealthHistoryEntry.from_dict(cluster_id, entry)
        return history

    def _persist_history(self, history: dict[str, HealthHistoryEntry], history_path: Path) -> None:
        data = {cluster_id: entry.to_dict() for cluster_id, entry in history.items()}
        _write_json(data, history_path)

    def _run_alertmanager_discovery(
        self,
        records: list[HealthSnapshotRecord],
        directories: dict[str, Path],
    ) -> None:
        """Run Alertmanager discovery for each cluster target and persist the inventory.
        
        Discovers Alertmanager instances in each cluster, verifies them, and writes
        the aggregated inventory to a run-scoped artifact.
        
        This is non-fatal: discovery failures are logged but do not stop the run.
        """
        if not records:
            self._log_event(
                "alertmanager-discovery",
                "DEBUG",
                "Alertmanager discovery skipped: no cluster records",
                event="alertmanager-discovery-skipped",
                reason="no_records",
            )
            return
        
        # Aggregate all discovered sources across all targets
        aggregated_inventory: AlertmanagerSourceInventory | None = None
        
        for record in records:
            target_context = record.target.context
            cluster_label = record.target.label
            
            # Log discovery start for this target
            self._log_event(
                "alertmanager-discovery",
                "DEBUG",
                "Starting Alertmanager discovery for cluster target",
                event="alertmanager-discovery-start",
                cluster_label=cluster_label,
                cluster_context=target_context,
                artifact_directory=str(directories["root"]),
            )
            
            try:
                # Run discovery for this context
                discovered_inventory = discover_alertmanagers(context=target_context)
                
                # Log discovery result counts by origin
                crd_count = len(discovered_inventory.get_by_origin(
                    AlertmanagerSourceOrigin.ALERTMANAGER_CRD
                ))
                prom_crd_count = len(discovered_inventory.get_by_origin(
                    AlertmanagerSourceOrigin.PROMETHEUS_CRD_CONFIG
                ))
                service_count = len(discovered_inventory.get_by_origin(
                    AlertmanagerSourceOrigin.SERVICE_HEURISTIC
                ))
                manual_count = len(discovered_inventory.get_by_origin(
                    AlertmanagerSourceOrigin.MANUAL
                ))
                
                self._log_event(
                    "alertmanager-discovery",
                    "DEBUG",
                    "Alertmanager discovery completed for cluster target",
                    event="alertmanager-discovery-result",
                    cluster_label=cluster_label,
                    cluster_context=target_context,
                    candidates_found=len(discovered_inventory.sources),
                    by_origin={
                        "alertmanager-crd": crd_count,
                        "prometheus-crd-config": prom_crd_count,
                        "service-heuristic": service_count,
                        "manual": manual_count,
                    },
                )
                
                # Merge into aggregated inventory
                if aggregated_inventory is None:
                    aggregated_inventory = discovered_inventory
                else:
                    for source in discovered_inventory.sources.values():
                        aggregated_inventory.add_source(source)
                        
            except Exception as exc:
                self._log_event(
                    "alertmanager-discovery",
                    "WARNING",
                    "Alertmanager discovery failed for cluster target",
                    event="alertmanager-discovery-failed",
                    cluster_label=cluster_label,
                    cluster_context=target_context,
                    severity_reason=str(exc),
                    reason="discovery-error",
                    # Run should continue (non-fatal)
                )
                continue
        
        # If we have no inventory, create empty one
        if aggregated_inventory is None:
            aggregated_inventory = AlertmanagerSourceInventory()
        
        # Note: verification step is intentionally skipped to keep discovery fast.
        # Call verify_and_update_inventory() if you need to validate source reachability.
        verified_inventory = aggregated_inventory
        
        # Deduplicate sources: merge multiple discovery strategies for the same
        # Alertmanager (e.g., CRD + Prometheus config + service heuristic) into
        # a single source with merged provenance tracking all contributing origins.
        verified_inventory = merge_deduplicate_inventory(verified_inventory)
        
        # Log verification result summary
        auto_tracked_count = len(verified_inventory.get_by_state(
            AlertmanagerSourceState.AUTO_TRACKED
        ))
        manual_count = len(verified_inventory.get_by_state(
            AlertmanagerSourceState.MANUAL
        ))
        degraded_count = len(verified_inventory.get_by_state(
            AlertmanagerSourceState.DEGRADED
        ))
        discovered_count = len(verified_inventory.get_by_state(
            AlertmanagerSourceState.DISCOVERED
        ))
        
        self._log_event(
            "alertmanager-discovery",
            "DEBUG",
            "Alertmanager verification result",
            event="alertmanager-verification-result",
            total_sources=len(verified_inventory.sources),
            by_state={
                "auto-tracked": auto_tracked_count,
                "manual": manual_count,
                "degraded": degraded_count,
                "discovered": discovered_count,
            },
        )
        
        # Write the inventory artifact
        try:
            artifact_path = write_alertmanager_sources(
                directories["root"],
                verified_inventory,
                self.run_id,
            )
            
            self._log_event(
                "alertmanager-discovery",
                "INFO",
                "Alertmanager sources inventory written",
                event="alertmanager-sources-written",
                source_count=len(verified_inventory.sources),
                artifact_path=str(artifact_path),
            )
        except Exception as exc:
            self._log_event(
                "alertmanager-discovery",
                "ERROR",
                "Failed to write Alertmanager sources inventory",
                event="alertmanager-sources-write-failed",
                severity_reason=str(exc),
                reason="write-error",
            )
            # Continue without failing the run

class BaselineRegistry:
    def __init__(self, policies: Iterable[BaselinePolicy] | None = None) -> None:
        self._policies: list[BaselinePolicy] = []
        if policies:
            for policy in policies:
                self.add(policy)

    def add(self, policy: BaselinePolicy) -> None:
        if policy in self._policies:
            return
        self._policies.append(policy)

    def role_for(self, reference: str) -> str | None:
        for policy in self._policies:
            role = policy.role_for(reference)
            if role:
                return role
        return None


def _resolve_peer_role(record: HealthSnapshotRecord, registry: BaselineRegistry | None) -> str | None:
    explicit_role = record.target.cluster_role
    if explicit_role:
        return explicit_role.strip() or None
    if registry:
        for reference in record.refs():
            role = registry.role_for(reference)
            if role:
                return role
    return None


def _policy_eligible_pair(
    primary: HealthSnapshotRecord,
    secondary: HealthSnapshotRecord,
    intent: ComparisonIntent,
    baseline_registry: BaselineRegistry | None,
) -> tuple[
    bool,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    primary_class = primary.target.cluster_class
    secondary_class = secondary.target.cluster_class
    primary_role = _resolve_peer_role(primary, baseline_registry)
    secondary_role = _resolve_peer_role(secondary, baseline_registry)
    primary_cohort = primary.target.baseline_cohort
    secondary_cohort = secondary.target.baseline_cohort
    reasons: list[str] = []
    if not primary_class or not secondary_class:
        reasons.append("cluster class metadata missing")
    elif primary_class != secondary_class:
        reasons.append("cluster class mismatch")
    if intent == ComparisonIntent.SUSPICIOUS_DRIFT:
        if not primary_role or not secondary_role:
            reasons.append("peer role metadata missing")
        elif primary_role != secondary_role:
            reasons.append("peer roles differ")
        if not primary_cohort or not secondary_cohort:
            reasons.append("baseline cohort metadata missing")
        elif primary_cohort != secondary_cohort:
            reasons.append(
                f"baseline cohorts differ ({primary_cohort} vs {secondary_cohort})"
            )
    if intent == ComparisonIntent.IRRELEVANT_DRIFT:
        reasons.append("comparison intent marked this pair as irrelevant drift")
    if reasons:
        return (
            False,
            "; ".join(reasons),
            primary_class,
            secondary_class,
            primary_role,
            secondary_role,
            primary_cohort,
            secondary_cohort,
        )
    return (
        True,
        "policy compatible",
        primary_class,
        secondary_class,
        primary_role,
        secondary_role,
        primary_cohort,
        secondary_cohort,
    )


def _safe_int(value: Any | None) -> int | None:
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


def _parse_comparison_intent(value: Any | None) -> ComparisonIntent:
    if value is None:
        return ComparisonIntent.SUSPICIOUS_DRIFT
    try:
        return ComparisonIntent(str(value))
    except ValueError:
        return ComparisonIntent.SUSPICIOUS_DRIFT


def _parse_manual_triggers(values: Sequence[str]) -> list[ManualComparison]:
    manual: list[ManualComparison] = []
    for raw_value in values:
        if ":" not in raw_value:
            continue
        primary, secondary = raw_value.split(":", 1)
        manual.append(
            ManualComparison(primary=normalize_ref(primary), secondary=normalize_ref(secondary))
        )
    return manual


def _parse_manual_external_analysis_requests(values: Sequence[str]) -> list[ManualExternalAnalysisRequest]:
    manual: list[ManualExternalAnalysisRequest] = []
    for raw_value in values:
        if ":" not in raw_value:
            continue
        tool_raw, target_raw = raw_value.split(":", 1)
        tool = tool_raw.strip().lower()
        target = normalize_ref(target_raw)
        if not tool or not target:
            continue
        manual.append(ManualExternalAnalysisRequest(tool=tool, target=target))
    return manual


def _validate_suspicious_pairs(
    peers: Sequence[ComparisonPeer],
    target_lookup: dict[str, HealthTarget],
    baseline: BaselinePolicy,
) -> None:
    issues: list[str] = []
    for peer in peers:
        if peer.intent != ComparisonIntent.SUSPICIOUS_DRIFT:
            continue
        primary = target_lookup.get(peer.primary)
        secondary = target_lookup.get(peer.secondary)
        if not primary or not secondary:
            issues.append(
                f"Suspicious-drift mapping {peer.primary} -> {peer.secondary} references unknown targets."
            )
            continue
        problems: list[str] = []
        if primary.cluster_class != secondary.cluster_class:
            problems.append(
                f"cluster_class differs ({primary.cluster_class or 'missing'} vs {secondary.cluster_class or 'missing'})"
            )
        if primary.baseline_cohort != secondary.baseline_cohort:
            problems.append(
                f"baseline_cohort differs ({primary.baseline_cohort or 'missing'} vs {secondary.baseline_cohort or 'missing'})"
            )
        if problems:
            issues.append(

                    f"Suspicious-drift pair {primary.label} ({primary.context}) vs "
                    f"{secondary.label} ({secondary.context}) invalid: "
                    + "; ".join(problems)

            )
    if issues:
        raise ValueError(
            "Suspicious-drift comparisons must stay within the same class/cohort and be backed by baseline peer roles. "
            + "Fix the following issues:\n- "
            + "\n- ".join(issues)
        )


def run_health_loop(
    config_path: Path,
    manual_triggers: Sequence[str] | None = None,
    manual_drilldown_contexts: Sequence[str] | None = None,
    manual_external_analysis: Sequence[str] | None = None,
    quiet: bool = False,
    drilldown_collector: DrilldownCollector | None = None,
    expected_scheduler_interval_seconds: int | None = None,
    run_id: str | None = None,
) -> tuple[
    int,
    list[HealthAssessmentArtifact],
    list[ComparisonTriggerArtifact],
    list[DrilldownArtifact],
    list[ExternalAnalysisArtifact],
    ExternalAnalysisSettings,
]:
    try:
        config = HealthRunConfig.load(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        emit_structured_log(
            component="health-loop",
            severity="ERROR",
            message=f"Unable to load health config {config_path}: {exc}",
            run_label=_safe_label(str(config_path.stem)),
            log_path=DEFAULT_HEALTH_LOG,
            metadata={"config_path": str(config_path), "severity_reason": str(exc)},
        )
        return 1, [], [], [], [], ExternalAnalysisSettings()
    try:
        contexts = list_kube_contexts()
    except RuntimeError as exc:
        emit_structured_log(
            component="health-loop",
            severity="ERROR",
            message=f"Unable to discover kube contexts: {exc}",
            run_label=_safe_label(str(config_path.stem)),
            log_path=DEFAULT_HEALTH_LOG,
            metadata={"severity_reason": str(exc)},
        )
        return 1, [], [], [], [], ExternalAnalysisSettings()
    manual_overrides = _parse_manual_triggers(manual_triggers or [])
    manual_analysis_requests = _parse_manual_external_analysis_requests(
        manual_external_analysis or []
    )
    runner = HealthLoopRunner(
        config,
        contexts,
        manual_overrides=manual_overrides,
        manual_drilldown_contexts=manual_drilldown_contexts,
        manual_external_analysis=manual_analysis_requests,
        quiet=quiet,
        drilldown_collector=drilldown_collector,
        expected_scheduler_interval_seconds=expected_scheduler_interval_seconds,
    )
    assessments, triggers, drilldowns = runner.execute()
    external_artifacts = runner.latest_external_artifacts
    return 0, assessments, triggers, drilldowns, external_artifacts, runner.config.external_analysis


_HEALTH_LOCK_FILENAME = ".health-loop.lock"
_HEALTH_ONLY_MESSAGE = "No peer mappings configured; running health-only mode."


@dataclass(frozen=True)
class ProcessIdentity:
    start_time: str | None
    cmdline: str | None
    hostname: str | None

    @property
    def signature(self) -> str | None:
        values = (self.start_time, self.cmdline, self.hostname)
        if not any(values):
            return None
        payload = "|".join(value or "" for value in values)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class LockFileSnapshot:
    timestamp_value: str | None
    timestamp: datetime | None
    pid: int | None
    mtime: float | None
    identity: ProcessIdentity | None
    scheduler_instance_id: str | None
    attempted_run_id: str | None
    scheduler_pid: int | None
    child_pid: int | None
    child_start_time: str | None
    run_label: str | None

    def age_seconds(self, reference: datetime) -> float | None:
        if self.timestamp is not None:
            return max(0.0, (reference - self.timestamp).total_seconds())
        if self.mtime is not None:
            return max(0.0, reference.timestamp() - self.mtime)
        return None


@dataclass(frozen=True)
class LockEvaluation:
    snapshot: LockFileSnapshot | None
    lock_age_seconds: float | None
    pid_alive: bool | None
    current_identity: ProcessIdentity | None
    identity_match: bool | None
    provenance_match: bool | None
    should_cleanup: bool
    stale_decision: str
    cleanup_reason: str | None


class HealthLoopScheduler:
    _LOCK_SKIP_ESCALATION_THRESHOLD = 3
    _LOCK_STALE_MIN_SECONDS = 60
    _LOCK_STALE_AGE_MULTIPLIER = 2

    def __init__(
        self,
        config_path: Path,
        manual_triggers: Sequence[str],
        manual_drilldown_contexts: Sequence[str] | None,
        manual_external_analysis: Sequence[str] | None,
        quiet: bool,
        interval_seconds: int | None,
        max_runs: int | None,
        run_once: bool,
        output_dir: Path,
        run_label: str | None = None,
    ) -> None:
        self._config_path = config_path
        self._manual_triggers = tuple(manual_triggers)
        self._manual_drilldown_contexts = tuple(manual_drilldown_contexts or [])
        self._manual_external_analysis = tuple(manual_external_analysis or [])
        self._quiet = quiet
        self._interval_seconds = interval_seconds
        self._max_runs = max_runs
        self._run_once = run_once
        self._lock_path = output_dir / "health" / _HEALTH_LOCK_FILENAME
        self._run_label = run_label or "health-scheduler"
        self._log_path = output_dir / "health" / "scheduler.log"
        self._last_run_finish_time: float | None = None
        self._runs_dir_base = output_dir

        self._instance_id = uuid4().hex
        self._pending_run_id: str | None = None
        self._pending_run_start: datetime | None = None
        self._lock_status_path = self._lock_path.parent / "lock-status.json"

        self._identity_hostname = self._resolve_hostname()
        self._proc_root = Path("/proc") if Path("/proc").exists() else None

        self._lock_skip_streak = 0
        self._lock_skip_escalation_threshold = self._LOCK_SKIP_ESCALATION_THRESHOLD

    def _log_event(self, severity: str, message: str, **metadata: Any) -> None:
        emit_structured_log(
            component="health-scheduler",
            message=message,
            severity=severity,
            run_label=self._run_label,
            log_path=self._log_path,
            metadata=metadata or None,
        )

    def _resolve_hostname(self) -> str | None:
        try:
            return socket.gethostname()
        except OSError:
            return None

    def _resolve_run_id(
        self,
        assessments: list[HealthAssessmentArtifact],
        triggers: list[ComparisonTriggerArtifact],
    ) -> str:
        if assessments:
            return assessments[0].run_id
        if triggers:
            return triggers[0].run_id
        return "<unknown>"

    def run(self) -> int:
        executed_runs = 0
        last_exit = 0
        self._log_event(
            "INFO",
            "Health scheduler started",
            interval_seconds=self._interval_seconds,
            max_runs=self._max_runs,
            run_once=self._run_once,
        )
        try:
            while True:
                if self._run_once and executed_runs >= 1:
                    break
                if self._max_runs is not None and executed_runs >= self._max_runs:
                    break
                run_executed = False
                self._pending_run_id = _build_runtime_run_id(self._run_label)
                self._pending_run_start = datetime.now(UTC)
                if not self._acquire_lock():
                    run_executed = False
                else:
                    try:
                        run_start_time = time.time()
                        freshness_age_seconds = (
                            run_start_time - self._last_run_finish_time
                            if self._last_run_finish_time is not None
                            else None
                        )
                        (
                            exit_code,
                            assessments,
                            triggers,
                            drilldowns,
                            external_artifacts,
                            settings,
                        ) = run_health_loop(
                            self._config_path,
                            manual_triggers=self._manual_triggers,
                            manual_drilldown_contexts=self._manual_drilldown_contexts,
                            manual_external_analysis=self._manual_external_analysis,
                            quiet=self._quiet,
                            expected_scheduler_interval_seconds=self._interval_seconds,
                            run_id=self._pending_run_id,
                        )
                        run_id = self._resolve_run_id(assessments, triggers)
                        run_executed = True
                        last_exit = exit_code
                        if exit_code != 0:
                            self._log_event(
                                "ERROR",
                                "Health run failed",
                                run_id=run_id,
                                severity_reason=f"exit_code={exit_code}",
                                event="run-failure",
                            )
                            return exit_code
                        executed_runs += 1
                        self._log_run_summary(
                            assessments,
                            triggers,
                            drilldowns,
                            external_artifacts,
                            settings,
                            freshness_age_seconds=freshness_age_seconds,
                            expected_interval_seconds=self._interval_seconds,
                        )
                        self._maybe_build_diagnostic_pack(run_id)
                        self._last_run_finish_time = time.time()
                    finally:
                        self._pending_run_id = None
                        self._pending_run_start = None
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
            self._log_event(
                "WARNING",
                "Health scheduler interrupted",
                event="interrupted",
                reason="keyboard",
            )
            return 1
        self._log_event(
            "INFO",
            "Health scheduler stopped",
            exit_code=last_exit,
            event="stop",
        )
        return last_exit

    def _acquire_lock(self) -> bool:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                payload = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "pid": os.getpid(),
                }
                identity = self._current_process_identity()
                identity_data = self._serialize_identity(identity)
                if identity_data:
                    payload["identity"] = identity_data
                payload["scheduler_instance_id"] = self._instance_id
                if self._pending_run_id:
                    payload["attempted_run_id"] = self._pending_run_id
                payload["scheduler_pid"] = os.getpid()
                payload["child_pid"] = os.getpid()
                if self._pending_run_start:
                    payload["child_start_time"] = self._pending_run_start.isoformat()
                payload["run_label"] = self._run_label
                with self._lock_path.open("x", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload))
                    handle.write("\n")
                self._lock_skip_streak = 0
                return True
            except FileExistsError:
                evaluation = self._evaluate_lock_state()
                if evaluation.should_cleanup and self._remove_stale_lock(evaluation):
                    self._lock_skip_streak = 0
                    continue
                self._log_lock_held(evaluation)
                return False

    def _release_lock(self) -> None:
        try:
            if self._lock_path.exists():
                self._lock_path.unlink()
        except OSError:
            pass

    def _current_process_identity(self) -> ProcessIdentity | None:
        identity = self._read_process_identity(os.getpid())
        if identity is not None:
            return identity
        if self._identity_hostname is None:
            return None
        return ProcessIdentity(None, None, self._identity_hostname)

    def _read_process_identity(self, pid: int) -> ProcessIdentity | None:
        if pid <= 0:
            return None
        hostname = self._identity_hostname
        if self._proc_root is None:
            return ProcessIdentity(None, None, hostname)
        proc_dir = self._proc_root / str(pid)
        if not proc_dir.exists():
            # Process may have exited
            return ProcessIdentity(None, None, hostname)
        start_time: str | None = None
        try:
            stat_content = (proc_dir / "stat").read_text(encoding="utf-8")
        except OSError:
            stat_content = ""
        if stat_content:
            parts = stat_content.split()
            if len(parts) > 21:
                start_time = parts[21]
        cmdline: str | None = None
        try:
            cmdline_bytes = (proc_dir / "cmdline").read_bytes()
            if cmdline_bytes:
                segments = [seg.decode("utf-8", "ignore") for seg in cmdline_bytes.split(b"\0") if seg]
                cmdline = " ".join(segments)
        except OSError:
            pass
        return ProcessIdentity(start_time, cmdline, hostname)

    def _serialize_identity(self, identity: ProcessIdentity | None) -> dict[str, str] | None:
        if identity is None:
            return None
        data: dict[str, str] = {}
        if identity.start_time is not None:
            data["start_time"] = identity.start_time
        if identity.cmdline is not None:
            data["cmdline"] = identity.cmdline
        if identity.hostname is not None:
            data["hostname"] = identity.hostname
        return data or None

    def _identity_from_mapping(
        self, raw: Mapping[str, object] | None
    ) -> ProcessIdentity | None:
        if not raw:
            return None
        start_time_raw = raw.get("start_time")
        start_time = _str_or_none(start_time_raw if isinstance(start_time_raw, str) else None)
        cmdline_raw = raw.get("cmdline")
        cmdline = _str_or_none(cmdline_raw if isinstance(cmdline_raw, str) else None)
        hostname_raw = raw.get("hostname")
        hostname = _str_or_none(hostname_raw if isinstance(hostname_raw, str) else None) or self._identity_hostname
        if start_time is None and cmdline is None and hostname is None:
            return None
        return ProcessIdentity(start_time, cmdline, hostname)

    def _identity_matches(
        self,
        stored: ProcessIdentity | None,
        current: ProcessIdentity | None,
    ) -> bool | None:
        if stored is None or current is None:
            return None
        stored_sig = stored.signature
        current_sig = current.signature
        if stored_sig is not None and current_sig is not None:
            return stored_sig == current_sig
        if stored == current:
            return True
        return None

    def _coerce_pid(self, raw: object | None) -> int | None:
        if raw is None:
            return None
        if isinstance(raw, str):
            if raw.isdigit():
                return int(raw)
            try:
                return int(raw)
            except ValueError:
                return None
        if isinstance(raw, (int, float)):
            return int(raw)
        return None

    def _evaluate_lock_state(self) -> LockEvaluation:
        snapshot = self._load_lock_snapshot()
        now = datetime.now(UTC)
        lock_age = snapshot.age_seconds(now) if snapshot else None
        current_pid = os.getpid()
        pid_alive: bool | None = None
        current_identity: ProcessIdentity | None = None
        identity_match: bool | None = None
        if snapshot and snapshot.pid is not None:
            pid_alive = self._pid_is_alive(snapshot.pid)
            if pid_alive:
                current_identity = self._read_process_identity(snapshot.pid)
                identity_match = self._identity_matches(snapshot.identity, current_identity)
        provenance_match = self._provenance_matches(snapshot)
        threshold = self._stale_lock_age_threshold()
        if snapshot is None:
            evaluation = LockEvaluation(
                snapshot=None,
                lock_age_seconds=lock_age,
                pid_alive=pid_alive,
                current_identity=current_identity,
                identity_match=identity_match,
                provenance_match=provenance_match,
                should_cleanup=False,
                stale_decision="unreadable",
                cleanup_reason=None,
            )
            self._write_lock_status(evaluation)
            return evaluation
        if snapshot.pid is None:
            stale_decision = "missing-pid"
            cleanup_reason = None
            should_cleanup = False
            if lock_age is not None and lock_age >= threshold:
                should_cleanup = True
                cleanup_reason = "missing-pid-old"
            evaluation = LockEvaluation(
                snapshot=snapshot,
                lock_age_seconds=lock_age,
                pid_alive=pid_alive,
                current_identity=current_identity,
                identity_match=identity_match,
                provenance_match=provenance_match,
                should_cleanup=should_cleanup,
                stale_decision=stale_decision,
                cleanup_reason=cleanup_reason,
            )
            self._write_lock_status(evaluation)
            return evaluation
        if pid_alive:
            if provenance_match:
                evaluation = LockEvaluation(
                    snapshot=snapshot,
                    lock_age_seconds=lock_age,
                    pid_alive=pid_alive,
                    current_identity=current_identity,
                    identity_match=identity_match,
                    provenance_match=provenance_match,
                    should_cleanup=False,
                    stale_decision="provenance-match",
                    cleanup_reason=None,
                )
                self._write_lock_status(evaluation)
                return evaluation
            if identity_match is True:
                evaluation = LockEvaluation(
                    snapshot=snapshot,
                    lock_age_seconds=lock_age,
                    pid_alive=pid_alive,
                    current_identity=current_identity,
                    identity_match=identity_match,
                    provenance_match=provenance_match,
                    should_cleanup=False,
                    stale_decision="identity-match",
                    cleanup_reason=None,
                )
                self._write_lock_status(evaluation)
                return evaluation
            if identity_match is False:
                has_scheduler_provenance = bool(
                    snapshot.scheduler_instance_id and snapshot.attempted_run_id
                )
                scheduler_mismatch = (
                    has_scheduler_provenance
                    and self._pending_run_id is not None
                    and (
                        snapshot.scheduler_instance_id != self._instance_id
                        or snapshot.attempted_run_id != self._pending_run_id
                    )
                )
                strong_identity = snapshot.identity is not None and current_identity is not None
                if scheduler_mismatch and strong_identity:
                    pid_collision = any(
                        pid == current_pid
                        for pid in (
                            snapshot.pid,
                            snapshot.scheduler_pid,
                            snapshot.child_pid,
                        )
                        if pid is not None
                    )
                    stale_decision = "pid-reuse-stale" if pid_collision else "scheduler-instance-mismatch"
                    evaluation = LockEvaluation(
                        snapshot=snapshot,
                        lock_age_seconds=lock_age,
                        pid_alive=pid_alive,
                        current_identity=current_identity,
                        identity_match=identity_match,
                        provenance_match=provenance_match,
                        should_cleanup=True,
                        stale_decision=stale_decision,
                        cleanup_reason=stale_decision,
                    )
                    self._write_lock_status(evaluation)
                    return evaluation
                cleanup_due_to_identity = lock_age is not None and lock_age >= threshold
                if cleanup_due_to_identity:
                    evaluation = LockEvaluation(
                        snapshot=snapshot,
                        lock_age_seconds=lock_age,
                        pid_alive=pid_alive,
                        current_identity=current_identity,
                        identity_match=identity_match,
                        provenance_match=provenance_match,
                        should_cleanup=True,
                        stale_decision="identity-mismatch-old",
                        cleanup_reason="identity-mismatch-old",
                    )
                    self._write_lock_status(evaluation)
                    return evaluation
                stale_decision = (
                    "foreign-live-lock"
                    if snapshot.identity is None or current_identity is None
                    else "identity-mismatch-young-foreign"
                )
                evaluation = LockEvaluation(
                    snapshot=snapshot,
                    lock_age_seconds=lock_age,
                    pid_alive=pid_alive,
                    current_identity=current_identity,
                    identity_match=identity_match,
                    provenance_match=provenance_match,
                    should_cleanup=False,
                    stale_decision=stale_decision,
                    cleanup_reason=None,
                )
                self._write_lock_status(evaluation)
                return evaluation
            evaluation = LockEvaluation(
                snapshot=snapshot,
                lock_age_seconds=lock_age,
                pid_alive=pid_alive,
                current_identity=current_identity,
                identity_match=identity_match,
                provenance_match=provenance_match,
                should_cleanup=False,
                stale_decision="foreign-live-lock",
                cleanup_reason=None,
            )
            self._write_lock_status(evaluation)
            return evaluation
        if lock_age is None:
            evaluation = LockEvaluation(
                snapshot=snapshot,
                lock_age_seconds=lock_age,
                pid_alive=pid_alive,
                current_identity=current_identity,
                identity_match=identity_match,
                provenance_match=provenance_match,
                should_cleanup=False,
                stale_decision="pid-dead-unknown-age",
                cleanup_reason=None,
            )
            self._write_lock_status(evaluation)
            return evaluation
        if lock_age < threshold:
            evaluation = LockEvaluation(
                snapshot=snapshot,
                lock_age_seconds=lock_age,
                pid_alive=pid_alive,
                current_identity=current_identity,
                identity_match=identity_match,
                provenance_match=provenance_match,
                should_cleanup=False,
                stale_decision="pid-dead-young",
                cleanup_reason=None,
            )
            self._write_lock_status(evaluation)
            return evaluation
        evaluation = LockEvaluation(
            snapshot=snapshot,
            lock_age_seconds=lock_age,
            pid_alive=pid_alive,
            current_identity=current_identity,
            identity_match=identity_match,
            provenance_match=provenance_match,
            should_cleanup=True,
            stale_decision="pid-dead-old",
            cleanup_reason="pid-not-running",
        )
        self._write_lock_status(evaluation)
        return evaluation

    def _provenance_matches(self, snapshot: LockFileSnapshot | None) -> bool:
        if not snapshot or not self._pending_run_id:
            return False
        return (
            snapshot.scheduler_instance_id == self._instance_id
            and snapshot.attempted_run_id == self._pending_run_id
        )

    def _write_lock_status(self, evaluation: LockEvaluation) -> None:
        snapshot = evaluation.snapshot
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "lock_file": str(self._lock_path),
            "lock_age_seconds": evaluation.lock_age_seconds,
            "lock_pid": snapshot.pid if snapshot else None,
            "lock_timestamp": snapshot.timestamp_value if snapshot else None,
            "pid_alive": evaluation.pid_alive,
            "identity_match": evaluation.identity_match,
            "provenance_match": evaluation.provenance_match,
            "stale_decision": evaluation.stale_decision,
            "cleanup_reason": evaluation.cleanup_reason,
            "scheduler_instance_id": snapshot.scheduler_instance_id if snapshot else None,
            "attempted_run_id": snapshot.attempted_run_id if snapshot else None,
            "scheduler_pid": snapshot.scheduler_pid if snapshot else None,
            "child_pid": snapshot.child_pid if snapshot else None,
            "child_start_time": snapshot.child_start_time if snapshot else None,
            "run_label": snapshot.run_label if snapshot else None,
        }
        try:
            self._lock_status_path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(data, self._lock_status_path)
        except OSError:
            pass

    def _load_lock_snapshot(self) -> LockFileSnapshot | None:
        try:
            stat_info = self._lock_path.stat()
        except OSError:
            return None
        try:
            contents = self._lock_path.read_text(encoding="utf-8")
        except OSError:
            contents = ""
        (
            timestamp_str,
            pid,
            identity,
            scheduler_instance_id,
            attempted_run_id,
            scheduler_pid,
            child_pid,
            child_start_time,
            run_label,
        ) = self._parse_lock_metadata(contents)
        timestamp = self._parse_lock_timestamp(timestamp_str)
        return LockFileSnapshot(
            timestamp_value=timestamp_str,
            timestamp=timestamp,
            pid=pid,
            mtime=stat_info.st_mtime,
            identity=identity,
            scheduler_instance_id=scheduler_instance_id,
            attempted_run_id=attempted_run_id,
            scheduler_pid=scheduler_pid,
            child_pid=child_pid,
            child_start_time=child_start_time,
            run_label=run_label,
        )

    def _parse_lock_metadata(
        self, contents: str
    ) -> tuple[
        str | None,
        int | None,
        ProcessIdentity | None,
        str | None,
        str | None,
        int | None,
        int | None,
        str | None,
        str | None,
    ]:
        trimmed = contents.strip()
        if trimmed.startswith("{"):
            try:
                raw = json.loads(trimmed)
            except json.JSONDecodeError:
                return (
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                )
            timestamp = _str_or_none(raw.get("timestamp"))
            pid = self._coerce_pid(raw.get("pid"))
            identity_raw = raw.get("identity")
            identity = (
                self._identity_from_mapping(identity_raw)
                if isinstance(identity_raw, Mapping)
                else None
            )
            scheduler_instance_id = _str_or_none(raw.get("scheduler_instance_id"))
            attempted_run_id = _str_or_none(raw.get("attempted_run_id"))
            scheduler_pid = self._coerce_pid(raw.get("scheduler_pid"))
            child_pid = self._coerce_pid(raw.get("child_pid"))
            child_start_time = _str_or_none(raw.get("child_start_time"))
            run_label = _str_or_none(raw.get("run_label"))
            return (
                timestamp,
                pid,
                identity,
                scheduler_instance_id,
                attempted_run_id,
                scheduler_pid,
                child_pid,
                child_start_time,
                run_label,
            )
        line = contents.splitlines()[0] if contents else ""
        parts = line.split()
        legacy_timestamp: str | None = parts[0] if parts else None
        legacy_pid: int | None = None
        for part in parts:
            if part.startswith("pid="):
                try:
                    legacy_pid = int(part.split("=", 1)[1])
                except ValueError:
                    legacy_pid = None
                break
        return (
            legacy_timestamp,
            legacy_pid,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    def _pid_is_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return True
        return True

    def _parse_lock_timestamp(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            if value.endswith("Z"):
                try:
                    iso_value = f"{value[:-1]}+00:00"
                    return datetime.fromisoformat(iso_value)
                except ValueError:
                    return None
            return None

    def _stale_lock_age_threshold(self) -> float:
        interval = self._interval_seconds or self._LOCK_STALE_MIN_SECONDS
        base = max(interval, self._LOCK_STALE_MIN_SECONDS)
        return base * self._LOCK_STALE_AGE_MULTIPLIER

    def _format_last_run_timestamp(self) -> str | None:
        if self._last_run_finish_time is None:
            return None
        return datetime.fromtimestamp(self._last_run_finish_time, UTC).isoformat()

    def _remove_stale_lock(self, evaluation: LockEvaluation) -> bool:
        try:
            if self._lock_path.exists():
                self._lock_path.unlink()
        except OSError:
            return False
        snapshot = evaluation.snapshot
        metadata: dict[str, object | None] = {
            "lock_file": str(self._lock_path),
            "lock_age_seconds": evaluation.lock_age_seconds,
            "lock_pid": snapshot.pid if snapshot else None,
            "pid_alive": evaluation.pid_alive,
            "lock_timestamp": snapshot.timestamp_value if snapshot else None,
            "expected_interval_seconds": self._interval_seconds,
            "cleanup_reason": evaluation.cleanup_reason or evaluation.stale_decision,
            "event": "lock-stale",
            "identity_match": evaluation.identity_match,
            "current_identity_signature": evaluation.current_identity.signature if evaluation.current_identity else None,
            "scheduler_instance_id": snapshot.scheduler_instance_id if snapshot else None,
            "attempted_run_id": snapshot.attempted_run_id if snapshot else None,
            "scheduler_pid": snapshot.scheduler_pid if snapshot else None,
            "child_pid": snapshot.child_pid if snapshot else None,
            "child_start_time": snapshot.child_start_time if snapshot else None,
            "run_label": snapshot.run_label if snapshot else None,
            "provenance_match": evaluation.provenance_match,
        }
        last_run_ts = self._format_last_run_timestamp()
        if last_run_ts is not None:
            metadata["last_successful_run_timestamp"] = last_run_ts
        if snapshot and snapshot.identity:
            metadata["lock_identity_signature"] = snapshot.identity.signature
            metadata["lock_identity_start_time"] = snapshot.identity.start_time
            metadata["lock_identity_hostname"] = snapshot.identity.hostname
        self._log_event(
            "WARNING",
            "Removed stale lock file",
            **metadata,
        )
        return True

    def _log_lock_held(self, evaluation: LockEvaluation) -> None:
        self._lock_skip_streak += 1
        escalated = self._lock_skip_streak >= self._lock_skip_escalation_threshold
        severity = "ERROR" if escalated else "WARNING"
        snapshot = evaluation.snapshot
        metadata: dict[str, object | None] = {
            "reason": "lock-held",
            "lock_file": str(self._lock_path),
            "event": "lock-skip",
            "lock_age_seconds": evaluation.lock_age_seconds,
            "lock_pid": snapshot.pid if snapshot else None,
            "pid_alive": evaluation.pid_alive,
            "lock_timestamp": snapshot.timestamp_value if snapshot else None,
            "expected_interval_seconds": self._interval_seconds,
            "stale_decision": evaluation.stale_decision,
            "repeated_lock_skips": self._lock_skip_streak,
            "identity_match": evaluation.identity_match,
            "current_identity_signature": evaluation.current_identity.signature if evaluation.current_identity else None,
            "scheduler_instance_id": snapshot.scheduler_instance_id if snapshot else None,
            "attempted_run_id": snapshot.attempted_run_id if snapshot else None,
            "scheduler_pid": snapshot.scheduler_pid if snapshot else None,
            "child_pid": snapshot.child_pid if snapshot else None,
            "child_start_time": snapshot.child_start_time if snapshot else None,
            "run_label": snapshot.run_label if snapshot else None,
            "provenance_match": evaluation.provenance_match,
        }
        last_run_ts = self._format_last_run_timestamp()
        if last_run_ts is not None:
            metadata["last_successful_run_timestamp"] = last_run_ts
        if evaluation.identity_match is False:
            metadata["identity_mismatch"] = True
        if snapshot and snapshot.identity:
            metadata["lock_identity_signature"] = snapshot.identity.signature
            metadata["lock_identity_start_time"] = snapshot.identity.start_time
            metadata["lock_identity_hostname"] = snapshot.identity.hostname
        if escalated:
            metadata["lock_skip_escalated"] = True
            metadata["severity_reason"] = "repeated-lock-held"
        self._log_event(
            severity,
            "Health run skipped because lock is held",
            **metadata,
        )

    def _log_run_summary(
        self,
        assessments: list[HealthAssessmentArtifact],
        triggers: list[ComparisonTriggerArtifact],
        drilldowns: list[DrilldownArtifact],
        external_analysis: list[ExternalAnalysisArtifact],
        settings: ExternalAnalysisSettings,
        freshness_age_seconds: float | None = None,
        expected_interval_seconds: int | None = None,
    ) -> None:
        run_id = self._resolve_run_id(assessments, triggers)
        healthy_count = sum(
            1 for artifact in assessments if artifact.health_rating == HealthRating.HEALTHY
        )
        degraded_count = len(assessments) - healthy_count
        review_config = _serialize_review_enrichment_policy(settings.review_enrichment)
        provider_execution = _build_provider_execution(
            settings,
            external_analysis,
            drilldowns,
            review_config,
        )
        metadata: dict[str, object] = {
            "run_id": run_id,
            "assessment_count": len(assessments),
            "healthy_count": healthy_count,
            "degraded_count": degraded_count,
            "trigger_count": len(triggers),
            "drilldown_count": len(drilldowns),
            "external_analysis_count": len(external_analysis),
            "provider_execution": provider_execution,
            "event": "run-summary",
        }
        if expected_interval_seconds is not None:
            metadata["expected_interval_seconds"] = expected_interval_seconds
            if freshness_age_seconds is not None:
                age_value = int(max(0.0, freshness_age_seconds))
                metadata["freshness_age_seconds"] = age_value
                status = freshness_status(age_value, expected_interval_seconds)
                if status:
                    metadata["freshness_status"] = status
        self._log_event(
            "INFO",
            "Health run summary",
            **metadata,
        )

    def _maybe_build_diagnostic_pack(self, run_id: str) -> None:
        env_value = os.environ.get("HEALTH_BUILD_DIAGNOSTIC_PACK")
        if not _env_is_truthy(env_value):
            return
        if not run_id or run_id == "<unknown>":
            self._log_event(
                "INFO",
                "Skipping diagnostic pack generation; run_id unavailable",
                run_id=run_id,
                event="diag-pack-skipped",
            )
            return
        runs_dir = str(self._runs_dir_base)
        build_script = _SCRIPTS_DIR / "build_diagnostic_pack.py"
        build_cmd = [
            sys.executable,
            str(build_script),
            "--run-id",
            run_id,
            "--runs-dir",
            runs_dir,
        ]
        try:
            subprocess.run(build_cmd, check=True, env=os.environ)
        except (subprocess.CalledProcessError, OSError) as exc:
            self._log_event(
                "ERROR",
                "Scheduled diagnostic pack build failed",
                run_id=run_id,
                severity_reason=str(exc),
                event="diag-pack-build-failed",
            )
            return
        update_script = _SCRIPTS_DIR / "update_ui_index.py"
        update_cmd = [
            sys.executable,
            str(update_script),
            "--run-id",
            run_id,
            "--runs-dir",
            runs_dir,
        ]
        try:
            subprocess.run(update_cmd, check=True, env=os.environ)
        except (subprocess.CalledProcessError, OSError) as exc:
            self._log_event(
                "ERROR",
                "Scheduled UI index refresh failed after diagnostic pack build",
                run_id=run_id,
                severity_reason=str(exc),
                event="diag-pack-ui-refresh-failed",
            )
            return
        self._log_event(
            "INFO",
            "Scheduled diagnostic pack generated",
            run_id=run_id,
            runs_dir=runs_dir,
            event="diag-pack-generated",
        )


def schedule_health_loop(
    config_path: Path,
    manual_triggers: Sequence[str] | None = None,
    manual_drilldown_contexts: Sequence[str] | None = None,
    manual_external_analysis: Sequence[str] | None = None,
    quiet: bool = False,
    *,
    interval_seconds: int | None = None,
    max_runs: int | None = None,
    run_once: bool = False,
) -> int:
    try:
        config = HealthRunConfig.load(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        emit_structured_log(
            component="health-scheduler",
            severity="ERROR",
            message=f"Unable to load health config {config_path}: {exc}",
            run_label=_safe_label(str(config_path.stem)),
            metadata={"config_path": str(config_path), "severity_reason": str(exc), "event": "config-load-failed"},
        )
        return 1
    scheduler = HealthLoopScheduler(
        config_path=config_path,
        manual_triggers=manual_triggers or [],
        manual_drilldown_contexts=manual_drilldown_contexts or [],
        manual_external_analysis=manual_external_analysis or [],
        quiet=quiet,
        interval_seconds=interval_seconds,
        max_runs=max_runs,
        run_once=run_once,
        output_dir=config.output_dir,
        run_label=config.run_label,
    )
    return scheduler.run()
