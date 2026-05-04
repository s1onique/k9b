"""Per-cluster health assessment loop with trigger-aware comparisons."""
from __future__ import annotations

import json
import subprocess
import time
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast
from uuid import uuid4  # noqa: F401 - re-exported for backward compatibility

from ..collect.cluster_snapshot import ClusterSnapshot, WarningEventSummary
from ..collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from ..compare.two_cluster import ClusterComparison, compare_snapshots
from ..datetime_utils import parse_iso_to_utc
from ..external_analysis.adapter import ExternalAnalysisRequest, build_external_analysis_adapters
from ..external_analysis.alertmanager_discovery import AlertmanagerSourceInventory
from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose, ExternalAnalysisStatus, write_external_analysis_artifact
from ..external_analysis.config import ExternalAnalysisSettings, parse_external_analysis_settings
from ..external_analysis.next_check_planner import plan_next_checks
from ..external_analysis.review_schema import classify_review_enrichment_shape
from ..identity.artifact import new_artifact_id
from ..llm.call_labels import build_llm_call_id
from ..llm.llamacpp_provider import classify_llm_failure
from ..models import Assessment, ConfidenceLevel, Finding, Hypothesis, Layer, NextCheck, RecommendedAction, SafetyLevel, Signal
from ..render.formatter import assessment_to_dict
from ..security.subprocess_helpers import _log_subprocess_failure
from ..structured_logging import DEFAULT_HEALTH_LOG, emit_structured_log
from . import loop_history
from .adaptation import HealthProposal
from .baseline import BaselineDriftCategory, BaselinePolicy, resolve_baseline_policy_path
from .drilldown import DrilldownArtifact, DrilldownCollector
from .drilldown_assessor import assess_drilldown_artifact
from .image_pull_secret import ImagePullSecretInsight, ImagePullSecretInspector
from .loop_alertmanager_discovery import run_alertmanager_discovery as _run_alertmanager_discovery_impl
from .loop_alertmanager_snapshot import run_alertmanager_snapshot_collection as _run_alertmanager_snapshot_collection_impl
from .loop_baseline_helpers import _load_baseline_policy_from_path, _normalize_category_list, _parse_cohort_baselines, _policy_for_target, _resolve_target_baseline_path
from .loop_config_helpers import _parse_comparison_intent, _parse_manual_external_analysis_requests, _parse_manual_triggers, _parse_threshold
from .loop_drilldown_helpers import determine_drilldown_reasons as _determine_drilldown_reasons_impl
from .loop_history import HealthHistoryEntry, HealthRating, _build_runtime_run_id, _format_snapshot_filename, _safe_label, _serialize_value, _str_or_none, _watched_crd_versions, _watched_release_versions, _write_json, persist_history_fact_artifacts
from .loop_port_forward_helpers import _choose_free_local_port, _wait_for_port_ready
from .loop_review_pipeline import write_review_and_proposals as _write_review_and_proposals_impl
from .loop_run_config_helpers import _resolve_collector_version, _resolve_output_dir
from .loop_scheduler import (
    _HEALTH_ONLY_MESSAGE,  # noqa: F401
    HealthLoopScheduler,  # noqa: F401 - re-exported for backward compatibility
    LockEvaluation,  # noqa: F401 - re-exported for backward compatibility
    LockFileSnapshot,  # noqa: F401 - re-exported for backward compatibility
    ProcessIdentity,  # noqa: F401 - re-exported for backward compatibility
)
from .notifications import NotificationArtifact, build_degraded_health_notification, build_external_analysis_notification, build_suspicious_comparison_notification, write_notification_artifact
from .ui import write_health_ui_index
from .utils import normalize_ref
from .validators import ComparisonDecisionValidator, DrilldownArtifactValidator, HealthAssessmentValidator


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


def _resolve_peer_role(
    record: HealthSnapshotRecord,
    registry: BaselineRegistry | None,
) -> str | None:
    """Resolve the peer role for a health snapshot record.

    Priority:
    1. Explicit cluster_role from the target metadata
    2. Registry lookup using record references (context or label)
    """
    explicit_role = record.target.cluster_role
    if explicit_role:
        return explicit_role.strip() or None
    if registry:
        for reference in record.refs():
            role = registry.role_for(reference)
            if role:
                return role
    return None


