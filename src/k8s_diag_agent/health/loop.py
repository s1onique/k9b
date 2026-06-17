"""Per-cluster health assessment loop with trigger-aware comparisons."""

from __future__ import annotations

import json
import subprocess
import warnings
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4  # noqa: F401 - re-exported for backward compatibility

from ..collect.cluster_snapshot import ClusterSnapshot
from ..collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from ..compare.two_cluster import ClusterComparison, compare_snapshots
from ..external_analysis.adapter import build_external_analysis_adapters
from ..external_analysis.alertmanager_discovery import AlertmanagerSourceInventory
from ..external_analysis.alertmanager_durable_learning import scan_and_propose
from ..external_analysis.artifact import ExternalAnalysisArtifact, ExternalAnalysisPurpose
from ..external_analysis.config import ExternalAnalysisSettings, parse_external_analysis_settings
from ..external_analysis.vmalert_discovery import VmalertSourceInventory
from ..llm.provider import LEGACY_LLAMACPP_PROVIDER_NAME, OPENAI_COMPATIBLE_PROVIDER_NAME
from ..structured_logging import DEFAULT_HEALTH_LOG, emit_structured_log
from . import loop_history
from .adaptation import HealthProposal
from .baseline import BaselinePolicy, resolve_baseline_policy_path
from .drilldown import DrilldownArtifact, DrilldownCollector
from .image_pull_secret import ImagePullSecretInsight, ImagePullSecretInspector
from .loop_alertmanager_discovery import run_alertmanager_discovery as _run_alertmanager_discovery_impl
from .loop_alertmanager_port_forward import (
    start_alertmanager_port_forward,
    stop_alertmanager_port_forward,
)
from .loop_alertmanager_snapshot import run_alertmanager_snapshot_collection as _run_alertmanager_snapshot_collection_impl
from .loop_baseline_helpers import _load_baseline_policy_from_path, _normalize_category_list, _parse_cohort_baselines, _policy_for_target, _resolve_target_baseline_path
from .loop_comparison_policy import (  # noqa: F401
    BaselineRegistry,  # noqa: F401 - re-exported for backward compatibility
    _policy_eligible_pair,  # noqa: F401 - re-exported for backward compatibility
    _resolve_peer_role,  # noqa: F401 - re-exported for backward compatibility
    _validate_suspicious_pairs,  # noqa: F401 - re-exported for backward compatibility
)
from .loop_comparison_triggers import determine_pair_trigger_reasons  # noqa: F401 - re-exported for backward compatibility
from .loop_comparison_types import (  # noqa: F401 - re-export for backward compatibility
    ComparisonDecision,  # noqa: F401
    ComparisonIntent,  # noqa: F401 - re-exported for backward compatibility
    ComparisonPeer,  # noqa: F401 - re-exported for backward compatibility
    ComparisonTriggerArtifact,  # noqa: F401 - re-exported for backward compatibility
    TriggerDetail,  # noqa: F401 - re-exported for backward compatibility
    TriggerPolicy,  # noqa: F401 - re-exported for backward compatibility
)
from .loop_config_helpers import _parse_comparison_intent, _parse_manual_external_analysis_requests, _parse_manual_triggers, _parse_threshold
from .loop_drilldown_helpers import determine_drilldown_reasons as _determine_drilldown_reasons_impl
from .loop_failure_metadata import extract_failure_metadata_field
from .loop_health_assessment import build_health_assessment as _build_health_assessment_impl
from .loop_history import HealthAssessmentArtifact, HealthAssessmentResult, HealthHistoryEntry, HealthRating, _build_runtime_run_id, _format_snapshot_filename, _safe_label, _str_or_none, _write_json
from .loop_port_forward_helpers import _choose_free_local_port, _wait_for_port_ready
from .loop_retention import prune_external_analysis_history
from .loop_review_pipeline import write_review_and_proposals as _write_review_and_proposals_impl
from .loop_run_config_helpers import _resolve_collector_version, _resolve_output_dir
from .loop_runner_assessments import build_assessments_for_records
from .loop_runner_comparisons import evaluate_triggers_for_records
from .loop_runner_drilldowns import build_drilldowns_for_records
from .loop_runner_external_analysis import run_external_analysis_for_records
from .loop_runner_history import load_runner_history, persist_runner_history
from .loop_runner_next_check_planning import run_next_check_planning
from .loop_runner_review_enrichment import run_review_enrichment as _run_review_enrichment_impl
from .loop_scheduler import (
    _HEALTH_ONLY_MESSAGE,  # noqa: F401
    HealthLoopScheduler,  # noqa: F401 - re-exported for backward compatibility
)
from .loop_scheduler_locking import (  # noqa: F401 - re-exported for backward compatibility
    LockEvaluation,
    LockFileSnapshot,
    ProcessIdentity,
)

# Import shared types from loop_types.py for this module and re-export for backward compatibility
from .loop_types import HealthSnapshotRecord as _HealthSnapshotRecord
from .loop_types import HealthTarget as _HealthTarget
from .loop_types import ManualExternalAnalysisRequest
from .loop_vmalert_discovery import run_vmalert_discovery as _run_vmalert_discovery_impl
from .loop_vmalert_rule_state import run_vmalert_rule_state_collection as _run_vmalert_rule_state_collection_impl
from .notifications import NotificationArtifact, write_notification_artifact
from .ui import write_health_ui_index
from .utils import normalize_ref

