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

from ..collect.cluster_snapshot import ClusterSnapshot
from ..collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from ..compare.two_cluster import ClusterComparison, compare_snapshots
from ..datetime_utils import parse_iso_to_utc
from ..external_analysis.adapter import ExternalAnalysisRequest, build_external_analysis_adapters, normalize_adapter_name
from ..external_analysis.alertmanager_discovery import AlertmanagerSourceInventory
from ..external_analysis.alertmanager_durable_learning import scan_and_propose
from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose, ExternalAnalysisStatus, write_external_analysis_artifact
from ..external_analysis.config import ExternalAnalysisSettings, parse_external_analysis_settings
from ..external_analysis.review_schema import classify_review_enrichment_shape
from ..external_analysis.vmalert_discovery import VmalertSourceInventory
from ..identity.artifact import new_artifact_id
from ..llm.call_labels import build_llm_call_id
from ..llm.llamacpp_provider import classify_llm_failure
from ..llm.provider import LEGACY_LLAMACPP_PROVIDER_NAME, OPENAI_COMPATIBLE_PROVIDER_NAME
from ..models import Assessment, ConfidenceLevel, Finding, Hypothesis, Layer, NextCheck, RecommendedAction, Signal
from ..structured_logging import DEFAULT_HEALTH_LOG, emit_structured_log
from . import loop_history
from .adaptation import HealthProposal
from .baseline import BaselineDriftCategory, BaselinePolicy, resolve_baseline_policy_path
from .drilldown import DrilldownArtifact, DrilldownCollector
from .drilldown_assessor import assess_drilldown_artifact
from .image_pull_secret import ImagePullSecretInsight, ImagePullSecretInspector
from .loop_alertmanager_discovery import run_alertmanager_discovery as _run_alertmanager_discovery_impl
from .loop_alertmanager_port_forward import (
    start_alertmanager_port_forward,
    stop_alertmanager_port_forward,
)
from .loop_alertmanager_snapshot import run_alertmanager_snapshot_collection as _run_alertmanager_snapshot_collection_impl
from .loop_assessment_baseline import assess_baseline_policy
from .loop_assessment_counts import assess_count_issues
from .loop_assessment_history_drift import assess_previous_run_drift
from .loop_assessment_image_pull import assess_image_pull_issues
from .loop_assessment_missing_evidence import assess_missing_evidence
from .loop_assessment_regressions import check_regression_from_history
from .loop_assessment_result import build_health_assessment_result
from .loop_assessment_summary import derive_assessment_summary
from .loop_assessment_warning_events import match_warning_event_patterns
from .loop_baseline_helpers import _load_baseline_policy_from_path, _normalize_category_list, _parse_cohort_baselines, _policy_for_target, _resolve_target_baseline_path
from .loop_comparison_policy import (  # noqa: F401
    BaselineRegistry,  # noqa: F401 - re-exported for backward compatibility
    _policy_eligible_pair,  # noqa: F401 - re-exported for backward compatibility
    _resolve_peer_role,  # noqa: F401 - re-exported for backward compatibility
    _validate_suspicious_pairs,  # noqa: F401 - re-exported for backward compatibility
)
from .loop_config_helpers import _parse_comparison_intent, _parse_manual_external_analysis_requests, _parse_manual_triggers, _parse_threshold
from .loop_drilldown_helpers import determine_drilldown_reasons as _determine_drilldown_reasons_impl
from .loop_failure_metadata import extract_failure_metadata_field
from .loop_history import HealthAssessmentArtifact, HealthAssessmentResult, HealthHistoryEntry, HealthRating, _build_runtime_run_id, _format_snapshot_filename, _safe_label, _serialize_value, _str_or_none, _write_json
from .loop_port_forward_helpers import _choose_free_local_port, _wait_for_port_ready
from .loop_retention import prune_external_analysis_history
from .loop_review_pipeline import write_review_and_proposals as _write_review_and_proposals_impl
from .loop_run_config_helpers import _resolve_collector_version, _resolve_output_dir
from .loop_health_assessment import build_health_assessment as _build_health_assessment_impl
from .loop_runner_assessments import build_assessments_for_records
from .loop_runner_history import load_runner_history, persist_runner_history
from .loop_runner_next_check_planning import run_next_check_planning
from .loop_scheduler import (
    _HEALTH_ONLY_MESSAGE,  # noqa: F401
    HealthLoopScheduler,  # noqa: F401 - re-exported for backward compatibility
)
from .loop_scheduler_locking import (  # noqa: F401 - re-exported for backward compatibility
    LockEvaluation,
    LockFileSnapshot,
    ProcessIdentity,
)
from .loop_signal_id import _SignalIdGenerator
from .loop_vmalert_discovery import run_vmalert_discovery as _run_vmalert_discovery_impl
from .loop_vmalert_rule_state import run_vmalert_rule_state_collection as _run_vmalert_rule_state_collection_impl
from .notifications import NotificationArtifact, build_external_analysis_notification, build_suspicious_comparison_notification, write_notification_artifact
from .ui import write_health_ui_index
from .utils import normalize_ref
from .validators import ComparisonDecisionValidator, DrilldownArtifactValidator


