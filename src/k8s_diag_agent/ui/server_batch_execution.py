"""Batch execution handler for the UI server.

This module contains the batch execution handler extracted from server.py.
It handles POST /api/run-batch-next-check-execution requests.

Keep behavior exact: dry-run parsing, error messages, status codes, and
post-execution side effects (pack refresh, cache invalidation) are preserved.

Imports:
- HealthUIRequestHandler type from .server (TYPE_CHECKING) for type hints
- _validate_json_mutation_request from .server_shared for request validation
- _refresh_diagnostic_pack_latest, _persist_batch_execution_history_to_ui_index,
  and _invalidate_runs_list_cache from .server_execution_side_effects for post-execution side effects
- run_batch_next_checks from k8s_diag_agent.batch for actual execution
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import HealthUIRequestHandler

logger = logging.getLogger(__name__)

__all__ = [
    "handle_run_batch_next_check_execution",
]


def handle_run_batch_next_check_execution(handler: HealthUIRequestHandler) -> None:
    """Handle batch execution of next-check candidates for a specific run.

    Accepts run_id in the payload and executes all eligible candidates
    that haven't been executed yet.

    Args:
        handler: The HealthUIRequestHandler instance
    """
    from ..structured_logging import emit_structured_log
    from .server_execution_side_effects import (
        _invalidate_runs_list_cache,
        _persist_batch_execution_history_to_ui_index,
        _refresh_diagnostic_pack_latest,
    )
    from .server_shared import _validate_json_mutation_request

    # Validate Content-Type and request size, parse JSON body
    payload = _validate_json_mutation_request(handler)
    if payload is None:
        return

    run_id = payload.get("runId")
    if not isinstance(run_id, str) or not run_id:
        handler._send_json({"error": "runId is required"}, 400)
        return

    # Default to False (actual execution) - UI Execute button should send dryRun: false
    # Preview/dry-run can be triggered by explicitly sending dryRun: true
    # Handle both boolean and string values - JSON.stringify converts boolean to "true"/"false" strings
    dry_run_raw = payload.get("dryRun", False)
    if isinstance(dry_run_raw, bool):
        dry_run = dry_run_raw
    elif isinstance(dry_run_raw, str):
        # Handle string "true"/"false" from JSON.stringify (converts boolean to string)
        dry_run = dry_run_raw.lower() == "true"
    else:
        dry_run = bool(dry_run_raw)

    # Log the parsed dry_run value for observability
    emit_structured_log(
        component="batch-execution",
        message="Batch execution request parsed",
        run_id=run_id,
        run_label="",
        severity="INFO",
        metadata={
            "run_id": run_id,
            "dry_run_parsed": dry_run,
            "dry_run_source": "request_payload" if "dryRun" in payload else "default_false",
        },
    )

    # Import the batch execution function from the package
    try:
        from k8s_diag_agent.batch import run_batch_next_checks
    except (ModuleNotFoundError, ImportError, AttributeError) as exc:
        # REVIEWED: Module import boundary - narrowing to expected import errors
        handler._send_json({"error": f"Failed to load batch execution module: {exc}"}, 500)
        return

    try:
        result = run_batch_next_checks(
            runs_dir=handler.runs_dir,
            run_id=run_id,
            dry_run=dry_run,
        )
    except FileNotFoundError:
        handler._send_json({"error": f"Run not found: {run_id}"}, 404)
        return
    except Exception as exc:
        # REVIEWED: External execution boundary - run_batch_next_checks may raise
        # diverse exceptions from artifact writes, subprocess calls, JSON serialization
        # Narrowing would risk leaking uncontrolled failures to 500 response
        handler._send_json({"error": f"Batch execution failed: {exc}"}, 500)
        return

    # Convert result to response
    # Use "would_execute" for dry-run mode to clearly distinguish from actual execution
    execution_mode = "would_execute" if dry_run else "executed"
    response = {
        "status": "success",
        "summary": f"Batch execution {execution_mode} for run {run_id}",
        "runId": run_id,
        "dryRun": dry_run,
        "totalCandidates": result.total_candidates,
        "eligibleCandidates": result.eligible_candidates,
        "executedCount": result.executed_count,
        "skippedAlreadyExecuted": result.skipped_already_executed,
        "skippedIneligible": result.skipped_ineligible,
        "failedCount": result.failed_count,
        "successCount": result.success_count,
    }

    # If not dry run, refresh diagnostic pack and update UI read model
    if not dry_run and result.executed_count > 0:
        _refresh_diagnostic_pack_latest(run_id, handler.runs_dir)
        _persist_batch_execution_history_to_ui_index(handler.runs_dir, run_id)
        # Invalidate the runs list cache so Recent Runs reflects the new execution state
        _invalidate_runs_list_cache()

    handler._send_json(response)

