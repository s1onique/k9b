"""Source artifact loading helpers for server context.

This module contains Alertmanager/vmalert source artifact loading functions
extracted from server_context.py. These functions load compact and source
inventories for the UI context.

Extraction: Alertmanager/vmalert source loading moved from server_context.py
to keep the parent module below the 500-line threshold.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from pathlib import Path


def load_context_sources(
    health_root: Path,
    run_id: str,
    _timings: dict[str, float | str],
    _phase: Any,
) -> dict[str, Any]:
    """Load Alertmanager/vmalert source artifacts for a run context.

    This function loads compact, sources, and rule state artifacts
    from the health_root directory for the UI context.

    Args:
        health_root: Path to the health directory (runs/health/)
        run_id: The run ID to load artifacts for
        _timings: Timing dict to update
        _phase: Phase timing helper function

    Returns:
        Dict with keys: alertmanager_compact_entry, alertmanager_sources_entry,
        vmalert_sources_entry, vmalert_rule_state_entry, and timing keys.
    """
    result: dict[str, Any] = {
        "alertmanager_compact_entry": None,
        "alertmanager_sources_entry": None,
        "vmalert_sources_entry": None,
        "vmalert_rule_state_entry": None,
    }

    # Phase 14: Load Alertmanager compact artifact if available
    # Alertmanager artifacts are written at health_root, not external-analysis/
    compact_path = health_root / f"{run_id}-alertmanager-compact.json"
    if compact_path.exists():
        try:
            compact_raw = _phase(
                "alertmanager_compact_read_ms",
                lambda: json.loads(compact_path.read_text(encoding="utf-8")),
            )
            result["alertmanager_compact_entry"] = {
                "status": compact_raw.get("status"),
                "alert_count": compact_raw.get("alert_count", 0),
                "severity_counts": compact_raw.get("severity_counts", {}),
                "state_counts": compact_raw.get("state_counts", {}),
                "top_alert_names": compact_raw.get("top_alert_names", []),
                "affected_namespaces": compact_raw.get("affected_namespaces", []),
                "affected_clusters": compact_raw.get("affected_clusters", []),
                "affected_services": compact_raw.get("affected_services", []),
                "truncated": compact_raw.get("truncated", False),
                "captured_at": compact_raw.get("captured_at"),
                # Per-cluster breakdown for cluster-scoped UI panels
                "by_cluster": compact_raw.get("by_cluster", []),
            }
        except (OSError, json.JSONDecodeError):
            _timings["alertmanager_compact_read_ms"] = 0.0
            pass  # Compact not available - non-fatal
    else:
        _timings["alertmanager_compact_read_ms"] = 0.0

    # Phase 15: Load Alertmanager sources inventory if available
    # Uses _serialize_alertmanager_sources from health/ui.py to apply operator overrides
    # Alertmanager artifacts are written at health_root, not external-analysis/
    sources_path = health_root / f"{run_id}-alertmanager-sources.json"
    if sources_path.exists():
        # Import here to avoid circular import at module level
        from ..health.ui import _serialize_alertmanager_sources as _serialize_am_sources

        try:
            result["alertmanager_sources_entry"] = cast(
                dict[str, object] | None,
                _phase(
                    "alertmanager_sources_build_ms",
                    lambda: _serialize_am_sources(health_root, run_id),
                ),
            )
        except (OSError, json.JSONDecodeError, ValueError, KeyError):
            _timings["alertmanager_sources_build_ms"] = 0.0
            pass  # Sources not available - non-fatal
    else:
        _timings["alertmanager_sources_build_ms"] = 0.0

    # Phase 15b: Load vmalert sources inventory if available
    # vmalert artifacts are written at health_root, not external-analysis/
    vmalert_sources_path = health_root / f"{run_id}-vmalert-sources.json"
    if vmalert_sources_path.exists():
        # Import here to avoid circular import at module level
        from ..health.ui import _serialize_vmalert_sources

        try:
            result["vmalert_sources_entry"] = cast(
                dict[str, object] | None,
                _phase(
                    "vmalert_sources_build_ms",
                    lambda: _serialize_vmalert_sources(health_root, run_id),
                ),
            )
        except (OSError, json.JSONDecodeError, ValueError, KeyError):
            _timings["vmalert_sources_build_ms"] = 0.0
            pass  # Sources not available - non-fatal
    else:
        _timings["vmalert_sources_build_ms"] = 0.0

    # Phase 15c: Load vmalert rule state artifact if available
    # vmalert rule state artifact is written at health_root, not external-analysis/
    vmalert_rule_state_path = health_root / f"{run_id}-vmalert-rule-state.json"
    if vmalert_rule_state_path.exists():
        try:
            result["vmalert_rule_state_entry"] = cast(
                dict[str, object],
                json.loads(vmalert_rule_state_path.read_text(encoding="utf-8")),
            )
        except (OSError, json.JSONDecodeError):
            _timings["vmalert_rule_state_read_ms"] = 0.0
            pass  # Rule state not available - non-fatal
    else:
        _timings["vmalert_rule_state_read_ms"] = 0.0

    return result
