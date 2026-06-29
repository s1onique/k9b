"""Health run configuration loading and validation.

This module contains the HealthRunConfig dataclass and its load() classmethod
for parsing health loop configuration files. It also includes the
build_health_assessment() function.

Split from loop_runner.py for LLM-friendly file sizes.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..collect.cluster_snapshot import ClusterSnapshot
    from ..external_analysis.config import ExternalAnalysisSettings
    from .baseline import BaselinePolicy
    from .image_pull_secret import ImagePullSecretInsight
    from .loop_history import HealthAssessmentResult, HealthHistoryEntry

from ..external_analysis.config import ExternalAnalysisSettings
from .baseline import BaselinePolicy, resolve_baseline_policy_path
from .loop_baseline_helpers import (
    _load_baseline_policy_from_path,
    _normalize_category_list,
    _parse_cohort_baselines,
    _policy_for_target,
    _resolve_target_baseline_path,
)
from .loop_comparison_types import ComparisonPeer, TriggerPolicy
from .loop_config_helpers import _parse_comparison_intent, _parse_threshold
from .loop_history import _safe_label, _str_or_none
from .loop_models import ManualComparison
from .loop_run_config_helpers import _resolve_collector_version, _resolve_output_dir
from .loop_types import HealthTarget
from .utils import normalize_ref


@dataclass
class HealthRunConfig:
    """Configuration for a health loop run.

    This dataclass holds all configuration for a health loop execution including
    target clusters, peer mappings, trigger policies, and external analysis settings.
    """

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
        """Load health run configuration from a JSON file.

        Args:
            path: Path to the configuration file.

        Returns:
            HealthRunConfig instance populated from the file.

        Raises:
            ValueError: If the configuration is invalid or missing required fields.
            FileNotFoundError: If baseline policy files cannot be found.
        """
        from ..external_analysis.config import parse_external_analysis_settings

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
                raise ValueError(f"Unable to locate baseline policy near {base_dir}: {exc}") from exc
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
                raise ValueError(f"Unable to locate baseline policy for target '{label}': {exc}") from exc
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

        from .loop_comparison_policy import _validate_suspicious_pairs

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
        """Get the baseline policy for a specific target.

        Args:
            target: The health target to get baseline for.

        Returns:
            Tuple of (BaselinePolicy, optional Path) for the target.
        """
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
    from .loop_health_assessment import build_health_assessment as _build_health_assessment_impl

    return _build_health_assessment_impl(
        snapshot=snapshot,
        target=target,
        previous=previous,
        baseline=baseline,
        warning_event_threshold=warning_event_threshold,
        image_pull_secret_insight=image_pull_secret_insight,
    )
