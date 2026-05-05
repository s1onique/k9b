"""Retention cleanup helpers for health loop artifacts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k8s_diag_agent.external_analysis.config import ExternalAnalysisRetention


LogEventCallback = Callable[..., None]


def prune_external_analysis_history(
    retention: ExternalAnalysisRetention,
    directory: Path,
    run_id: str,
    log_event: LogEventCallback,
) -> None:
    """Prune external analysis artifacts that exceed retention policy.

    Args:
        retention: Retention policy with max_artifacts and/or max_age_days.
        directory: Path to the external-analysis directory.
        run_id: Current run ID - artifacts starting with this prefix are preserved.
        log_event: Callback for logging events. Signature: (component, severity, message, **metadata).
    """
    if retention.max_artifacts is None and retention.max_age_days is None:
        return
    files: list[tuple[Path, float]] = []
    prefix = f"{run_id}-"
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
            log_event(
                "health-loop",
                "WARNING",
                "Failed to remove retained external analysis artifact",
                artifact_path=str(path),
                severity_reason=str(exc),
                event="external-analysis-retention-failed",
            )
    if deleted:
        metadata: dict[str, Any] = {
            "deleted_count": len(deleted),
            "deleted_paths": deleted[:5],
            "retention_policy": {
                "max_artifacts": retention.max_artifacts,
                "max_age_days": retention.max_age_days,
            },
        }
        log_event(
            "health-loop",
            "INFO",
            "External analysis retention pruned old artifacts",
            event="external-analysis-retention",
            **metadata,
        )