def _is_openai_compatible_provider(provider_name: str) -> bool:
    """Check if provider name resolves to the OpenAI-compatible provider.

    This handles both canonical (openai_compatible) and legacy (llamacpp)
    provider names during the migration period.
    """
    return provider_name in (OPENAI_COMPATIBLE_PROVIDER_NAME, LEGACY_LLAMACPP_PROVIDER_NAME)


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


# HealthAssessmentResult and HealthAssessmentArtifact are imported from loop_history
# for consistency and to avoid duplication. See imports above.


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
                    parsed_trigger_details.append(
                        TriggerDetail(
                            type=str(detail_raw.get("type", "")),
                            reason=str(detail_raw.get("reason", "")),
                            baseline_expectation=str(detail_raw.get("baseline_expectation")) if detail_raw.get("baseline_expectation") else None,
                            actual_value=str(detail_raw.get("actual_value", "")),
                            previous_run_value=str(detail_raw.get("previous_run_value")) if detail_raw.get("previous_run_value") else None,
                            why=str(detail_raw.get("why", "")),
                            next_check=str(detail_raw.get("next_check")) if detail_raw.get("next_check") else None,
                            peer_roles=str(detail_raw.get("peer_roles")) if detail_raw.get("peer_roles") else None,
                            classification=str(detail_raw.get("classification")) if detail_raw.get("classification") else None,
                        )
                    )

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
                "The health config key 'run_id' is deprecated. Provide 'run_label' instead; the legacy value will be used as the stable label while each execution generates a unique run_id.",
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
            watched_helm = tuple(str(item).strip() for item in entry.get("watched_helm_releases") or [] if str(item).strip())
            watched_crd = tuple(str(item).strip() for item in entry.get("watched_crd_families") or [] if str(item).strip())
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
                raise ValueError(f"Target '{label}' missing required metadata: {', '.join(missing_metadata)}")
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
                raise ValueError(f"Unable to locate baseline policy for target '{label}': {exc}")
            if resolved_path is None:
                raise ValueError(f"Target '{label}' cannot resolve a baseline policy; declare baseline_policy_path or register its cohort in baseline_policies.")
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
            manual_pairs.append(ManualComparison(primary=normalized_primary, secondary=normalized_secondary))

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
        return self.target_baselines.get(target.label, (self.baseline_policy, self.baseline_policy_path))


