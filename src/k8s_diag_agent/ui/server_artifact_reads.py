"""Artifact-read responsibilities for the UI server.

This module contains artifact-read-specific handlers extracted from server_reads.py:
- Debug endpoint handlers for execution-state-bundle, execution-summary, and diagnostics-enabled
- Batch eligibility index validation helpers

Keep behavior exact: HTTP status codes, error messages, and security checks are
preserved from the original implementation.

Extraction rationale: These debug and batch-eligibility helpers are artifact-read
concerns that belong together as a cohesive group. They read diagnostic artifacts
and return structured data, making them a natural seam for extraction.
"""

from __future__ import annotations

import json
import logging
import os
import re as regex_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

from ..security.path_validation import SecurityError, validate_run_id

logger = logging.getLogger(__name__)


__all__ = [
    "_handle_debug_routes",
    "_has_batch_eligibility_index",
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