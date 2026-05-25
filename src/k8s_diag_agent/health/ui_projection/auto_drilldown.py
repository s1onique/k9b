"""Auto-drilldown serialization projection for health UI.

Extracted from health/ui.py to provide a focused module for auto-drilldown concerns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ...external_analysis.artifact import ExternalAnalysisPurpose
from ...external_analysis.config import AutoDrilldownPolicy
from ..ui_shared import _relative_path


def _serialize_auto_drilldown_policy(policy: AutoDrilldownPolicy) -> dict[str, object]:
    """Serialize auto-drilldown policy to dict for UI consumption."""
    provider = (policy.provider or "").strip()
    return {
        "enabled": policy.enabled,
        "provider": provider or None,
        "maxPerRun": policy.max_per_run,
    }


def _serialize_auto_drilldown_interpretations(
    artifacts: object | None,
    root_dir: Path,
) -> dict[str, dict[str, object]]:
    """Serialize auto-drilldown interpretations for UI consumption."""
    interpretations: dict[str, dict[str, object]] = {}
    if not isinstance(artifacts, Sequence):
        return interpretations
    seen: set[str] = set()
    for entry in artifacts:
        if not isinstance(entry, Mapping):
            continue
        if entry.get("purpose") != ExternalAnalysisPurpose.AUTO_DRILLDOWN.value:
            continue
        cluster_label = str(entry.get("cluster_label") or "").strip()
        if not cluster_label or cluster_label in seen:
            continue
        seen.add(cluster_label)
        interpretations[cluster_label] = {
            "adapter": str(entry.get("tool_name") or ""),
            "status": str(entry.get("status") or ""),
            "summary": entry.get("summary"),
            "timestamp": str(entry.get("timestamp") or ""),
            "artifact_path": _relative_path(root_dir, entry.get("artifact_path")),
            "provider": entry.get("provider"),
            "duration_ms": entry.get("duration_ms"),
            "payload": entry.get("payload"),
            "error_summary": entry.get("error_summary"),
            "skip_reason": entry.get("skip_reason"),
        }
    return interpretations


__all__ = [
    "_serialize_auto_drilldown_interpretations",
    "_serialize_auto_drilldown_policy",
]
