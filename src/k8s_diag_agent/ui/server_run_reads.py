"""Run-scoped read handlers for the UI server.

This module contains run-specific context loading extracted from server_reads.py.
Functions here handle loading UI context for specific runs by reading their
durable artifacts.

Extraction rational: load_context_for_run is called for non-latest runs and
browsing historical run data. This is a distinct responsibility from the
main dispatcher in server_reads.py.

Keep behavior exact: response shapes, error codes, and cache behavior are
preserved from the original implementation.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)


def _get_llm_activity_from_index(health_root: Path, run_id: str) -> dict[str, object]:
    """Load llm_activity data from ui-index.json for a specific run.

    This is used by load_context_for_run to get the deanonymized historical
    LLM activity entries from the index, which are already processed with
    the correct alias_mapping during index regeneration.

    Falls back to empty entries if ui-index.json doesn't exist or the
    run_id doesn't match.

    Args:
        health_root: Path to the health directory containing ui-index.json
        run_id: The run ID to look for

    Returns:
        A dict with 'entries' and 'summary' keys, or empty fallback
    """
    default: dict[str, object] = {"entries": [], "summary": {"retainedEntries": 0}}
    try:
        index = _load_ui_index_file(health_root)
        ui_run = index.get("run", {})
        if isinstance(ui_run, dict) and str(ui_run.get("run_id") or "") == run_id:
            la = ui_run.get("llm_activity")
            if isinstance(la, dict):
                return la
    except (OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
        # Catch expected local failures: missing/malformed file, unexpected structure.
        # Do NOT catch unrelated programmer errors (e.g. AttributeError, NameError).
        pass
    return default


def _load_ui_index_file(health_root: Path) -> dict[str, object]:
    """Load ui-index.json from health root directory.

    This is a local helper to avoid importing load_ui_index from ui.model,
    which would create a circular import back into ui.server_reads.

    Args:
        health_root: Path to the health directory containing ui-index.json

    Returns:
        The parsed ui-index.json contents as a dict

    Raises:
        FileNotFoundError: If ui-index.json doesn't exist
        json.JSONDecodeError: If the file contains invalid JSON
    """
    index_path = health_root / "ui-index.json"
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        return cast(dict[str, object], raw)
    # If not a dict (edge case), return empty dict
    return {}


def load_context_for_run(handler: HealthUIRequestHandler, run_id: str) -> Any:
    """Load UI context for a specific run from its durable artifacts.

    This allows browsing non-latest runs by reading their artifacts
    and building the context from that specific run's data.

    Args:
        handler: The HealthUIRequestHandler instance
        run_id: The run ID to load

    Returns:
        UIIndexContext for the requested run, or None if not found.
    """
    from .model import build_ui_context
    from .server_read_support import (
        _build_clusters_from_review,
        _build_drilldown_availability_from_review,
        _build_execution_history,
        _build_llm_stats_for_run,
        _build_proposal_status_summary,
        _build_queue_from_plan,
        _build_review_enrichment_status_for_past_run,
        _count_run_artifacts,
        _find_next_check_plan,
        _find_review_enrichment,
        _load_notifications_for_run,
        _load_proposals_for_run,
        _scan_external_analysis,
    )

    reviews_dir = handler.runs_dir / "health" / "reviews"
    review_artifact_path = reviews_dir / f"{run_id}-review.json"

    if not review_artifact_path.exists():
        logger.debug(
            "Run review artifact not found",
            extra={"run_id": run_id, "path": str(review_artifact_path)},
        )
        return None

    try:
        review_data = json.loads(review_artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Failed to read run review artifact",
            extra={"run_id": run_id, "error": str(exc)},
        )
        return None

    run_label = review_data.get("run_label", run_id)
    timestamp = review_data.get("timestamp", datetime.now(UTC).isoformat())

    selected_drilldowns = review_data.get("selected_drilldowns", [])
    cluster_count = len(selected_drilldowns) if isinstance(selected_drilldowns, list) else 0

    clusters = _build_clusters_from_review(run_id, review_data, handler.runs_dir)

    drilldown_count = _count_run_artifacts(handler.runs_dir / "health" / "drilldowns", run_id)

    proposals_data, proposal_count = _load_proposals_for_run(handler.runs_dir / "health" / "proposals", run_id)

    external_analysis_dir = handler._health_root / "external-analysis"
    external_analysis_data = _scan_external_analysis(external_analysis_dir, run_id)
    external_analysis_count = external_analysis_data.get("count", 0)

    notification_history, notification_count = _load_notifications_for_run(handler.runs_dir / "health" / "notifications", run_id)

    drilldown_availability = _build_drilldown_availability_from_review(review_data, handler.runs_dir / "health" / "drilldowns", run_id)

    review_enrichment = _find_review_enrichment(external_analysis_dir, run_id)

    has_enrichment_artifact = review_enrichment is not None
    review_enrichment_status: dict[str, object] | None = None

    if not has_enrichment_artifact:
        external_analysis_config = review_data.get("external_analysis_settings")
        run_config: dict[str, object] | None = None
        if isinstance(external_analysis_config, dict):
            candidate = external_analysis_config.get("review_enrichment")
            if isinstance(candidate, dict):
                run_config = candidate

        review_enrichment_status = _build_review_enrichment_status_for_past_run(run_config)

    next_check_plan = _find_next_check_plan(external_analysis_dir, run_id)

    next_check_queue = _build_queue_from_plan(next_check_plan)

    execution_history, _ = _build_execution_history(external_analysis_dir, run_id)

    llm_stats = _build_llm_stats_for_run(external_analysis_dir, run_id)

    alertmanager_compact_entry = None
    compact_path = handler._health_root / f"{run_id}-alertmanager-compact.json"
    if compact_path.exists():
        try:
            compact_raw = json.loads(compact_path.read_text(encoding="utf-8"))
            alertmanager_compact_entry = {
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
                "by_cluster": compact_raw.get("by_cluster", []),
            }
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    alertmanager_sources_entry = None
    sources_path = handler._health_root / f"{run_id}-alertmanager-sources.json"
    if sources_path.exists():
        from ..health.ui import _serialize_alertmanager_sources as _serialize_am_sources

        try:
            alertmanager_sources_entry = _serialize_am_sources(handler._health_root, run_id)
        except (OSError, json.JSONDecodeError, ValueError, KeyError):
            pass

    vmalert_sources_entry = None
    vmalert_sources_path = handler._health_root / f"{run_id}-vmalert-sources.json"
    if vmalert_sources_path.exists():
        from ..health.ui import _serialize_vmalert_sources

        try:
            vmalert_sources_entry = _serialize_vmalert_sources(handler._health_root, run_id)
        except (OSError, json.JSONDecodeError, ValueError, KeyError):
            pass

    run_entry = {
        "run_id": run_id,
        "run_label": run_label,
        "timestamp": timestamp,
        "collector_version": review_data.get("collector_version", "0.0.0"),
        "cluster_count": cluster_count,
        "drilldown_count": drilldown_count,
        "proposal_count": proposal_count,
        "external_analysis_count": external_analysis_count,
        "notification_count": notification_count,
        "llm_stats": llm_stats,
        "historical_llm_stats": None,
        # Load llm_activity from ui-index.json (contains deanonymized historical entries)
        # Fall back to empty if ui-index.json doesn't exist or has no llm_activity for this run
        "llm_activity": _get_llm_activity_from_index(handler._health_root, run_id),
        "llm_policy": None,
        "review_enrichment": review_enrichment,
        "review_enrichment_status": review_enrichment_status,
        "provider_execution": None,
        "next_check_plan": next_check_plan,
        "next_check_queue": next_check_queue,
        "next_check_queue_explanation": None,
        "next_check_execution_history": execution_history,
        "deterministic_next_checks": None,
        "planner_availability": None,
        "diagnostic_pack_review": None,
        "diagnostic_pack": None,
        "alertmanager_compact": alertmanager_compact_entry,
        "alertmanager_sources": alertmanager_sources_entry,
        "vmalert_sources": vmalert_sources_entry,
    }

    proposal_status_summary = _build_proposal_status_summary(proposals_data)

    index: dict[str, object] = {
        "run": run_entry,
        "clusters": clusters,
        "latest_assessment": None,
        "latest_findings": None,
        "proposals": proposals_data,
        "proposal_status_summary": proposal_status_summary,
        "notification_history": notification_history,
        "drilldown_availability": drilldown_availability,
        "run_stats": {"total_runs": 0},
        "auto_drilldown_interpretations": {},
        "external_analysis": external_analysis_data,
    }

    try:
        return build_ui_context(index)
    except Exception as exc:
        logger.warning(
            "Failed to build context for run",
            extra={"run_id": run_id, "error": str(exc)},
        )
        return None
