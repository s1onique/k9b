"""Snapshot collection helper for HealthLoopRunner.

This module provides the _collect_snapshots functionality extracted from
HealthLoopRunner. It handles snapshot collection from target clusters.

These helpers do NOT import HealthLoopRunner.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..collect.cluster_snapshot import ClusterSnapshot
from .baseline import BaselinePolicy
from .loop_history import _format_snapshot_filename, _write_json
from .loop_types import HealthSnapshotRecord, HealthTarget


def collect_snapshots_for_targets(
    targets: list[HealthTarget],
    available_contexts: set[str],
    run_id: str,
    snapshot_collector: Callable[[str], ClusterSnapshot],
    baseline_for_target_fn: Callable[[HealthTarget], tuple[BaselinePolicy, Path | None]],
    log_event_fn: Callable[..., None] | None,
    directory: Path,
) -> list[HealthSnapshotRecord]:
    """Collect snapshots from all target clusters.

    Args:
        targets: List of health target configurations.
        available_contexts: Set of available Kubernetes contexts.
        run_id: Current run identifier.
        snapshot_collector: Function to collect cluster snapshots.
        baseline_for_target_fn: Function to get baseline policy and path for a target.
        log_event_fn: Optional logging callback.

    Returns:
        List of HealthSnapshotRecord objects.
    """
    records: list[HealthSnapshotRecord] = []
    for target in targets:
        if target.context not in available_contexts:
            if log_event_fn:
                log_event_fn(
                    "health-loop",
                    "WARNING",
                    "Context not available for snapshot collection",
                    cluster_label=target.label,
                    cluster_context=target.context,
                    reason="context-unavailable",
                )
            continue
        try:
            snapshot = snapshot_collector(target.context)
        except RuntimeError as exc:
            if log_event_fn:
                log_event_fn(
                    "health-loop",
                    "WARNING",
                    "Snapshot collection failed",
                    cluster_label=target.label,
                    cluster_context=target.context,
                    severity_reason=str(exc),
                    reason="collection-error",
                )
            continue
        filename = _format_snapshot_filename(run_id, target.label, snapshot.metadata.captured_at)
        path = directory / filename
        _write_json(snapshot.to_dict(), path)
        if log_event_fn:
            log_event_fn(
                "health-loop",
                "INFO",
                "Snapshot collected",
                cluster_label=target.label,
                cluster_context=target.context,
                artifact_path=str(path),
                event="snapshot",
            )
        baseline_policy, baseline_path = baseline_for_target_fn(target)
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


__all__ = ["collect_snapshots_for_targets"]
