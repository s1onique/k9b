"""Artifact-read responsibilities for the UI server.

This module contains artifact-read-specific handlers extracted from server_reads.py:
- Debug endpoint handlers for execution-state-bundle, execution-summary, and diagnostics-enabled
- Batch eligibility index validation helpers
- Promotions loading from ui-index.json with run_id validation
- External analysis file counting

Keep behavior exact: HTTP status codes, error messages, and security checks are
preserved from the original implementation.

Extraction rationale: These debug, promotions, and counting helpers are artifact-read
concerns that belong together as a cohesive group. They read diagnostic artifacts
and return structured data, making them a natural seam for extraction.
"""

from __future__ import annotations

import json
import logging
import os
import re as regex_module
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

from ..security.path_validation import SecurityError, safe_run_artifact_glob, validate_run_id

logger = logging.getLogger(__name__)


__all__ = [
    "_count_external_analysis_files",
    "_handle_debug_routes",
    "_has_batch_eligibility_index",
    "_load_promotions_for_run",
]


def _has_batch_eligibility_index(ui_index_path: Path) -> bool:
    """Check if ui-index.json has v2+ with batch eligibility fields.

    This is a cheap validator to ensure the index is usable for the
    batch eligibility fast path before using its mtime for cache freshness.

    Args:
        ui_index_path: Path to ui-index.json

    Returns:
        True if the index has version >= 2 and entries have batch eligibility fields
    """
    try:
        raw_index = json.loads(ui_index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False

    recent_summary = raw_index.get("recent_runs_summary")
    if not isinstance(recent_summary, dict):
        return False

    if recent_summary.get("version", 1) < 2:
        return False

    runs = recent_summary.get("runs")
    if not isinstance(runs, list):
        return False

    if not runs:
        # Empty runs list is valid - just means no runs yet
        return True

    first = runs[0]
    return isinstance(first, dict) and "batchEligibility" in first and "batchExecutable" in first and "batchEligibleCount" in first


def _handle_debug_routes(handler: HealthUIRequestHandler, route: str) -> bool:
    """Handle debug endpoint routes that read diagnostic artifacts.

    This function handles the following routes:
    - GET /api/debug/runs/{run_id}/execution-state-bundle
    - GET /api/debug/runs/{run_id}/execution-summary
    - GET /api/debug/diagnostics-enabled

    Debug endpoints are only enabled when K9B_ENABLE_DEBUG_ENDPOINTS=true.

    Args:
        handler: The HealthUIRequestHandler instance
        route: The request path

    Returns:
        True if the route was handled (response sent), False if not matched
    """
    # Debug endpoint: /api/debug/runs/{run_id}/execution-summary
    # Only enabled when K9B_ENABLE_DEBUG_ENDPOINTS=true
    if route.startswith("/api/debug/runs/"):
        if os.environ.get("K9B_ENABLE_DEBUG_ENDPOINTS", "false").lower() != "true":
            handler._send_json({"error": "Debug endpoints disabled - set K9B_ENABLE_DEBUG_ENDPOINTS=true to enable"})
            return True

        # Match execution-state-bundle endpoint
        bundle_match = regex_module.match(r"^/api/debug/runs/([^/]+)/execution-state-bundle$", route)
        if bundle_match:
            run_id = bundle_match.group(1)
            health_root = handler.runs_dir / "health"
            from .api_debug import build_execution_state_bundle

            try:
                validate_run_id(run_id)
            except SecurityError:
                handler._send_json({"error": "Invalid run_id format"})
                return True

            bundle_bytes = build_execution_state_bundle(run_id, health_root)
            if bundle_bytes is None:
                handler._send_json({"error": "Debug diagnostics disabled"})
                return True

            # Send ZIP response (only call _send_bytes - it sets status internally)
            handler._send_bytes(
                bundle_bytes,
                content_type="application/zip",
                filename=f"k9b-execution-state-diagnostics-{run_id}.zip",
            )
            return True

        # Match execution-summary endpoint
        match = regex_module.match(r"^/api/debug/runs/([^/]+)/execution-summary$", route)
        if match:
            run_id = match.group(1)
            health_root = handler.runs_dir / "health"
            from .api_debug import build_execution_summary_diagnostics

            diagnostic = build_execution_summary_diagnostics(run_id, health_root, debug_flag=True)
            if diagnostic:
                handler._send_json(diagnostic)
            else:
                handler._send_json({"error": "Diagnostics disabled"})
            return True

        # Unknown /api/debug/runs/* route - not handled by this function
        return False

    # Debug diagnostics enabled flag: GET /api/debug/diagnostics-enabled
    if route == "/api/debug/diagnostics-enabled":
        from .api_debug import is_debug_diagnostics_enabled

        handler._send_json({
            "debugExecutionDiagnosticsEnabled": is_debug_diagnostics_enabled()
        })
        return True

    return False


def _load_ui_index_for_promotions(health_root: Path) -> tuple[dict[str, object] | None, str | None]:
    """Load ui-index.json with error handling for promotions loading.

    Args:
        health_root: Path to the health directory containing ui-index.json

    Returns:
        Tuple of (parsed ui-index.json contents or None, error reason or None).
        Error reasons are preserved for operator-visible diagnostics:
        - None: index loaded successfully
        - "missing_index": file does not exist
        - "index_load_error:<exc>": read/parse failed with exception
    """
    ui_index_path = health_root / "ui-index.json"
    if not ui_index_path.exists():
        return None, "missing_index"
    try:
        raw = json.loads(ui_index_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw, None
        return None, "invalid_index_shape"
    except Exception as exc:
        return None, f"index_load_error:{exc}"


def _load_promotions_for_run(
    health_root: Path,
    run_id: str,
) -> tuple[list[dict[str, object]], dict[str, Any]]:
    """Load promotions from ui-index.json with run_id validation.

    This function reads the promotions_index from ui-index.json and validates
    that it belongs to the requested run to prevent cross-run data leakage.

    Args:
        health_root: Path to the health directory containing ui-index.json
        run_id: The run ID to validate against

    Returns:
        Tuple of (promotions list, timings dict with load metrics)
    """
    timings: dict[str, Any] = {}
    timings["promoted_glob_ms"] = 0.0
    timings["promotion_glob_count"] = 0

    # Load promotions from ui-index.json with run_id validation
    promotions_index: Mapping[str, object] | None = None
    promotions_source = "file_scan"
    promotions_index_run_id: str | None = None
    promotions_fallback_reason: str | None = None

    index, index_load_error = _load_ui_index_for_promotions(health_root)
    if index is not None:
        raw_promotions_index = index.get("promotions_index")
        if isinstance(raw_promotions_index, Mapping):
            # Validate shape - must have run_id field for run-scoped correctness
            if "run_id" not in raw_promotions_index:
                promotions_fallback_reason = "missing_run_id_field"
            else:
                promotions_index = raw_promotions_index
                promotions_index_run_id = str(raw_promotions_index.get("run_id") or "")
                # CRITICAL: Validate run_id matches selected run to prevent cross-run data leakage
                if promotions_index_run_id != run_id:
                    promotions_fallback_reason = f"run_id_mismatch:{promotions_index_run_id}!={run_id}"
                    promotions_index = None
                elif not isinstance(raw_promotions_index.get("promotions"), list):
                    promotions_fallback_reason = "invalid_promotions_shape"
                    promotions_index = None
    else:
        # Use the specific error from _load_ui_index_for_promotions
        # This preserves the original server_reads.py behavior for malformed indices
        # "missing_index", "invalid_index_shape", or "index_load_error:<exc>"
        promotions_fallback_reason = index_load_error or "missing_index"

    if promotions_index is not None:
        # Use index-backed promotions (instant)
        raw_promotions = promotions_index.get("promotions", [])
        promotions = list(cast(list[dict[str, object]], raw_promotions)) if isinstance(raw_promotions, list) else []
        promotions_source = "index"
    else:
        # CRITICAL: Do NOT probe external-analysis when index is missing/mismatched
        # Even bounded iterdir() costs 1.5-2.7s on large directories, which blocks /api/run
        # Return empty promotions with explicit reason so operator can regenerate index
        if promotions_fallback_reason is None:
            promotions_fallback_reason = "missing_promotions_index"

        promotions = []
        promotions_source = "skipped_missing_index"

    timings["promotions_count"] = len(promotions)
    timings["promotions_source"] = promotions_source
    timings["promotions_index_run_id"] = promotions_index_run_id or ""
    if promotions_fallback_reason:
        timings["promotions_fallback_reason"] = promotions_fallback_reason

    return promotions, timings


def _count_external_analysis_files(
    health_root: Path,
    run_id: str,
) -> int:
    """Count external analysis files for a run (fast glob only, no load).

    SECURITY: run_id is validated by validate_run_id() before glob construction.

    Args:
        health_root: Path to the health directory containing external-analysis
        run_id: The run ID to count files for

    Returns:
        Number of external analysis files for this run
    """
    external_analysis_dir = health_root / "external-analysis"
    if not external_analysis_dir.exists():
        return 0

    try:
        validated_run_id = validate_run_id(run_id)
        glob_pattern = safe_run_artifact_glob(validated_run_id, "-*.json")
        return len(list(external_analysis_dir.glob(glob_pattern)))
    except SecurityError:
        # Safe fallback: return 0 on invalid run_id
        return 0