def _validate_suspicious_pairs(
    peers: Sequence[ComparisonPeer],
    target_lookup: dict[str, HealthTarget],
    baseline: BaselinePolicy,
) -> None:
    """Validate that all suspicious-drift peer mappings are within the same class/cohort."""
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
    """Determine if a pair of health snapshot records is eligible for comparison.

    Returns:
        Tuple of (eligible, reason, primary_class, secondary_class, primary_role,
                 secondary_role, primary_cohort, secondary_cohort)
    """
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


_HISTORY_FILENAME = loop_history._HISTORY_FILENAME
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"


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
    artifact_id: str | None = None  # None for legacy artifacts, auto-generated for new artifacts

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
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
        # Include artifact_id when present (backward compat: legacy artifacts without it)
        if self.artifact_id is not None:
            data["artifact_id"] = self.artifact_id
        return data

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ComparisonTriggerArtifact:
        """Parse a trigger artifact from a dict, with backward compatibility for legacy artifacts."""
        # Parse artifact_id for backward compatibility (legacy artifacts without it)
        artifact_id_value = raw.get("artifact_id")
        parsed_artifact_id: str | None = None
        if artifact_id_value is not None and isinstance(artifact_id_value, str) and artifact_id_value:
            parsed_artifact_id = artifact_id_value

        # Parse timestamp
        timestamp_value = raw.get("timestamp")
        parsed_timestamp: datetime
        if isinstance(timestamp_value, str):
            parsed_timestamp = parse_iso_to_utc(timestamp_value) or datetime.now(UTC)
        else:
            parsed_timestamp = datetime.now(UTC)

        # Parse trigger details
        trigger_details_raw = raw.get("trigger_details") or []
        parsed_trigger_details: list[TriggerDetail] = []
        if isinstance(trigger_details_raw, list):
            for detail_raw in trigger_details_raw:
                if isinstance(detail_raw, Mapping):
                    parsed_trigger_details.append(TriggerDetail(
                        type=str(detail_raw.get("type", "")),
                        reason=str(detail_raw.get("reason", "")),
                        baseline_expectation=str(detail_raw.get("baseline_expectation")) if detail_raw.get("baseline_expectation") else None,
                        actual_value=str(detail_raw.get("actual_value", "")),
                        previous_run_value=str(detail_raw.get("previous_run_value")) if detail_raw.get("previous_run_value") else None,
                        why=str(detail_raw.get("why", "")),
                        next_check=str(detail_raw.get("next_check")) if detail_raw.get("next_check") else None,
                        peer_roles=str(detail_raw.get("peer_roles")) if detail_raw.get("peer_roles") else None,
                        classification=str(detail_raw.get("classification")) if detail_raw.get("classification") else None,
                    ))

        # Parse trigger_reasons
        trigger_reasons_raw = raw.get("trigger_reasons") or []
        parsed_trigger_reasons: tuple[str, ...]
        if isinstance(trigger_reasons_raw, list):
            parsed_trigger_reasons = tuple(str(item) for item in trigger_reasons_raw)
        else:
            parsed_trigger_reasons = ()

        # Parse categories
        def _parse_tuple(value: Any) -> tuple[str, ...]:
            if isinstance(value, list):
                return tuple(str(item) for item in value)
            return ()

        return cls(
            run_label=str(raw.get("run_label", "")),
            run_id=str(raw.get("run_id", "")),
            timestamp=parsed_timestamp,
            primary=str(raw.get("primary", "")),
            secondary=str(raw.get("secondary", "")),
            primary_label=str(raw.get("primary_label", "")),
            secondary_label=str(raw.get("secondary_label", "")),
            trigger_reasons=parsed_trigger_reasons,
            comparison_summary=dict(raw.get("comparison_summary") or {}),
            differences=dict(raw.get("differences") or {}),
            trigger_details=tuple(parsed_trigger_details),
            comparison_intent=str(raw.get("comparison_intent", "")),
            expected_drift_categories=_parse_tuple(raw.get("expected_drift_categories")),
            ignored_drift_categories=_parse_tuple(raw.get("ignored_drift_categories")),
            peer_notes=str(raw.get("peer_notes")) if raw.get("peer_notes") else None,
            notes=str(raw.get("notes")) if raw.get("notes") else None,
            artifact_id=parsed_artifact_id,
        )


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
        output_dir = _resolve_output_dir(raw.get("output_dir"))
        collector_version = _resolve_collector_version(raw.get("collector_version"))

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
        # Storage for verified Alertmanager inventory (populated by _run_alertmanager_discovery)
        self._alertmanager_inventory: AlertmanagerSourceInventory | None = None

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

    @staticmethod
    def _failure_metadata_field(metadata: dict[str, object] | None, key: str) -> Any:
        """Extract a field from failure metadata, checking top-level and nested prompt_diagnostics.

        This helper enables result logs to extract failure details from either:
        1. metadata[key] - top-level failure class or exception type
        2. metadata["prompt_diagnostics"][key] - nested in prompt diagnostics

        Args:
            metadata: The failure_metadata dict from ExternalAnalysisArtifact
            key: The field name to extract (e.g., "failure_class", "exception_type")

        Returns:
            The field value (str for text fields, bool for boolean fields), or None if not found
        """
        if not metadata:
            return None
        value = metadata.get(key)
        if value is not None:
            # Preserve boolean values as-is; convert other truthy values to string
            if isinstance(value, bool):
                return value
            return str(value)
        prompt_diags = metadata.get("prompt_diagnostics")
        if isinstance(prompt_diags, dict):
            value = prompt_diags.get(key)
            if value is not None:
                if isinstance(value, bool):
                    return value
                return str(value)
        return None

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
        # Collect Alertmanager snapshots from tracked sources
        self._run_alertmanager_snapshot_collection(directories)
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
        self._persist_history(history, directories)
        review_path, proposals = self._write_review_artifact(assessments, drilldowns, directories)
        enrichment_artifact = self._run_review_enrichment(review_path, directories)
        if enrichment_artifact:
            external_artifacts.append(enrichment_artifact)
        # Filter to execution artifacts for run-scoped feedback
        execution_artifacts = tuple(
            a for a in external_artifacts
            if a.purpose == ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION
        )
        plan_artifact = self._run_next_check_planning(
            review_path, enrichment_artifact, directories, execution_artifacts
        )
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
            "history_facts": root / "history",
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
                artifact_id=new_artifact_id(),
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
            failure_metadata: dict[str, object] | None = None
            # Build actual prompt first for exact measurement.
            # Note: assess_drilldown_artifact() also builds the prompt internally.
            # Since build_drilldown_prompt() is deterministic, the measured chars
            # should match the actual prompt sent to the LLM.
            from ..llm.drilldown_prompts import build_drilldown_prompt
            actual_prompt = build_drilldown_prompt(drilldown)
            actual_prompt_chars = len(actual_prompt) if actual_prompt else 0
            # Build deterministic call ID for start log
            start_call_id = build_llm_call_id(self.run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label)
            # Resolve max_tokens for llama.cpp provider
            start_max_tokens: int | None = None
            if provider_name == "llamacpp":
                from .drilldown_assessor import resolve_drilldown_max_tokens
                start_max_tokens = resolve_drilldown_max_tokens(provider_name)
            # Log LLM call start
            self._log_event(
                "llm-call",
                "INFO",
                "LLM call started",
                llm_call=True,
                llm_call_id=start_call_id,
                llm_provider=provider_name,
                llm_operation="auto-drilldown",
                llm_phase="start",
                run_id=self.run_id,
                run_label=self.run_label,
                cluster_label=drilldown.label,
                max_tokens=start_max_tokens,
                timeout_seconds=None,
                actual_prompt_chars=actual_prompt_chars,
            )
            try:
                # max_tokens will be resolved by assess_drilldown_artifact using provider config
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
                # LLMResponseParseError is a ValueError subclass: handle it with structured failure metadata
                from ..llm.llamacpp_provider import LLMResponseParseError
                from .drilldown_assessor import build_drilldown_prompt_diagnostics
                if isinstance(exc, LLMResponseParseError):
                    status = ExternalAnalysisStatus.FAILED
                    summary = str(exc)
                    error_summary = str(exc)
                    payload = None
                    skip_reason = None
                    elapsed_ms = int((time.perf_counter() - start) * 1000)
                    # Determine failure class based on length cap
                    if exc.completion_stopped_by_length is True:
                        failure_class_value = "llm_response_parse_error_length_capped"
                    else:
                        failure_class_value = "llm_response_parse_error"
                    # Build structured top-level failure metadata
                    exc_diags = exc.to_diagnostics()
                    max_toks: int | None = None
                    if provider_name == "llamacpp":
                        from .drilldown_assessor import resolve_drilldown_max_tokens
                        max_toks = resolve_drilldown_max_tokens(provider_name)
                    prompt_diags = build_drilldown_prompt_diagnostics(
                        drilldown,
                        provider_name=provider_name,
                        actual_prompt_chars=actual_prompt_chars,
                        max_tokens=max_toks,
                        elapsed_ms=elapsed_ms,
                        failure_class=failure_class_value,
                        exception_type="LLMResponseParseError",
                    )
                    llm_call_id_val = build_llm_call_id(
                        self.run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label
                    )
                    failure_metadata = {
                        "failure_class": failure_class_value,
                        "exception_type": "LLMResponseParseError",
                        "finish_reason": exc_diags.get("finish_reason"),
                        "completion_stopped_by_length": exc_diags.get("completion_stopped_by_length"),
                        "response_content_chars": exc_diags.get("response_content_chars"),
                        "response_content_prefix": exc_diags.get("response_content_prefix"),
                        "max_tokens": exc_diags.get("max_tokens"),
                        "provider": provider_name,
                        "operation": "auto-drilldown",
                        "llm_call_id": llm_call_id_val,
                        "llm_call": True,
                        "prompt_diagnostics": prompt_diags,
                    }
                    self._log_event(
                        "llm-prompt-diagnostics",
                        "ERROR",
                        "Auto-drilldown LLM call failed",
                        llm_call=True,
                        llm_call_id=llm_call_id_val,
                        llm_provider=provider_name,
                        llm_operation="auto-drilldown",
                        llm_phase="diagnostics",
                        operation=prompt_diags.get("operation"),
                        provider=prompt_diags.get("provider"),
                        prompt_chars=prompt_diags.get("prompt_chars"),
                        prompt_tokens_estimate=prompt_diags.get("prompt_tokens_estimate"),
                        actual_prompt_chars=prompt_diags.get("actual_prompt_chars"),
                        actual_prompt_tokens_estimate=prompt_diags.get("actual_prompt_tokens_estimate"),
                        section_coverage_ratio=prompt_diags.get("section_coverage_ratio"),
                        prompt_section_count=prompt_diags.get("prompt_section_count"),
                        top_prompt_sections=[
                            s.get("name") for s in prompt_diags.get("top_prompt_sections", [])
                        ],
                        elapsed_ms=elapsed_ms,
                        failure_class=failure_class_value,
                        exception_type="LLMResponseParseError",
                    )
                else:
                    # Non-LLM ValueError (including schema validation): preserve SKIPPED behavior
                    # but set explicit failure metadata for observability
                    status = ExternalAnalysisStatus.SKIPPED
                    summary = str(exc)
                    skip_reason = str(exc)
                    error_summary = None
                    payload = None
                    failure_metadata = {
                        "failure_class": "llm_response_schema_validation_error",
                        "exception_type": "ValueError",
                        "provider": provider_name,
                        "operation": "auto-drilldown",
                        "llm_call_id": build_llm_call_id(
                            self.run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label
                        ),
                        "llm_call": True,
                        "max_tokens": start_max_tokens,
                        "actual_prompt_chars": actual_prompt_chars,
                    }
            except Exception as exc:
                status = ExternalAnalysisStatus.FAILED
                summary = str(exc)
                error_summary = str(exc)
                payload = None
                # Build prompt diagnostics for failure logging and artifact
                failure_metadata = None
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                from .drilldown_assessor import build_drilldown_prompt_diagnostics
                try:
                    # Classify the exception properly - check __cause__ and __context__ for wrapped exceptions
                    classified_failure_class, classified_exc_type = classify_llm_failure(exc)
                    # Resolve max_tokens for diagnostics using the drilldown_assessor helper
                    diagnostic_max_tokens: int | None = None
                    if provider_name == "llamacpp":
                        from .drilldown_assessor import resolve_drilldown_max_tokens
                        diagnostic_max_tokens = resolve_drilldown_max_tokens(provider_name)
                    prompt_diags = build_drilldown_prompt_diagnostics(
                        drilldown,
                        provider_name=provider_name,
                        actual_prompt_chars=actual_prompt_chars,
                        max_tokens=diagnostic_max_tokens,
                        elapsed_ms=elapsed_ms,
                        failure_class=classified_failure_class.value,
                        exception_type=classified_exc_type,
                    )
                    # Build deterministic call ID for correlation across logs and artifacts
                    call_id = build_llm_call_id(self.run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label)
                    # Log structured diagnostics for failure observability
                    self._log_event(
                        "llm-prompt-diagnostics",
                        "ERROR",
                        "Auto-drilldown LLM call failed",
                        llm_call=True,
                        llm_call_id=call_id,
                        llm_provider=provider_name,
                        llm_operation="auto-drilldown",
                        llm_phase="diagnostics",
                        operation=prompt_diags.get("operation"),
                        provider=prompt_diags.get("provider"),
                        prompt_chars=prompt_diags.get("prompt_chars"),
                        prompt_tokens_estimate=prompt_diags.get("prompt_tokens_estimate"),
                        actual_prompt_chars=prompt_diags.get("actual_prompt_chars"),
                        actual_prompt_tokens_estimate=prompt_diags.get("actual_prompt_tokens_estimate"),
                        section_coverage_ratio=prompt_diags.get("section_coverage_ratio"),
                        prompt_section_count=prompt_diags.get("prompt_section_count"),
                        top_prompt_sections=[
                            s.get("name") for s in prompt_diags.get("top_prompt_sections", [])
                        ],
                        elapsed_ms=elapsed_ms,
                        failure_class=classified_failure_class.value,
                        exception_type=classified_exc_type,
                    )
                    failure_metadata = {"prompt_diagnostics": prompt_diags}
                except Exception:  # noqa: BLE001
                    # If diagnostics extraction fails, log with fallback
                    failure_metadata = None
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
                failure_metadata=failure_metadata,
            )
            write_external_analysis_artifact(artifact_path, artifact)
            severity = (
                "INFO"
                if status == ExternalAnalysisStatus.SUCCESS
                else "WARNING"
                if status == ExternalAnalysisStatus.SKIPPED
                else "ERROR"
            )
            # Build status-appropriate log message
            _interp_label = (
                "Auto drilldown interpretation failed"
                if status == ExternalAnalysisStatus.FAILED
                else "Auto drilldown interpretation skipped"
                if status == ExternalAnalysisStatus.SKIPPED
                else "Auto drilldown interpretation recorded"
            )
            self._log_event(
                "external-analysis",
                severity,
                _interp_label,
                tool=provider_name,
                cluster_label=drilldown.label,
                status=status.value,
                artifact_path=str(artifact_path),
                error_summary=error_summary,
                duration_ms=duration_ms,
                event="auto-drilldown",
            )
            # Log LLM call result with deterministic call ID for correlation
            result_call_id = build_llm_call_id(self.run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label)
            # Extract failure details from failure_metadata if available (check top-level and nested prompt_diagnostics)
            result_failure_class: str | None = HealthLoopRunner._failure_metadata_field(failure_metadata, "failure_class")
            result_exception_type: str | None = HealthLoopRunner._failure_metadata_field(failure_metadata, "exception_type")
            result_skip_reason: str | None = None
            if failure_metadata:
                nested_diags = failure_metadata.get("prompt_diagnostics")
                if isinstance(nested_diags, dict):
                    result_skip_reason = str(nested_diags.get("skip_reason")) if nested_diags.get("skip_reason") else None
            if status == ExternalAnalysisStatus.SKIPPED and skip_reason:
                result_skip_reason = skip_reason
            # Resolve max_tokens for llama.cpp provider
            result_max_tokens: int | None = None
            if provider_name == "llamacpp":
                from .drilldown_assessor import resolve_drilldown_max_tokens
                result_max_tokens = resolve_drilldown_max_tokens(provider_name)
            self._log_event(
                "llm-call",
                severity,
                "LLM call completed" if status == ExternalAnalysisStatus.SUCCESS else ("LLM call skipped" if status == ExternalAnalysisStatus.SKIPPED else "LLM call failed"),
                llm_call=True,
                llm_call_id=result_call_id,
                llm_provider=provider_name,
                llm_operation="auto-drilldown",
                llm_phase="result",
                run_id=self.run_id,
                run_label=self.run_label,
                cluster_label=drilldown.label,
                status=status.value,
                duration_ms=duration_ms,
                artifact_path=str(artifact_path),
                max_tokens=result_max_tokens,
                failure_class=result_failure_class,
                exception_type=result_exception_type,
                finish_reason=HealthLoopRunner._failure_metadata_field(failure_metadata, "finish_reason"),
                completion_stopped_by_length=HealthLoopRunner._failure_metadata_field(
                    failure_metadata,
                    "completion_stopped_by_length",
                ),
                skip_reason=result_skip_reason,
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
        # If the artifact was skipped due to invalid JSON/parse error, use invalid-json classification
        # instead of unrecognized-payload to avoid misleading diagnostics
        if artifact.status == ExternalAnalysisStatus.SKIPPED and artifact.failure_metadata:
            failure_meta = cast(dict[str, Any], artifact.failure_metadata)
            failure_class = str(failure_meta.get("failure_class", ""))
            exception_type = str(failure_meta.get("exception_type", ""))
            if "llm_response_parse_error" in failure_class or "LLMResponseParseError" in exception_type:
                # Create an INVALID_JSON classification with structured output diagnostics
                from ..external_analysis.review_schema import ReviewEnrichmentShapeAnalysis, ReviewEnrichmentShapeClassification
                shape_analysis = ReviewEnrichmentShapeAnalysis(
                    classification=ReviewEnrichmentShapeClassification.INVALID_JSON,
                    reason="LLM response parse error - invalid JSON or length capped",
                    raw_payload_keys=(),
                    summary_present=False,
                    triage_order_count=0,
                    top_concerns_count=0,
                    evidence_gaps_count=0,
                    next_checks_count=0,
                    focus_notes_count=0,
                )
            else:
                shape_analysis = classify_review_enrichment_shape(enrichment_payload)
        else:
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
            raw_payload_keys=list(shape_analysis.raw_payload_keys)[:10],
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

        # Additional failure metadata for failed status
        log_kwargs: dict[str, Any] = {
            "run_label": self.run_label,
            "run_id": self.run_id,
            "provider": provider or "unspecified",
            "artifact_path": str(artifact_path),
            "status": artifact.status.value,
            "next_checks_count": next_checks_count,
            "error_summary": error_summary,
            "skip_reason": skip_reason,
            "event": "review-enrichment-result",
        }
        # Include failure metadata for FAILED status if available
        if artifact.status == ExternalAnalysisStatus.FAILED and artifact.duration_ms is not None:
            log_kwargs["elapsed_ms"] = artifact.duration_ms
        self._log_event(
            "review-enrichment",
            severity,
            message,
            **log_kwargs,
        )
        return artifact

    def _run_next_check_planning(
        self,
        review_path: Path | None,
        enrichment_artifact: ExternalAnalysisArtifact | None,
        directories: dict[str, Path],
        execution_artifacts: tuple[ExternalAnalysisArtifact, ...] | None = None,
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
        plan = plan_next_checks(review_path, self.run_id, enrichment_artifact, execution_artifacts)
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
        """Build health review and generate proposals from assessments and drilldowns.

        Delegates to loop_review_pipeline module for the core pipeline logic.
        Notifications for proposals are created inside the extracted module.
        """
        try:
            review_path, proposals = _write_review_and_proposals_impl(
                run_id=self.run_id,
                run_label=self.run_label,
                assessments=assessments,
                drilldowns=drilldowns,
                directories=directories,
                warning_threshold=self.config.trigger_policy.warning_event_threshold,
                baseline_policy=self.config.baseline_policy,
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

        if review_path is None:
            return None, ()

        self._log_event(
            "review-assessment",
            "INFO",
            "Health review written",
            artifact_path=str(review_path),
            assessment_count=len(assessments),
            drilldown_count=len(drilldowns),
            event="review-created",
        )

        if proposals:
            for proposal in proposals:
                self._log_event(
                    "proposal-promotion",
                    "INFO",
                    "Health proposal written",
                    proposal_id=proposal.proposal_id,
                    artifact_path=proposal.artifact_path,
                    event="proposal-generated",
                )

        return review_path, proposals

    def _determine_drilldown_reasons(
        self,
        record: HealthSnapshotRecord,
        previous_history: dict[str, HealthHistoryEntry],
    ) -> tuple[str, ...]:
        """Determine drilldown reasons for a cluster record.

        Delegates to the extracted drilldown helpers module for the core logic.
        """
        return _determine_drilldown_reasons_impl(
            record=record,
            previous_history=previous_history,
            manual_drilldown_contexts=self._manual_drilldown_contexts,
            warning_event_threshold=self.config.trigger_policy.warning_event_threshold,
        )

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
                artifact_id=new_artifact_id(),
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

    def _persist_history(self, history: dict[str, HealthHistoryEntry], directories: dict[str, Path]) -> None:
        # First, write immutable fact artifacts for each cluster
        history_facts_dir = directories.get("history_facts")
        if history_facts_dir:
            try:
                persist_history_fact_artifacts(
                    history=history,
                    run_id=self.run_id,
                    history_dir=history_facts_dir,
                    artifact_id_fn=new_artifact_id,
                )
                self._log_event(
                    "health-loop",
                    "INFO",
                    "History fact artifacts written",
                    artifact_count=len(history),
                    history_facts_dir=str(history_facts_dir),
                    event="history-facts-written",
                )
            except Exception as exc:
                # Fact artifact write failure is non-fatal; log and continue
                self._log_event(
                    "health-loop",
                    "WARNING",
                    "Failed to write history fact artifacts",
                    severity_reason=str(exc),
                    event="history-facts-failed",
                )

        # Then, write the mutable aggregate history.json (backward compatibility)
        history_path = directories["history"]
        data = {cluster_id: entry.to_dict() for cluster_id, entry in history.items()}
        _write_json(data, history_path)

    def _run_alertmanager_discovery(
        self,
        records: list[HealthSnapshotRecord],
        directories: dict[str, Path],
    ) -> None:
        """Run Alertmanager discovery for each cluster target and persist the inventory.
        
        Delegates to loop_alertmanager_discovery module for the actual discovery logic.
        Stores the verified inventory in self._alertmanager_inventory for downstream
        snapshot collection.
        """
        def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
            self._log_event(component, severity, message, **metadata)
        
        self._alertmanager_inventory = _run_alertmanager_discovery_impl(
            records=records,
            directories=directories,
            log_event=log_callback,
            run_id=self.run_id,
        )

    def _run_alertmanager_snapshot_collection(
        self,
        directories: dict[str, Path],
    ) -> None:
        """Collect Alertmanager snapshot and compact artifacts for tracked sources.

        Delegates to loop_alertmanager_snapshot module for the actual collection logic.
        Uses port-forward helpers from this runner for cluster-internal endpoints.

        This is non-fatal: fetch failures are logged but do not stop the run.
        """
        def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
            self._log_event(component, severity, message, **metadata)

        _run_alertmanager_snapshot_collection_impl(
            inventory=self._alertmanager_inventory,
            run_id=self.run_id,
            run_label=self.run_label,
            log_event=log_callback,
            directories=directories,
            start_port_forward=self._start_alertmanager_port_forward,
            stop_port_forward=self._stop_alertmanager_port_forward,
        )

    def _choose_free_local_port(self) -> int:
        """Choose a free local TCP port for port-forward.
        
        Delegates to the extracted port-forward helpers module.
        """
        return _choose_free_local_port()

    def _wait_for_port_ready(
        self,
        host: str,
        port: int,
        timeout_seconds: float = 5.0,
        poll_interval: float = 0.1,
    ) -> bool:
        """Wait for a TCP port to become accepting connections.
        
        Delegates to the extracted port-forward helpers module.
        """
        return _wait_for_port_ready(host, port, timeout_seconds, poll_interval)

    def _start_alertmanager_port_forward(
        self,
        namespace: str,
        service_name: str,
        context: str | None,
    ) -> tuple[subprocess.Popen[str], int]:
        """Start kubectl port-forward to an Alertmanager service.
        
        Chooses a free local port and waits for it to become ready before returning.
        
        Returns:
            Tuple of (subprocess handle, local port number)
            
        Raises:
            RuntimeError: If port-forward cannot be started or the port
                        does not become ready within the timeout.
        """
        # Choose a free local port before starting kubectl
        local_port = self._choose_free_local_port()
        
        # Build the kubectl command with the chosen port
        cmd = [
            "kubectl", "port-forward",
            "-n", namespace,
            f"svc/{service_name}",
            f"{local_port}:9093",  # Forward to Alertmanager's default port
        ]
        if context:
            cmd.extend(["--context", context])
        
        self._log_event(
            "alertmanager-snapshot",
            "INFO",
            "Starting Alertmanager port-forward",
            event="alertmanager-portforward-start",
            run_id=self.run_id,
            run_label=self.run_label,
            namespace=namespace,
            service_name=service_name,
            cluster_context=context,
            local_port=local_port,
        )
        
        try:
            # Start the port-forward process with text mode for type compatibility
            # Capture stderr for diagnostics (stdout discarded as it's kubectl port-forward noise)
            port_forward_process: subprocess.Popen[str] = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            
            # Wait for the port to become ready (with retries)
            if not self._wait_for_port_ready("127.0.0.1", local_port, timeout_seconds=5.0):
                # Port did not become ready - capture stderr for diagnostics before cleanup
                # Avoid communicate-before-kill hang: kill first if still running, then collect stderr
                stderr_output = ""
                if port_forward_process.poll() is None:
                    port_forward_process.kill()
                    try:
                        _, stderr_output = port_forward_process.communicate(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        port_forward_process.kill()
                        _, stderr_output = port_forward_process.communicate()
                else:
                    try:
                        _, stderr_output = port_forward_process.communicate(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        stderr_output = ""

                # Log subprocess failure with safe metadata
                _log_subprocess_failure(
                    operation="port_forward",
                    command_args=cmd,
                    return_code=port_forward_process.returncode,
                    stderr=stderr_output,
                    run_id=self.run_id,
                    cluster_label=self.run_label,
                )

                self._log_event(
                    "alertmanager-snapshot",
                    "ERROR",
                    "Alertmanager port-forward failed to become ready",
                    event="alertmanager-portforward-failed",
                    run_id=self.run_id,
                    run_label=self.run_label,
                    namespace=namespace,
                    service_name=service_name,
                    local_port=local_port,
                    reason="port-not-ready",
                )
                raise RuntimeError(
                    f"kubectl port-forward for {namespace}/{service_name} "
                    f"did not become ready on port {local_port}"
                )
            
            # Check if process is still running
            if port_forward_process.poll() is not None:
                self._log_event(
                    "alertmanager-snapshot",
                    "ERROR",
                    "Alertmanager port-forward failed to start",
                    event="alertmanager-portforward-failed",
                    run_id=self.run_id,
                    run_label=self.run_label,
                    namespace=namespace,
                    service_name=service_name,
                    exit_code=port_forward_process.returncode,
                    reason="process-exited",
                )
                raise RuntimeError(
                    f"kubectl port-forward exited unexpectedly with code "
                    f"{port_forward_process.returncode}"
                )
            
            self._log_event(
                "alertmanager-snapshot",
                "INFO",
                "Alertmanager port-forward ready",
                event="alertmanager-portforward-ready",
                run_id=self.run_id,
                run_label=self.run_label,
                namespace=namespace,
                service_name=service_name,
                local_port=local_port,
            )
            
            return port_forward_process, local_port
            
        except FileNotFoundError:
            self._log_event(
                "alertmanager-snapshot",
                "ERROR",
                "kubectl not found - cannot establish port-forward",
                event="alertmanager-portforward-failed",
                run_id=self.run_id,
                run_label=self.run_label,
                namespace=namespace,
                service_name=service_name,
                reason="kubectl-not-found",
            )
            raise RuntimeError("kubectl not found in PATH - cannot port-forward to Alertmanager")
        except OSError as exc:
            self._log_event(
                "alertmanager-snapshot",
                "ERROR",
                "Failed to start port-forward subprocess",
                event="alertmanager-portforward-failed",
                run_id=self.run_id,
                run_label=self.run_label,
                namespace=namespace,
                service_name=service_name,
                severity_reason=str(exc),
                reason="subprocess-error",
            )
            raise RuntimeError(f"Failed to start kubectl port-forward: {exc}")

    def _stop_alertmanager_port_forward(
        self,
        process: subprocess.Popen[str],
        local_port: int | None,
    ) -> None:
        """Stop the port-forward process and log the event."""
        try:
            if process.poll() is None:
                # Process is still running, terminate it gracefully
                process.terminate()
                try:
                    # Wait briefly for graceful termination
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't stop gracefully
                    process.kill()
                    process.wait()
            
            self._log_event(
                "alertmanager-snapshot",
                "INFO",
                "Alertmanager port-forward stopped",
                event="alertmanager-portforward-stopped",
                run_id=self.run_id,
                run_label=self.run_label,
                local_port=local_port,
            )
        except Exception as exc:
            self._log_event(
                "alertmanager-snapshot",
                "WARNING",
                "Error during port-forward cleanup",
                event="alertmanager-portforward-stopped",
                run_id=self.run_id,
                run_label=self.run_label,
                local_port=local_port,
                severity_reason=str(exc),
                reason="cleanup-error",
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