def build_health_assessment(
    snapshot: ClusterSnapshot,
    target: HealthTarget,
    previous: HealthHistoryEntry | None,
    baseline: BaselinePolicy,
    warning_event_threshold: int = 0,
    image_pull_secret_insight: ImagePullSecretInsight | None = None,
) -> HealthAssessmentResult:
    """Build a health assessment for a cluster snapshot.

    Delegates to the extracted loop_health_assessment module.
    """
    return _build_health_assessment_impl(
        snapshot=snapshot,
        target=target,
        previous=previous,
        baseline=baseline,
        warning_event_threshold=warning_event_threshold,
        image_pull_secret_insight=image_pull_secret_insight,
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
        summary_parts.append(f"{primary.target.label} ({primary_role})" if primary_role else primary.target.label)
        summary_parts.append(f"{secondary.target.label} ({secondary_role})" if secondary_role else secondary.target.label)
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
                reason=(f"baseline mismatch ({primary_path} vs {secondary_path})" if primary_path and secondary_path else "baseline mismatch"),
                baseline_expectation=None,
                actual_value=f"{primary_path} vs {secondary_path}",
                previous_run_value=None,
                why=("Targets rely on different baseline policies, so expected parity between them may not hold."),
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
    if policy.control_plane_version and not baseline_policy.is_drift_allowed(BaselineDriftCategory.CONTROL_PLANE_VERSION):
        primary_version = primary.snapshot.metadata.control_plane_version or "unknown"
        secondary_version = secondary.snapshot.metadata.control_plane_version or "unknown"
        if primary_version != secondary_version:
            expectation = baseline_policy.control_plane_expectation
            expectation_desc = expectation.describe() if expectation else None
            reason = f"control plane version drift ({primary_version} vs {secondary_version})"
            previous_value = f"{primary.target.label}: {_format_previous_control_plane(primary.snapshot.metadata.cluster_id)} | {secondary.target.label}: {_format_previous_control_plane(secondary.snapshot.metadata.cluster_id)}"
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
    if policy.watched_helm_release and not baseline_policy.is_drift_allowed(BaselineDriftCategory.WATCHED_HELM_RELEASE):
        watched_releases = set(primary.target.watched_helm_releases) | set(secondary.target.watched_helm_releases)
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
            previous_value = f"{primary.target.label}: {_format_previous_release(primary.snapshot.metadata.cluster_id, release_key)} | {secondary.target.label}: {_format_previous_release(secondary.snapshot.metadata.cluster_id, release_key)}"
            why_parts = []
            if release_policy:
                if release_policy.why:
                    why_parts.append(release_policy.why)
            else:
                why_parts.append(f"Watched Helm release {release_key} drift can cause workload unpredictability.")
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
    if policy.watched_crd and not baseline_policy.is_drift_allowed(BaselineDriftCategory.WATCHED_CRD):
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
            previous_value = f"{primary.target.label}: {_format_previous_crd(primary.snapshot.metadata.cluster_id, crd_name)} | {secondary.target.label}: {_format_previous_crd(secondary.snapshot.metadata.cluster_id, crd_name)}"
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
        if primary_prev and primary_prev.health_rating == HealthRating.HEALTHY and (primary.assessment and primary.assessment.rating == HealthRating.DEGRADED):
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
        if secondary_prev and secondary_prev.health_rating == HealthRating.HEALTHY and (secondary.assessment and secondary.assessment.rating == HealthRating.DEGRADED):
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
                        reason=(f"missing evidence anomaly for {entry.target.label}: {', '.join(sorted(new_missing))}"),
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
        self._manual_keys: set[tuple[str, str]] = {(item.primary, item.secondary) for item in manual_items}
        self._manual_drilldown_contexts: set[str] = {normalize_ref(value) for value in (manual_drilldown_contexts or []) if value}
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
        # Storage for vmalert inventory (populated by _run_vmalert_discovery)
        self._vmalert_inventory: VmalertSourceInventory | None = None

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
        """Extract a field from failure metadata.

        Delegates to extract_failure_metadata_field for the implementation.
        Kept as a static method for backward compatibility.
        """
        return extract_failure_metadata_field(metadata, key)

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
        # Run vmalert discovery (non-fatal)
        self._run_vmalert_discovery(records, directories)
        # Collect vmalert rule state from discovered sources (non-fatal)
        self._run_vmalert_rule_state_collection(directories)
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
        execution_artifacts = tuple(a for a in external_artifacts if a.purpose == ExternalAnalysisPurpose.NEXT_CHECK_EXECUTION)
        plan_artifact = self._run_next_check_planning(review_path, enrichment_artifact, directories, execution_artifacts)
        if plan_artifact:
            external_artifacts.append(plan_artifact)
        healthy_count = sum(1 for artifact in assessments if artifact.health_rating == HealthRating.HEALTHY)
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
        # Scan for durable Alertmanager proposal candidates from aggregated patterns
        try:
            durable_candidates = scan_and_propose(directories["root"])
            durable_proposals: tuple[HealthProposal, ...] = ()
            if durable_candidates:
                durable_proposals = tuple(
                    HealthProposal.from_durable_proposal_candidate(
                        candidate=candidate,
                        source_run_id=self.run_id,
                        source_artifact_path=str(directories["root"] / "alertmanager-durable-proposals" / f"{candidate.proposal_id}.json"),
                    )
                    for candidate in durable_candidates
                )
                self._log_event(
                    "health-loop",
                    "INFO",
                    "Durable Alertmanager proposals generated",
                    durable_proposal_count=len(durable_proposals),
                    event="durable-proposals-generated",
                )
            # Merge durable proposals with run-scoped proposals
            all_proposals = (*proposals, *durable_proposals)
        except OSError as exc:
            self._log_event(
                "health-loop",
                "WARNING",
                "Durable proposal scan failed",
                severity_reason=str(exc),
                event="durable-proposals-failed",
            )
            all_proposals = proposals
        try:
            ui_index_path = write_health_ui_index(
                directories["root"],
                self.run_id,
                self.run_label,
                self.config.collector_version,
                records,
                assessments,
                drilldowns,
                all_proposals,
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
                proposal_count=len(all_proposals),
                durable_proposal_count=len(durable_proposals) if "durable_proposals" in dir() else 0,
                external_analysis_count=len(external_artifacts),
                event="ui-index-generated",
            )
        except OSError as exc:
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
        prune_external_analysis_history(
            retention=self.config.external_analysis.retention,
            directory=directory,
            run_id=self.run_id,
            log_event=self._log_event,
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
            filename = _format_snapshot_filename(self.run_id, target.label, snapshot.metadata.captured_at)
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
        return build_assessments_for_records(
            records=records,
            history=history,
            assessment_dir=assessment_dir,
            notification_dir=notification_dir,
            run_id=self.run_id,
            run_label=self.run_label,
            warning_event_threshold=self.config.trigger_policy.warning_event_threshold,
            record_notification_fn=self._record_notification,
            image_pull_inspector=self._image_pull_secret_inspector,
            log_event_fn=self._log_event,
        )

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

    def _run_external_analysis(self, records: list[HealthSnapshotRecord], directories: dict[str, Path]) -> list[ExternalAnalysisArtifact]:
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
        record_lookup = {normalize_ref(record.target.label): record for record in records}
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
            source_artifact = record.assessment.artifact_path if record.assessment else str(record.path)
            analysis_request = ExternalAnalysisRequest(
                run_id=self.run_id,
                cluster_label=record.target.label,
                source_artifact=source_artifact,
            )
            artifact = adapter.run(analysis_request)
            artifact_path = directories["external_analysis"] / (f"{self.run_id}-{record.target.label}-{adapter.name}.json")
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

    def _run_auto_drilldown_analysis(self, drilldowns: list[DrilldownArtifact], directories: dict[str, Path]) -> list[ExternalAnalysisArtifact]:
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
            artifact_path = directories["external_analysis"] / (f"{self.run_id}-{drilldown.label}-auto-{provider_name}.json")
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
            if _is_openai_compatible_provider(provider_name):
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
                summary = assessment.recommended_action.description if assessment.recommended_action else (assessment.hypotheses[0].description if assessment.hypotheses else "Auto drilldown interpretation")
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
                    if _is_openai_compatible_provider(provider_name):
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
                    llm_call_id_val = build_llm_call_id(self.run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label)
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
                        top_prompt_sections=[s.get("name") for s in prompt_diags.get("top_prompt_sections", [])],
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
                        "llm_call_id": build_llm_call_id(self.run_id, "auto-drilldown", provider_name, cluster_label=drilldown.label),
                        "llm_call": True,
                        "max_tokens": start_max_tokens,
                        "actual_prompt_chars": actual_prompt_chars,
                    }
            # REVIEWED: LLM call boundary in auto-drilldown.
            # assess_drilldown_artifact() calls the provider and may raise exceptions from:
            # - provider network/HTTP errors (requests.RequestException, httpx.HTTPError, etc.)
            # - LLM parsing errors (ValueError subclasses, already handled above)
            # - unexpected provider SDK errors
            # Non-fatal fallback: FAILED status with failure_metadata (when available).
            # No credential exposure: failure_metadata uses bounded field extraction, not raw response.
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
                    if _is_openai_compatible_provider(provider_name):
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
                        top_prompt_sections=[s.get("name") for s in prompt_diags.get("top_prompt_sections", [])],
                        elapsed_ms=elapsed_ms,
                        failure_class=classified_failure_class.value,
                        exception_type=classified_exc_type,
                    )
                    failure_metadata = {"prompt_diagnostics": prompt_diags}
                # REVIEWED: internal diagnostics extraction boundary.
                # Narrowed to TypeError/AttributeError/KeyError/ValueError: these are
                # the expected exceptions when accessing dict fields or calling helpers
                # during prompt diagnostics extraction. Non-fatal fallback: no diagnostics.
                except (TypeError, AttributeError, KeyError, ValueError):
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
            severity = "INFO" if status == ExternalAnalysisStatus.SUCCESS else "WARNING" if status == ExternalAnalysisStatus.SKIPPED else "ERROR"
            # Build status-appropriate log message
            _interp_label = "Auto drilldown interpretation failed" if status == ExternalAnalysisStatus.FAILED else "Auto drilldown interpretation skipped" if status == ExternalAnalysisStatus.SKIPPED else "Auto drilldown interpretation recorded"
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
            # Resolve max_tokens for openai-compatible provider
            result_max_tokens: int | None = None
            if _is_openai_compatible_provider(provider_name):
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

    def _run_review_enrichment(self, review_path: Path | None, directories: dict[str, Path]) -> ExternalAnalysisArtifact | None:
        policy = self.config.external_analysis.review_enrichment
        if not policy.enabled or not review_path:
            return None
        provider_requested = (policy.provider or "").strip()
        # Normalize provider name to canonical form for artifact naming and adapter lookup
        provider_normalized = normalize_adapter_name(provider_requested) if provider_requested else "review-enrichment"
        provider_segment = _safe_label(provider_normalized) if provider_normalized else "review-enrichment"
        artifact_path = directories["external_analysis"] / (f"{self.run_id}-review-enrichment-{provider_segment}.json")
        start = time.perf_counter()
        try:
            if not provider_requested:
                raise ValueError("No review enrichment provider configured")
            # Use normalized name first for adapter lookup, then requested as fallback
            adapter = self._analysis_adapters.get(provider_normalized) or self._analysis_adapters.get(provider_normalized.lower()) or self._analysis_adapters.get(provider_requested) or self._analysis_adapters.get(provider_requested.lower())
            if not adapter:
                raise ValueError(f"Adapter '{provider_requested}' (normalized: '{provider_normalized}') is not registered for review enrichment")
            # Run preflight check to validate provider configuration before execution
            # Pass the originally requested provider name so preflight can report it accurately
            preflight_result = None
            if hasattr(adapter, "preflight_check"):
                try:
                    preflight_result = adapter.preflight_check(provider_requested=provider_requested)
                except TypeError:
                    # Fallback for adapters that don't accept provider_requested parameter
                    preflight_result = adapter.preflight_check()
                if not preflight_result.ok:
                    # Emit ERROR log for provider misconfiguration
                    self._log_event(
                        "review-enrichment",
                        "ERROR",
                        "Review enrichment preflight check failed",
                        run_label=self.run_label,
                        run_id=self.run_id,
                        provider_requested=preflight_result.provider_requested,
                        provider_normalized=preflight_result.provider_normalized,
                        reason=preflight_result.reason or "unknown",
                        operator_message=preflight_result.operator_message or "Provider configuration check failed",
                        artifact_path=str(artifact_path),
                        status="failed",
                        event="review-enrichment-preflight-failed",
                    )
                    # Build failure artifact with provider metadata
                    duration_ms = int((time.perf_counter() - start) * 1000)
                    failure_metadata: dict[str, object] = {
                        "preflight_failed": True,
                        "provider_requested": preflight_result.provider_requested,
                        "provider_normalized": preflight_result.provider_normalized,
                        "reason": preflight_result.reason or "unknown",
                        "operator_message": preflight_result.operator_message or "Provider configuration check failed",
                    }
                    artifact = ExternalAnalysisArtifact(
                        tool_name=adapter.name,
                        run_id=self.run_id,
                        cluster_label=self.run_label,
                        run_label=self.run_label,
                        source_artifact=str(review_path),
                        summary=f"Provider preflight failed: {preflight_result.reason or 'configuration error'}",
                        findings=(),
                        suggested_next_checks=(),
                        status=ExternalAnalysisStatus.FAILED,
                        raw_output=None,
                        timestamp=datetime.now(UTC),
                        artifact_path=str(artifact_path),
                        provider=preflight_result.provider_normalized,
                        duration_ms=duration_ms,
                        purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
                        error_summary=preflight_result.operator_message,
                        failure_metadata=failure_metadata,
                    )
                    write_external_analysis_artifact(artifact_path, artifact)
                    # Log final result with preflight failure info
                    self._log_event(
                        "review-enrichment",
                        "ERROR",
                        "Review enrichment failed",
                        run_label=self.run_label,
                        run_id=self.run_id,
                        provider_requested=preflight_result.provider_requested,
                        provider_normalized=preflight_result.provider_normalized,
                        provider_legacy_alias_used=preflight_result.legacy_provider_used,
                        artifact_path=str(artifact_path),
                        status="failed",
                        elapsed_ms=duration_ms,
                        event="review-enrichment-result",
                    )
                    return artifact
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
                provider=provider_normalized,
                duration_ms=duration_ms,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
            )
        except ValueError as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            # Distinguish between unconfigured (SKIPPED) and misconfigured (FAILED).
            # - "no provider configured": operator did not set a provider → SKIP (intent to skip)
            # - "adapter not registered": provider set but adapter missing → SKIP (graceful degradation)
            # - "missing base_url" / "invalid config": provider set with structural problem → FAIL
            exc_str = str(exc)
            is_unconfigured = not provider_requested or "No review enrichment provider configured" in exc_str
            is_adapter_missing = "is not registered for review enrichment" in exc_str
            artifact_status = ExternalAnalysisStatus.SKIPPED if (is_unconfigured or is_adapter_missing) else ExternalAnalysisStatus.FAILED
            artifact = ExternalAnalysisArtifact(
                tool_name=provider_requested or "review-enrichment",
                run_id=self.run_id,
                cluster_label=self.run_label,
                run_label=self.run_label,
                source_artifact=str(review_path),
                summary=str(exc),
                status=artifact_status,
                timestamp=datetime.now(UTC),
                artifact_path=str(artifact_path),
                provider=provider_normalized if provider_requested else None,
                duration_ms=duration_ms,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
                skip_reason=str(exc) if (is_unconfigured or is_adapter_missing) else None,
                error_summary=str(exc) if not (is_unconfigured or is_adapter_missing) else None,
            )
        # REVIEWED: review enrichment LLM call boundary.
        # adapter.run() calls the provider and may raise exceptions from:
        # - provider network/HTTP errors (requests.RequestException, httpx.HTTPError, etc.)
        # - LLM parsing errors (ValueError subclasses, already handled above)
        # - unexpected provider SDK errors
        # Non-fatal fallback: FAILED status with bounded error_summary (str(exc)).
        # No credential exposure: error_summary is the exception message only.
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            artifact = ExternalAnalysisArtifact(
                tool_name=provider_requested or "review-enrichment",
                run_id=self.run_id,
                cluster_label=self.run_label,
                run_label=self.run_label,
                source_artifact=str(review_path),
                summary=str(exc),
                status=ExternalAnalysisStatus.FAILED,
                timestamp=datetime.now(UTC),
                artifact_path=str(artifact_path),
                provider=provider_normalized if provider_requested else None,
                duration_ms=duration_ms,
                purpose=ExternalAnalysisPurpose.REVIEW_ENRICHMENT,
                error_summary=str(exc),
            )
        write_external_analysis_artifact(artifact_path, artifact)
        severity = "INFO" if artifact.status == ExternalAnalysisStatus.SUCCESS else "WARNING" if artifact.status == ExternalAnalysisStatus.SKIPPED else "ERROR"
        message = "Review enrichment recorded" if artifact.status == ExternalAnalysisStatus.SUCCESS else "Review enrichment skipped" if artifact.status == ExternalAnalysisStatus.SKIPPED else "Review enrichment failed"
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
            provider=provider_normalized if provider_requested else "unspecified",
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

        # Extract reason/operator_message from artifact failure_metadata for ERROR logging
        reason: str | None = None
        operator_message: str | None = None
        if artifact.status == ExternalAnalysisStatus.FAILED and artifact.failure_metadata:
            failure_meta = cast(dict[str, Any], artifact.failure_metadata)
            reason = str(failure_meta.get("reason")) if failure_meta.get("reason") else None
            operator_message = str(failure_meta.get("operator_message")) if failure_meta.get("operator_message") else None

        # Additional failure metadata for failed status
        log_kwargs: dict[str, Any] = {
            "run_label": self.run_label,
            "run_id": self.run_id,
            "provider": provider_normalized if provider_requested else "unspecified",
            "artifact_path": str(artifact_path),
            "status": artifact.status.value,
            "next_checks_count": next_checks_count,
            "error_summary": error_summary,
            "skip_reason": skip_reason,
            "event": "review-enrichment-result",
        }
        # Include failure metadata for FAILED status if available
        if artifact.status == ExternalAnalysisStatus.FAILED:
            if artifact.duration_ms is not None:
                log_kwargs["elapsed_ms"] = artifact.duration_ms
            if reason:
                log_kwargs["reason"] = reason
            if operator_message:
                log_kwargs["operator_message"] = operator_message
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
        return run_next_check_planning(
            review_path=review_path,
            enrichment_artifact=enrichment_artifact,
            directories=directories,
            run_id=self.run_id,
            run_label=self.run_label,
            log_event=self._log_event,
            execution_artifacts=execution_artifacts,
        )

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
        # REVIEWED: review pipeline write / domain transformation boundary.
        # _write_review_and_proposals_impl may raise exceptions from:
        # - domain transformation errors (ValueError, TypeError, KeyError, AttributeError)
        # - artifact write errors (OSError)
        # Internal pipeline already catches build_health_review and proposal generation
        # errors separately; this catches JSON write failures and unexpected transform
        # errors. Non-fatal fallback: return None, empty proposals. No credential exposure.
        except (ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
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
            ignored_categories = tuple(sorted(set(primary_record.baseline_policy.ignored_drift_categories) | set(secondary_record.baseline_policy.ignored_drift_categories)))
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
            decision_reason = policy_reason if not policy_eligible else "; ".join(detail.reason for detail in trigger_details) if triggered else "policy compatible but no triggers fired"
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
        return load_runner_history(history_path=history_path)

    def _persist_history(self, history: dict[str, HealthHistoryEntry], directories: dict[str, Path]) -> None:
        return persist_runner_history(
            history=history,
            directories=directories,
            run_id=self.run_id,
            log_event_fn=self._log_event,
        )

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

    def _run_vmalert_discovery(
        self,
        records: list[HealthSnapshotRecord],
        directories: dict[str, Path],
    ) -> None:
        """Run vmalert discovery for each cluster target and persist the inventory.

        Delegates to loop_vmalert_discovery module for the actual discovery logic.
        Stores the verified inventory in self._vmalert_inventory for downstream processing.

        This is non-fatal: discovery/verification failures are logged but do not stop the run.
        """

        def log_callback(component: str, severity: str, message: str, **metadata: Any) -> None:
            self._log_event(component, severity, message, **metadata)

        self._vmalert_inventory = _run_vmalert_discovery_impl(
            records=records,
            directories=directories,
            log_event=log_callback,
            run_id=self.run_id,
        )

    def _run_vmalert_rule_state_collection(
        self,
        directories: dict[str, Path],
    ) -> None:
        """Collect vmalert rule state from discovered sources.

        Delegates to loop_vmalert_rule_state module for the actual collection logic.

        This is non-fatal: fetch failures are logged but do not stop the run.
        """
        _run_vmalert_rule_state_collection_impl(
            inventory=self._vmalert_inventory,
            directories=directories,
            run_id=self.run_id,
            cluster_label=self.run_label,
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

        Delegates to start_alertmanager_port_forward from loop_alertmanager_port_forward module.
        Kept as a wrapper for backward compatibility.
        """
        return start_alertmanager_port_forward(
            namespace=namespace,
            service_name=service_name,
            context=context,
            run_id=self.run_id,
            run_label=self.run_label,
            log_event=self._log_event,
            choose_free_local_port=self._choose_free_local_port,
            wait_for_port_ready=self._wait_for_port_ready,
        )

    def _stop_alertmanager_port_forward(
        self,
        process: subprocess.Popen[str],
        local_port: int | None,
    ) -> None:
        """Stop the port-forward process and log the event.

        Delegates to stop_alertmanager_port_forward from loop_alertmanager_port_forward module.
        Kept as a wrapper for backward compatibility.
        """
        stop_alertmanager_port_forward(
            process=process,
            local_port=local_port,
            run_id=self.run_id,
            run_label=self.run_label,
            log_event=self._log_event,
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
    manual_analysis_requests = _parse_manual_external_analysis_requests(manual_external_analysis or [])
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
