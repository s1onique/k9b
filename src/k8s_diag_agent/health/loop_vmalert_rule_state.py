"""vmalert rule state collection runner for health loop.

Extracts the vmalert rule state fetch flow from HealthLoopRunner into a focused module.
This module provides the rule state collection logic that:

1. Reads discovered vmalert sources from the inventory
2. Fetches alert/rule state from eligible sources
3. Persists results to a run-scoped artifact

Key invariants:
- Non-fatal to health loop - failures are recorded but not raised
- Only fetches from sources in useful states
- Artifacts are immutable once written
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..structured_logging import emit_structured_log

if TYPE_CHECKING:
    from ..external_analysis.vmalert_discovery import VmalertSourceInventory

# Shortcut to structured log for this module
_log = emit_structured_log


def run_vmalert_rule_state_collection(
    inventory: VmalertSourceInventory | None,
    directories: dict[str, Path],
    run_id: str,
    cluster_label: str | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any] | None:
    """Collect vmalert rule state from discovered sources and persist artifact.

    This function is non-fatal to the health loop. Failures are logged and recorded
    but do not propagate as exceptions.

    Args:
        inventory: The vmalert source inventory (from discovery phase)
        directories: Run directory mapping from HealthLoopRunner
        run_id: The current run identifier
        cluster_label: Optional cluster label for logging
        timeout_seconds: Timeout for each fetch request

    Returns:
        Metadata dict with collection stats, or None if skipped
    """
    from ..external_analysis.vmalert_rule_state_artifact import (
        collect_vmalert_rule_state,
        write_vmalert_rule_state,
    )

    _log(
        "vmalert-rule-state",
        "DEBUG",
        "vmalert rule state collection started",
        run_id=run_id,
        cluster_label=cluster_label,
    )

    # Handle missing inventory
    if inventory is None:
        _log(
            "vmalert-rule-state",
            "DEBUG",
            "vmalert inventory not available (discovery may have failed)",
            run_id=run_id,
        )
        return None

    # Check for eligible sources
    eligible_count = sum(
        1 for s in inventory.sources.values()
        if s.state.value in ("discovered", "auto-tracked", "manual", "discovered-but-unverified")
    )
    if eligible_count == 0:
        _log(
            "vmalert-rule-state",
            "DEBUG",
            "vmalert rule state collection skipped: no eligible sources",
            run_id=run_id,
            source_count=len(inventory.sources),
        )
        return None

    _log(
        "vmalert-rule-state",
        "DEBUG",
        "Starting vmalert rule state collection",
        run_id=run_id,
        eligible_sources=eligible_count,
    )

    # Collect rule state from all eligible sources
    artifact = collect_vmalert_rule_state(
        inventory=inventory,
        timeout_seconds=timeout_seconds,
    )

    _log(
        "vmalert-rule-state",
        "DEBUG",
        "vmalert rule state collection completed",
        run_id=run_id,
        fetched_sources=artifact.fetched_source_count,
        failed_sources=artifact.failed_source_count,
        firing_alerts=artifact.firing_alert_count,
        pending_alerts=artifact.pending_alert_count,
    )

    # Persist artifact
    try:
        artifact_path = write_vmalert_rule_state(
            directories["root"],
            artifact,
            run_id,
        )
        _log(
            "vmalert-rule-state",
            "INFO",
            "vmalert rule state artifact written",
            run_id=run_id,
            artifact_path=str(artifact_path),
            source_count=artifact.source_count,
            fetched_source_count=artifact.fetched_source_count,
            failed_source_count=artifact.failed_source_count,
            alert_count=len(artifact.alerts),
        )
    except FileExistsError:
        # Artifact already exists - this is fine (immutability contract)
        _log(
            "vmalert-rule-state",
            "DEBUG",
            "vmalert rule state artifact already exists",
            run_id=run_id,
        )
    # REVIEWED: Operational exception boundary for artifact write failures.
    # Catches: OSError (file I/O), RuntimeError (serialization), ValueError (validation).
    # Non-fatal: health loop continues regardless of artifact write failure.
    except (OSError, RuntimeError, ValueError) as exc:
        _log(
            "vmalert-rule-state",
            "WARNING",
            "Failed to write vmalert rule state artifact",
            run_id=run_id,
            error=str(exc),
        )

    return {
        "source_count": artifact.source_count,
        "fetched_source_count": artifact.fetched_source_count,
        "failed_source_count": artifact.failed_source_count,
        "alert_count": len(artifact.alerts),
        "firing_alert_count": artifact.firing_alert_count,
        "pending_alert_count": artifact.pending_alert_count,
        "critical_firing_count": artifact.critical_firing_count,
        "rule_group_count": len(artifact.rule_groups),
        "fetch_error_count": len(artifact.fetch_errors),
        "captured_at": artifact.captured_at,
    }
