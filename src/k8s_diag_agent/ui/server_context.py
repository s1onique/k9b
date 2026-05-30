"""Context loading helpers for the UI server.

This module contains context loading and UI-index building logic extracted
from server.py. It provides functions for loading run-specific context from
durable artifacts.

Extraction: _load_context and _load_context_for_run methods moved from
HealthUIRequestHandler in server.py. The thin wrapper method remains in
HealthUIRequestHandler for backward compatibility.

Keep behavior exact: no logic changes, no response shape changes.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from .model import UIIndexContext, build_ui_context, load_ui_index

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)


def load_request_context(
    handler: HealthUIRequestHandler,
    requested_run_id: str | None = None,
) -> UIIndexContext | None:
    """Load the UI context, optionally for a specific run.

    If requested_run_id is provided, try to load context from that run's review
    artifact. Otherwise, load from the ui-index.json (latest run).

    This is the top-level context loader that delegates to specialized functions
    based on whether a specific run is requested.

    Args:
        handler: The HealthUIRequestHandler instance with runs_dir and _health_root
        requested_run_id: Optional run ID to load. If None, loads latest run.

    Returns:
        UIIndexContext or None if loading fails.
    """
    # If a specific run is requested, try to build context from its review artifact
    if requested_run_id:
        context = load_context_for_run(handler, requested_run_id)
        if context is not None:
            return context
        # If the requested run doesn't exist, fall back to latest
        # Log a warning but don't fail - this provides explicit behavior
        logger.warning(
            "Requested run not found, falling back to latest",
            extra={"requested_run_id": requested_run_id},
        )

    # Default: load from ui-index.json (latest run)
    # NOTE: Do NOT log here - let the caller (HealthUIRequestHandler) decide how to
    # handle load failures. This preserves the original behavior where _load_context
    # did not log and returned None, allowing the test_access_log_emits_error_on_handler_exception
    # test to verify error path handling.
    try:
        # ui-index.json is written to runs/health/ by write_health_ui_index
        index = load_ui_index(handler.runs_dir / "health")
        return build_ui_context(index)
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError):
        # Do not log - caller handles the error response
        return None


def load_context_for_run(
    handler: HealthUIRequestHandler,
    run_id: str,
) -> UIIndexContext | None:
    """Load UI context for a specific run from its durable artifacts.

    This allows browsing non-latest runs by reading their artifacts
    and building the context from that specific run's data.

    Args:
        handler: The HealthUIRequestHandler instance with runs_dir and _health_root
        run_id: The run ID to load.

    Returns:
        UIIndexContext for the requested run, or None if not found.
    """
    # Phase timing instrumentation for cold /api/run diagnosis
    _timings: dict[str, float | str] = {}
    _total_start = time.perf_counter()

    def _phase(name: str, fn: Callable[[], object]) -> object:
        """Time a phase and return its result."""
        _t0 = time.perf_counter()
        result = fn()
        _timings[name] = (time.perf_counter() - _t0) * 1000
        return result

    # Import shared helpers here to avoid circular imports at module level
    from ..structured_logging import emit_structured_log
    from .server_read_support import (
        RunArtifactIndex,
        _build_clusters_and_drilldown_availability,
        _build_execution_history,
        _build_llm_stats_for_run,
        _build_proposal_status_summary,
        _build_queue_from_plan,
        _build_review_enrichment_status_for_past_run,
        _build_run_artifact_index,
        _count_run_artifacts,
        _find_next_check_plan,
        _find_review_enrichment,
        _load_proposals_for_run,
        _scan_external_analysis,
    )

    # Phase 1: Check if the run exists by looking for its review artifact
    reviews_dir = handler.runs_dir / "health" / "reviews"
    review_artifact_path = reviews_dir / f"{run_id}-review.json"

    if not review_artifact_path.exists():
        logger.debug(
            "Run review artifact not found",
            extra={"run_id": run_id, "path": str(review_artifact_path)},
        )
        return None

    _timings["review_artifact_read_ms"] = (time.perf_counter() - _total_start) * 1000

    try:
        review_data = json.loads(review_artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "Failed to read run review artifact",
            extra={"run_id": run_id, "error": str(exc)},
        )
        return None

    # Derive run metadata from review artifact
    run_label = review_data.get("run_label", run_id)
    timestamp = review_data.get("timestamp", datetime.now(UTC).isoformat())

    # Get cluster info from review's selected_drilldowns
    selected_drilldowns = review_data.get("selected_drilldowns", [])
    cluster_count = len(selected_drilldowns) if isinstance(selected_drilldowns, list) else 0

    # Extract proposal_status_summary from review artifact for fast loading
    # This avoids scanning the proposals/ directory on each /api/run request
    review_proposal_status_summary: dict[str, object] | None = review_data.get(
        "_proposal_status_summary"
    ) if isinstance(review_data, dict) else None

    # Phase 2+7: Build clusters and drilldown availability in single pass
    # OPTIMIZATION: Merged into one function that reads drilldown artifacts once
    # instead of two separate calls that each did their own glob+parse operations
    clusters_t0 = time.perf_counter()
    clusters, drilldown_availability = _build_clusters_and_drilldown_availability(
        run_id, review_data, handler.runs_dir
    )
    clusters_elapsed = (time.perf_counter() - clusters_t0) * 1000
    _timings["clusters_build_ms"] = round(clusters_elapsed, 2)
    _timings["drilldown_availability_build_ms"] = round(clusters_elapsed, 2)  # Combined timing

    # Phase 3: Scan for drilldowns belonging to this run
    drilldown_count = _phase(
        "drilldown_scan_ms",
        lambda: _count_run_artifacts(handler.runs_dir / "health" / "drilldowns", run_id),
    )

    # Phase 4: Load proposals (skip if _proposal_status_summary exists in review)
    # OPTIMIZATION: When review artifact has _proposal_status_summary, skip the
    # proposals/ directory scan. Full proposals_data is deferred - only summary
    # is needed for selected-run shell. Proposal detail panels can be lazy-loaded.
    if review_proposal_status_summary is not None:
        # Skip proposals scan - use summary metadata only
        proposals_data: list[dict[str, object]] = []
        # Derive proposal_count from status_counts if available
        status_counts = review_proposal_status_summary.get("status_counts", [])
        proposal_count = sum(item.get("count", 0) for item in status_counts if isinstance(item, dict))
        _timings["proposals_scan_ms"] = 0.0
        _timings["proposals_source"] = "summary_deferred"
    else:
        # Fall back to full proposals scan (backward compatibility)
        proposals_result = _phase(
            "proposals_scan_ms",
            lambda: _load_proposals_for_run(handler.runs_dir / "health" / "proposals", run_id),
        )
        proposals_data, proposal_count = cast(tuple[list[dict[str, object]], int], proposals_result)
        _timings["proposals_source"] = "directory_scan"

    # Phase 5: Scan for external-analysis artifacts for this run
    external_analysis_dir = handler._health_root / "external-analysis"
    external_analysis_data = _phase(
        "external_analysis_scan_ms",
        lambda: _scan_external_analysis(external_analysis_dir, run_id),
    )
    external_analysis_count = external_analysis_data.get("count", 0)

    # Phase 6: Load notifications for this run (index-backed, no directory scan)
    # OPTIMIZATION: Past runs should not scan the full notifications directory.
    # Use ui-index.json notification_index if available, otherwise defer.
    notification_t0 = time.perf_counter()
    notification_history: list[dict[str, object]] = []
    notification_count = 0
    notifications_source = "deferred"
    notification_index_available = False
    notification_history_complete = True  # Assume complete unless bounded
    notification_records_used = 0

    try:
        from .server_reads import _get_llm_activity_from_index
        from .server_reads import _load_ui_index_file as _load_index

        index = _load_index(handler._health_root)
        notif_index = index.get("notification_index")
        if isinstance(notif_index, dict):
            notification_index_available = True
            all_notifs = notif_index.get("notifications", [])
            if isinstance(all_notifs, list):
                # Filter by runId field if present (runId not run_id in index)
                run_id_field = "runId"  # notification_index uses runId
                filtered = [n for n in all_notifs if isinstance(n, dict) and n.get(run_id_field) == run_id]
                notification_records_used = len(filtered)
                notification_count = notification_records_used
                # Bound to latest 20 per run to keep payload small
                notification_history = cast(list[dict[str, object]], filtered[:20])
                # Mark as incomplete if we had more than 20 and truncated
                notification_history_complete = len(filtered) <= 20
                notifications_source = "index"
    except (OSError, json.JSONDecodeError, ValueError, KeyError):
        # Malformed index - defer notification loading
        notifications_source = "deferred"

    _timings["notifications_scan_ms"] = (time.perf_counter() - notification_t0) * 1000
    _timings["notifications_source"] = notifications_source
    _timings["notification_index_available"] = notification_index_available

    # Phase 8: Build per-run artifact index ONCE for reuse across multiple lookups
    # NOTE: clusters and drilldown_availability were already built in Phase 2+7 above
    # This replaces repeated directory scans with a single bounded scan by run_id prefix
    raw_artifact_index = _phase(
        "artifact_index_build_ms",
        lambda: _build_run_artifact_index(external_analysis_dir, run_id),
    )
    artifact_index = cast("RunArtifactIndex | None", raw_artifact_index)

    # Phase 9: Find review enrichment artifact (uses shared index)
    review_enrichment = _phase(
        "review_enrichment_lookup_ms",
        lambda: _find_review_enrichment(external_analysis_dir, run_id, artifact_index),
    )

    # Phase 9: Build review_enrichment_status for past runs.
    # For past runs, we derive status from the enrichment artifact and
    # the review artifact's config metadata, independent of current policy.
    has_enrichment_artifact = review_enrichment is not None
    review_enrichment_status: dict[str, object] | None = None

    if not has_enrichment_artifact:
        # Derive status from run config in review artifact.
        # Use the dedicated helper that only checks run-level config,
        # not current policy (which may have changed since the run).
        external_analysis_config = review_data.get("external_analysis_settings")
        run_config: dict[str, object] | None = None
        if isinstance(external_analysis_config, dict):
            candidate = external_analysis_config.get("review_enrichment")
            # Guard against malformed nested config (e.g., "review_enrichment": "bogus")
            if isinstance(candidate, dict):
                run_config = candidate

        review_enrichment_status = cast(
            dict[str, object],
            _phase(
                "review_enrichment_status_build_ms",
                lambda: _build_review_enrichment_status_for_past_run(run_config),
            ),
        )

    # Phase 10: Find next-check plan artifact (uses shared index)
    next_check_plan = cast(
        dict[str, object] | None,
        _phase(
            "next_check_plan_lookup_ms",
            lambda: _find_next_check_plan(external_analysis_dir, run_id, artifact_index),
        ),
    )

    # Phase 11: Build next_check_queue from plan if exists
    next_check_queue: list[dict[str, object]] = cast(
        list[dict[str, object]],
        _phase("next_check_queue_build_ms", lambda: _build_queue_from_plan(next_check_plan)),
    )

    # Phase 12: Build next_check_execution_history (uses shared index)
    execution_history: list[dict[str, object]]
    exec_result = _phase(
        "execution_history_build_ms",
        lambda: _build_execution_history(external_analysis_dir, run_id, artifact_index),
    )
    execution_history, exec_telemetry = cast(
        tuple[list[dict[str, object]], dict[str, object]],
        exec_result,
    )

    # Phase 13: Build llm_stats from external-analysis artifacts for this run (uses shared index)
    llm_stats = _phase(
        "llm_stats_build_ms",
        lambda: _build_llm_stats_for_run(external_analysis_dir, run_id, artifact_index),
    )

    # Phase 14-15c: Load Alertmanager/vmalert source artifacts
    # Extracted to server_context_sources.py to keep this module below 500 lines
    from .server_context_sources import load_context_sources

    source_results = load_context_sources(handler._health_root, run_id, _timings, _phase)
    alertmanager_compact_entry = source_results["alertmanager_compact_entry"]
    alertmanager_sources_entry = source_results["alertmanager_sources_entry"]
    vmalert_sources_entry = source_results["vmalert_sources_entry"]
    vmalert_rule_state_entry = source_results["vmalert_rule_state_entry"]

    # Phase 16: Build run entry with artifact-backed values
    run_entry: dict[str, object] = {
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
        "historical_llm_stats": None,  # Historical stats are retained globally, not per-run
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
        "vmalert_rule_state": vmalert_rule_state_entry,
    }

    # Phase 17: Build proposal status summary
    # OPTIMIZATION: Use pre-computed summary from review artifact when available
    # This avoids scanning the proposals/ directory and iterating all proposals
    if review_proposal_status_summary is not None:
        proposal_status_summary = review_proposal_status_summary
        _timings["proposal_status_summary_build_ms"] = 0.0
        _timings["proposal_status_summary_source"] = "review_artifact"
    else:
        # Fall back to building from loaded proposals (backward compatibility)
        proposal_status_summary = cast(
            dict[str, object],
            _phase(
                "proposal_status_summary_build_ms",
                lambda: _build_proposal_status_summary(proposals_data),
            ),
        )
        _timings["proposal_status_summary_source"] = "built_from_proposals"

    # Phase 18: Build UI index structure
    run_index: dict[str, object] = {
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

    # Phase 19: Build UIIndexContext
    _timings["build_ui_context_ms"] = (time.perf_counter() - _total_start) * 1000  # reset after build
    _ctx_start = time.perf_counter()
    try:
        ctx = build_ui_context(run_index)
        _timings["build_ui_context_ms"] = (time.perf_counter() - _ctx_start) * 1000
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "Failed to build context for run",
            extra={"run_id": run_id, "error": str(exc)},
        )
        return None

    # Total context load timing
    _timings["total_ms"] = (time.perf_counter() - _total_start) * 1000

    # Emit structured timing log with all phases
    emit_structured_log(
        component="ui-run-context",
        message="/api/run _load_context_for_run phase timings",
        run_id=run_id,
        run_label=run_label,
        severity="INFO",
        metadata={
            "total_ms": round(cast(float, _timings.get("total_ms", 0.0)), 2),
            "review_artifact_read_ms": round(cast(float, _timings.get("review_artifact_read_ms", 0.0)), 2),
            "clusters_build_ms": round(cast(float, _timings.get("clusters_build_ms", 0.0)), 2),
            "drilldown_scan_ms": round(cast(float, _timings.get("drilldown_scan_ms", 0.0)), 2),
            "proposals_scan_ms": round(cast(float, _timings.get("proposals_scan_ms", 0.0)), 2),
            "external_analysis_scan_ms": round(cast(float, _timings.get("external_analysis_scan_ms", 0.0)), 2),
            "notifications_scan_ms": round(cast(float, _timings.get("notifications_scan_ms", 0.0)), 2),
            "drilldown_availability_build_ms": round(cast(float, _timings.get("drilldown_availability_build_ms", 0.0)), 2),
            "review_enrichment_lookup_ms": round(cast(float, _timings.get("review_enrichment_lookup_ms", 0.0)), 2),
            "review_enrichment_status_build_ms": round(cast(float, _timings.get("review_enrichment_status_build_ms", 0.0)), 2),
            "next_check_plan_lookup_ms": round(cast(float, _timings.get("next_check_plan_lookup_ms", 0.0)), 2),
            "next_check_queue_build_ms": round(cast(float, _timings.get("next_check_queue_build_ms", 0.0)), 2),
            "execution_history_build_ms": round(cast(float, _timings.get("execution_history_build_ms", 0.0)), 2),
            "llm_stats_build_ms": round(cast(float, _timings.get("llm_stats_build_ms", 0.0)), 2),
            "alertmanager_compact_read_ms": round(cast(float, _timings.get("alertmanager_compact_read_ms", 0.0)), 2),
            "alertmanager_sources_build_ms": round(cast(float, _timings.get("alertmanager_sources_build_ms", 0.0)), 2),
            "vmalert_sources_build_ms": round(cast(float, _timings.get("vmalert_sources_build_ms", 0.0)), 2),
            "proposal_status_summary_build_ms": round(cast(float, _timings.get("proposal_status_summary_build_ms", 0.0)), 2),
            "build_ui_context_ms": round(cast(float, _timings.get("build_ui_context_ms", 0.0)), 2),
            "proposals_source": cast(str, _timings.get("proposals_source", "missing")),
            "proposal_status_summary_source": cast(str, _timings.get("proposal_status_summary_source", "missing")),
            "run_id": run_id,
            "run_label": run_label,
            "cluster_count": cluster_count,
            "drilldown_count": drilldown_count,
            "proposal_count": proposal_count,
            "external_analysis_count": external_analysis_count,
            "notification_count": notification_count,
            # Notification loading telemetry
            "notifications_source": notifications_source,
            "notification_index_available": notification_index_available,
            "notification_records_used": notification_records_used,
            "notification_history_complete": notification_history_complete,
        },
    )

    return ctx
