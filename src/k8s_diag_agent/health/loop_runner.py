"""Health loop runner orchestration.

This module contains the HealthLoopRunner class which orchestrates the health
assessment loop. It handles snapshot collection, comparison, assessment building,
and artifact generation.

Split from loop.py for LLM-friendly file sizes while preserving the public
import contract through the loop.py facade.

HealthRunConfig and build_health_assessment have been moved to loop_run_config.
Helper methods have been moved to loop_runner_*.py modules:
- loop_runner_compatibility.py: compatibility delegator methods
- loop_runner_collection.py: snapshot collection helpers
- loop_runner_review.py: review/proposals helpers
- loop_runner_execute.py: execute() orchestration
- loop_runner_monitoring.py: Alertmanager/vmalert discovery
- loop_runner_drilldown_analysis.py: auto-drilldown analysis
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..collect.cluster_snapshot import ClusterSnapshot
from ..collect.live_snapshot import collect_cluster_snapshot, list_kube_contexts
from ..compare.two_cluster import ClusterComparison, compare_snapshots
from ..external_analysis.adapter import build_external_analysis_adapters
from ..external_analysis.artifact import ExternalAnalysisArtifact
from ..external_analysis.config import ExternalAnalysisSettings
from ..llm.provider import LEGACY_LLAMACPP_PROVIDER_NAME, OPENAI_COMPATIBLE_PROVIDER_NAME
from ..structured_logging import DEFAULT_HEALTH_LOG, emit_structured_log
from . import loop_history
from .drilldown import DrilldownCollector
from .image_pull_secret import ImagePullSecretInspector
from .loop_automatic_diagnosis import run_automatic_diagnosis_loop  # noqa: F401 - re-exported as a stable patch seam for tests and compatibility wrappers
from .loop_comparison_policy import BaselineRegistry
from .loop_config_helpers import _parse_manual_external_analysis_requests, _parse_manual_triggers
from .loop_drilldown_helpers import determine_drilldown_reasons as _determine_drilldown_reasons_impl
from .loop_history import (
    HealthAssessmentArtifact,
    HealthHistoryEntry,
    _build_runtime_run_id,
    _safe_label,
)
from .loop_models import ManualComparison
from .loop_port_forward_helpers import _choose_free_local_port, _wait_for_port_ready
from .loop_retention import prune_external_analysis_history
from .loop_run_config import HealthRunConfig
from .loop_runner_collection import collect_snapshots_for_targets
from .loop_runner_compatibility import (
    failure_metadata_field_compat,
    run_alertmanager_discovery_compat,
    run_alertmanager_snapshot_collection_compat,
    run_auto_drilldown_analysis_compat,
    run_automatic_diagnosis_loop_compat,
    run_vmalert_discovery_compat,
    start_alertmanager_port_forward_compat,
    stop_alertmanager_port_forward_compat,
)
from .loop_runner_review import write_review_artifact
from .loop_types import HealthSnapshotRecord as _HealthSnapshotRecord
from .loop_types import HealthTarget as _HealthTarget
from .loop_types import ManualExternalAnalysisRequest
from .notifications import NotificationArtifact, write_notification_artifact
from .utils import normalize_ref

# Re-export for backward compatibility
HealthTarget = _HealthTarget
HealthSnapshotRecord = _HealthSnapshotRecord

if TYPE_CHECKING:
    from ..external_analysis.alertmanager_discovery import AlertmanagerSourceInventory
    from ..external_analysis.next_check_incident_linkage import IncidentLinkageContext
    from ..external_analysis.vmalert_discovery import VmalertSourceInventory
    from .adaptation import HealthProposal
    from .drilldown import DrilldownArtifact
    from .loop_comparison_types import ComparisonTriggerArtifact


# Module constants
_HISTORY_FILENAME = loop_history._HISTORY_FILENAME
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS_DIR = _PROJECT_ROOT / "scripts"


def _is_openai_compatible_provider(provider_name: str) -> bool:
    """Check if provider name resolves to the OpenAI-compatible provider."""
    return provider_name in (OPENAI_COMPATIBLE_PROVIDER_NAME, LEGACY_LLAMACPP_PROVIDER_NAME)


class HealthLoopRunner:
    """Orchestrates the health assessment loop for multiple clusters."""

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
        """Initialize the health loop runner."""
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
        self._alertmanager_inventory: AlertmanagerSourceInventory | None = None
        self._vmalert_inventory: VmalertSourceInventory | None = None

    def _log_event(self, component: str, severity: str, message: str, **metadata: Any) -> None:
        """Emit a structured log event."""
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
        """Record a notification artifact."""
        artifact_path = write_notification_artifact(directory, artifact)
        self._notification_records.append((artifact, artifact_path))
        return artifact_path

    @property
    def latest_external_artifacts(self) -> list[ExternalAnalysisArtifact]:
        """Get the latest external artifacts from the last run."""
        return list(self._latest_external_artifacts)

    def execute(
        self,
    ) -> tuple[
        list[HealthAssessmentArtifact],
        list[ComparisonTriggerArtifact],
        list[DrilldownArtifact],
    ]:
        """Execute the health loop run.

        This delegates to execute_health_loop_run() from loop_runner_execute.
        """
        from .loop_runner_execute import execute_health_loop_run

        self._log_event("health-loop", "INFO", "Health run started", event="start")
        self._notification_records = []
        directories = self._ensure_directories()
        records = self._collect_snapshots(directories["snapshots"])
        return execute_health_loop_run(self, records, directories)

    def _ensure_directories(self) -> dict[str, Path]:
        """Ensure all required directories exist."""
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
        """Prune external analysis history based on retention policy."""
        prune_external_analysis_history(
            retention=self.config.external_analysis.retention,
            directory=directory,
            run_id=self.run_id,
            log_event=self._log_event,
        )

    def _collect_snapshots(self, directory: Path) -> list[HealthSnapshotRecord]:
        """Collect snapshots from all target clusters."""
        return collect_snapshots_for_targets(
            targets=list(self.config.targets),
            available_contexts=self.available_contexts,
            run_id=self.run_id,
            snapshot_collector=self.snapshot_collector,
            baseline_for_target_fn=self.config.baseline_for_target,
            log_event_fn=self._log_event,
            directory=directory,
        )

    def _write_review_artifact(
        self,
        assessments: list[HealthAssessmentArtifact],
        drilldowns: list[DrilldownArtifact],
        directories: dict[str, Path],
    ) -> tuple[Path | None, tuple[HealthProposal, ...]]:
        """Build health review and generate proposals from assessments and drilldowns."""
        return write_review_artifact(
            run_id=self.run_id,
            run_label=self.run_label,
            assessments=assessments,
            drilldowns=drilldowns,
            directories=directories,
            warning_threshold=self.config.trigger_policy.warning_event_threshold,
            baseline_policy=self.config.baseline_policy,
            log_event_fn=self._log_event,
        )

    def _determine_drilldown_reasons(
        self,
        record: HealthSnapshotRecord,
        previous_history: dict[str, HealthHistoryEntry],
    ) -> tuple[str, ...]:
        """Determine drilldown reasons for a cluster record."""
        return _determine_drilldown_reasons_impl(
            record=record,
            previous_history=previous_history,
            manual_drilldown_contexts=self._manual_drilldown_contexts,
            warning_event_threshold=self.config.trigger_policy.warning_event_threshold,
        )

    def _derive_incident_linkage_context(
        self,
        records: list[HealthSnapshotRecord],
    ) -> IncidentLinkageContext | None:
        """Derive incident linkage context from cluster snapshots."""
        from .loop_incident_linkage_from_snapshot import derive_linkage_context_from_snapshots

        snapshots = [record.snapshot for record in records if record.snapshot is not None]
        if not snapshots:
            return None
        return derive_linkage_context_from_snapshots(snapshots, self.run_id)

    def _run_monitoring_discovery(
        self,
        records: list[HealthSnapshotRecord],
        directories: dict[str, Path],
    ) -> None:
        """Run Alertmanager and vmalert discovery and collection."""
        from .loop_runner_monitoring import (
            run_alertmanager_discovery,
            run_alertmanager_snapshot_collection,
            run_vmalert_discovery,
            run_vmalert_rule_state_collection,
        )

        self._alertmanager_inventory = run_alertmanager_discovery(
            records=records,
            directories=directories,
            log_event=self._log_event,
            run_id=self.run_id,
        )
        run_alertmanager_snapshot_collection(
            inventory=self._alertmanager_inventory,
            run_id=self.run_id,
            run_label=self.run_label,
            log_event=self._log_event,
            directories=directories,
            start_port_forward=self._start_alertmanager_port_forward,
            stop_port_forward=self._stop_alertmanager_port_forward,
        )
        self._vmalert_inventory = run_vmalert_discovery(
            records=records,
            directories=directories,
            log_event=self._log_event,
            run_id=self.run_id,
        )
        run_vmalert_rule_state_collection(
            inventory=self._vmalert_inventory,
            directories=directories,
            run_id=self.run_id,
            cluster_label=self.run_label,
        )

    def _choose_free_local_port(self) -> int:
        """Choose a free local TCP port for port-forward."""
        return _choose_free_local_port()

    def _wait_for_port_ready(
        self,
        host: str,
        port: int,
        timeout_seconds: float = 5.0,
        poll_interval: float = 0.1,
    ) -> bool:
        """Wait for a TCP port to become accepting connections."""
        return _wait_for_port_ready(host, port, timeout_seconds, poll_interval)

    def _start_alertmanager_port_forward(
        self,
        namespace: str,
        service_name: str,
        context: str | None,
    ) -> tuple:
        """Start kubectl port-forward to an Alertmanager service."""
        return start_alertmanager_port_forward_compat(
            runner=self,
            namespace=namespace,
            service_name=service_name,
            context=context,
        )

    def _stop_alertmanager_port_forward(
        self,
        process: subprocess.Popen[str],
        local_port: int | None,
    ) -> None:
        """Stop the port-forward process and log the event."""
        stop_alertmanager_port_forward_compat(
            runner=self,
            process=process,
            local_port=local_port,
        )

    def _run_auto_drilldown_analysis(
        self,
        drilldowns: list[DrilldownArtifact],
        directories: dict[str, Path],
    ) -> list[ExternalAnalysisArtifact]:
        """Run LLM auto-drilldown analysis on drilldown artifacts.

        This is a compatibility delegator that wraps run_auto_drilldown_analysis
        from loop_runner_drilldown_analysis, providing the instance-based interface
        expected by existing tests and production call sites.
        """
        return run_auto_drilldown_analysis_compat(self, drilldowns, directories)

    def _run_alertmanager_discovery(
        self,
        records: list[HealthSnapshotRecord],
        directories: dict[str, Path],
    ) -> AlertmanagerSourceInventory | None:
        """Run Alertmanager discovery for each cluster target.

        This is a compatibility delegator that wraps run_alertmanager_discovery
        from loop_runner_monitoring.
        """
        return run_alertmanager_discovery_compat(self, records, directories)

    def _run_alertmanager_snapshot_collection(
        self,
        directories: dict[str, Path],
    ) -> None:
        """Collect Alertmanager snapshot and compact artifacts for tracked sources.

        This is a compatibility delegator that wraps run_alertmanager_snapshot_collection
        from loop_runner_monitoring.
        """
        run_alertmanager_snapshot_collection_compat(self, directories)

    def _run_vmalert_discovery(
        self,
        records: list[HealthSnapshotRecord],
        directories: dict[str, Path],
    ) -> VmalertSourceInventory | None:
        """Run vmalert discovery for each cluster target.

        This is a compatibility delegator that wraps run_vmalert_discovery
        from loop_runner_monitoring.
        """
        return run_vmalert_discovery_compat(self, records, directories)

    def _run_automatic_diagnosis_loop(
        self,
        external_analysis_dir: Path,
    ) -> dict[str, Any]:
        """Run automatic diagnosis loop evidence collection.

        This is a compatibility delegator that wraps run_automatic_diagnosis_loop
        from loop_automatic_diagnosis, providing the instance-based interface
        expected by existing tests and production call sites.

        Returns:
            Bounded result summary dict.
        """
        return run_automatic_diagnosis_loop_compat(self, external_analysis_dir)

    @staticmethod
    def _failure_metadata_field(
        metadata: dict[str, object] | None,
        field_name: str,
    ) -> str | bool | None:
        """Extract a field from failure metadata, checking top-level and nested prompt_diagnostics.

        This static helper provides backward compatibility for code that references
        HealthLoopRunner._failure_metadata_field.
        """
        return failure_metadata_field_compat(metadata, field_name)


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
    """Run a health loop with the given configuration."""
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