# Re-export for backward compatibility with existing imports
HealthTarget = _HealthTarget
HealthSnapshotRecord = _HealthSnapshotRecord

if TYPE_CHECKING:
    from ..external_analysis.next_check_incident_linkage import IncidentLinkageContext


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
class ManualComparison:
    primary: str
    secondary: str


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
        # Derive incident linkage context from cluster snapshots for production runs
        # This enables deterministic incident_id generation in next-check plan artifacts
        linkage_context = self._derive_incident_linkage_context(records)
        plan_artifact = self._run_next_check_planning(review_path, enrichment_artifact, directories, execution_artifacts, linkage_context)
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
        return build_drilldowns_for_records(
            records=records,
            previous_history=previous_history,
            directory=directory,
            run_id=self.run_id,
            run_label=self.run_label,
            drilldown_collector=self._drilldown_collector,
            manual_drilldown_contexts=self._manual_drilldown_contexts,
            warning_event_threshold=self.config.trigger_policy.warning_event_threshold,
            log_event_fn=self._log_event,
        )

    def _run_external_analysis(self, records: list[HealthSnapshotRecord], directories: dict[str, Path]) -> list[ExternalAnalysisArtifact]:
        """Run manual external analysis for snapshot records.

        Delegates to the extracted loop_runner_external_analysis module.
        Preserves behavior exactly - no schema or artifact contract changes.
        """
        return run_external_analysis_for_records(
            records=records,
            manual_requests=self._manual_external_analysis_requests,
            external_analysis_policy=self._analysis_policy,
            analysis_adapters=self._analysis_adapters,
            run_id=self.run_id,
            run_label=self.run_label,
            record_notification_fn=self._record_notification,
            log_event_fn=self._log_event,
            directories=directories,
        )

    def _run_auto_drilldown_analysis(self, drilldowns: list[DrilldownArtifact], directories: dict[str, Path]) -> list[ExternalAnalysisArtifact]:
        """Run LLM-based auto-drilldown analysis on drilldown artifacts.

        Delegates to the extracted loop_runner_drilldown_analysis module.
        Preserves behavior exactly - no schema or artifact contract changes.
        """
        from .loop_runner_drilldown_analysis import run_auto_drilldown_analysis as _run_auto_drilldown_impl

        return _run_auto_drilldown_impl(
            drilldowns=drilldowns,
            directories=directories,
            run_id=self.run_id,
            run_label=self.run_label,
            auto_drilldown_policy=self.config.external_analysis.auto_drilldown,
            provider_name=self.config.external_analysis.auto_drilldown.provider or "default",
            log_event_fn=self._log_event,
        )

    def _run_review_enrichment(self, review_path: Path | None, directories: dict[str, Path]) -> ExternalAnalysisArtifact | None:
        """Run review enrichment via external analysis adapter.

        Delegates to the extracted loop_runner_review_enrichment module.
        Preserves behavior exactly - no schema or artifact contract changes.
        """
        return _run_review_enrichment_impl(
            review_path=review_path,
            directories=directories,
            review_enrichment_policy=self.config.external_analysis.review_enrichment,
            analysis_adapters=self._analysis_adapters,
            run_id=self.run_id,
            run_label=self.run_label,
            log_event_fn=self._log_event,
        )

    def _run_next_check_planning(
        self,
        review_path: Path | None,
        enrichment_artifact: ExternalAnalysisArtifact | None,
        directories: dict[str, Path],
        execution_artifacts: tuple[ExternalAnalysisArtifact, ...] | None = None,
        linkage_context: IncidentLinkageContext | None = None,
    ) -> ExternalAnalysisArtifact | None:
        return run_next_check_planning(
            review_path=review_path,
            enrichment_artifact=enrichment_artifact,
            directories=directories,
            run_id=self.run_id,
            run_label=self.run_label,
            log_event=self._log_event,
            execution_artifacts=execution_artifacts,
            linkage_context=linkage_context,
        )

    def _derive_incident_linkage_context(
        self,
        records: list[HealthSnapshotRecord],
    ) -> IncidentLinkageContext | None:
        """Derive incident linkage context from cluster snapshots for next-check planning.

        This is the production wiring that connects cluster evidence to next-check
        incident linkage. It examines health signals from cluster snapshots to determine
        if there are incident-class issues that should be linked to next-check plans.

        Args:
            records: List of health snapshot records from cluster collection.

        Returns:
            IncidentLinkageContext if incident-class health issues are detected,
            None otherwise.
        """
        # Import here to avoid circular imports at module level
        from .loop_incident_linkage_from_snapshot import derive_linkage_context_from_snapshots

        # Extract snapshots from records
        snapshots = [record.snapshot for record in records if record.snapshot is not None]
        if not snapshots:
            return None

        return derive_linkage_context_from_snapshots(snapshots, self.run_id)

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
        """Evaluate comparison triggers for peer pairs and build trigger artifacts.

        Delegates to the extracted loop_runner_comparisons module for the core logic.
        Preserves behavior exactly - no schema or artifact contract changes.
        """
        return evaluate_triggers_for_records(
            records=records,
            peers=self.config.peers,
            trigger_policy=self.config.trigger_policy,
            baseline_registry=self.baseline_registry,
            history=history,
            run_id=self.run_id,
            run_label=self.run_label,
            manual_comparison_keys=self._manual_keys,
            comparison_fn=self.comparison_fn,
            record_notification_fn=self._record_notification,
            log_event_fn=self._log_event,
            directories=directories,
        )

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
