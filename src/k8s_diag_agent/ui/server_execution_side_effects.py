"""Post-execution side-effect helpers for the UI server.

This module contains side-effect functions that run after next-check execution:
- Diagnostic pack refresh (rebuilds /latest/ mirror)
- Execution history persistence to ui-index.json
- Runs list cache invalidation

Extracted from server.py to remove transitional import-back coupling from
server_batch_execution.py.

These functions perform filesystem writes and subprocess calls after execution.
"""

from __future__ import annotations

import json
import subprocess as _subprocess
import sys
from pathlib import Path
from threading import Lock
from typing import Any, cast

from ..structured_logging import emit_structured_log

logger = __import__("logging").getLogger(__name__)

# In-memory cache for runs list payload - keyed by runs_dir mtime
# Moved from server.py to be with the cache invalidation helper that uses it
_runs_list_cache: dict[str, tuple[dict[str, Any], float]] = {}  # key -> (payload, mtime)
_runs_list_cache_lock = Lock()

# Path to scripts directory (project root / scripts)
_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"


def _export_usefulness_review_for_run(run_id: str, runs_dir: Path) -> bool:
    """Export run-scoped usefulness review artifact after pack refresh.

    This produces the run-scoped JSON file at:
    runs/health/diagnostic-packs/<run_id>/next_check_usefulness_review.json

    The Recent runs Download link in the UI requires this exact run-scoped file
    to exist for the Download button to appear.

    Args:
        run_id: The current run ID
        runs_dir: Path to the runs directory

    Returns:
        True if export succeeded, False otherwise.
    """
    try:
        # Import here to avoid circular imports
        from scripts.export_next_check_usefulness_review import (
            export_next_check_usefulness_review,
        )

        emit_structured_log(
            component="pack-refresh",
            message="Exporting run-scoped usefulness review artifact",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(runs_dir / "health"),
                "operation": "export_usefulness_review",
            },
        )

        # Export to run-scoped path only (not /latest/ mirror)
        # The /latest/ mirror is already created by build_diagnostic_pack.py
        export_result = export_next_check_usefulness_review(
            runs_dir,
            run_id=run_id,
            use_run_scoped_path=True,
        )

        # Extract output path from result
        output_path = export_result.output_path
        if output_path is None:
            emit_structured_log(
                component="pack-refresh",
                message="Export returned no output path",
                run_id=run_id,
                run_label="",
                severity="WARNING",
                metadata={
                    "run_id": run_id,
                    "runs_root": str(runs_dir),
                    "health_root": str(runs_dir / "health"),
                    "operation": "export_usefulness_review",
                    "error_summary": "export returned None output_path",
                },
            )
            return False

        output_path_obj = Path(output_path)
        if not output_path_obj.exists():
            emit_structured_log(
                component="pack-refresh",
                message="Usefulness review export not found after export",
                run_id=run_id,
                run_label="",
                severity="WARNING",
                metadata={
                    "run_id": run_id,
                    "runs_root": str(runs_dir),
                    "health_root": str(runs_dir / "health"),
                    "exported_path": str(output_path),
                    "operation": "export_usefulness_review",
                    "error_summary": "exported file does not exist",
                },
            )
            return False

        emit_structured_log(
            component="pack-refresh",
            message="Usefulness review exported successfully",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(runs_dir / "health"),
                "exported_path": str(output_path),
                "file_size_bytes": output_path_obj.stat().st_size,
                "operation": "export_usefulness_review",
            },
        )
        return True
    except (OSError, ImportError, ModuleNotFoundError, AttributeError) as exc:
        # REVIEWED: Script import boundary - narrowing would risk silent failures in export flow
        # ImportErrors from scripts/export_next_check_usefulness_review are non-fatal
        emit_structured_log(
            component="pack-refresh",
            message="Failed to export run-scoped usefulness review artifact",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(runs_dir / "health"),
                "operation": "export_usefulness_review",
                "error": str(exc),
            },
        )
        return False



def _refresh_diagnostic_pack_latest(run_id: str, runs_dir: Path) -> bool:
    """Refresh the latest diagnostic pack mirror files after manual next-check execution.

    This rebuilds the review_bundle.json and review_input_14b.json files in the
    'latest' directory so the UI always points to current content after operator
    actions.

    Args:
        run_id: The current run ID
        runs_dir: Path to the runs directory

    Returns:
        True if refresh succeeded, False otherwise.
    """
    # Try multiple locations for the build script to handle both local and containerized environments
    build_script: Path | None = None
    script_locations_tried: list[str] = []

    # First try the scripts directory relative to project root
    primary_script = _SCRIPTS_DIR / "build_diagnostic_pack.py"
    script_locations_tried.append(str(primary_script))
    if primary_script.exists():
        build_script = primary_script

    # Fall back to current working directory (useful in containerized environments)
    if build_script is None:
        cwd_script = Path.cwd() / "scripts" / "build_diagnostic_pack.py"
        script_locations_tried.append(str(cwd_script))
        if cwd_script.exists():
            build_script = cwd_script

    # Last resort: try the script name directly in common locations
    if build_script is None:
        for search_path in [Path.cwd(), Path("/app"), Path("/app/scripts")]:
            candidate = search_path / "build_diagnostic_pack.py"
            script_locations_tried.append(str(candidate))
            if candidate.exists():
                build_script = candidate
                break

    if build_script is None:
        # All locations failed - emit structured log with diagnostic info
        emit_structured_log(
            component="pack-refresh",
            message="Cannot refresh diagnostic pack: build script not found",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(runs_dir / "health"),
                "refresh_root": str(_SCRIPTS_DIR),
                "script_path_attempted": script_locations_tried,
                "failed_stage": "script_discovery",
                "error_summary": "build script not found in any searched location",
            },
        )
        return False

    # Determine the correct Python executable to use
    # In containerized environments, use sys.executable; in local dev, also prefer sys.executable
    python_exe = sys.executable
    if not python_exe:
        # Fallback for edge cases
        python_exe = "python3"

    runs_dir_str = str(runs_dir)
    health_root = runs_dir / "health"
    build_cmd = [
        python_exe,
        str(build_script),
        "--run-id",
        run_id,
        "--runs-dir",
        runs_dir_str,
    ]

    try:
        # Emit structured log for start of pack refresh
        emit_structured_log(
            component="pack-refresh",
            message="Starting diagnostic pack refresh",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
                "python_executable": python_exe,
                "command": build_cmd,
            },
        )

        # Run the build script - it will write the latest mirror files as part of its work
        _subprocess.run(
            build_cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout for pack building
        )

        # Emit structured log for successful refresh
        emit_structured_log(
            component="pack-refresh",
            message="Diagnostic pack latest mirror refreshed successfully",
            run_id=run_id,
            run_label="",
            severity="INFO",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
            },
        )

        # Also export the run-scoped usefulness review artifact for Recent runs Download link
        _export_usefulness_review_for_run(run_id, runs_dir)

        return True
    except _subprocess.CalledProcessError as exc:
        emit_structured_log(
            component="pack-refresh",
            message="Failed to refresh diagnostic pack latest mirror",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
                "failed_stage": "script_execution",
                "returncode": exc.returncode,
                "error_summary": f"script returned non-zero: {exc.returncode}",
                "stderr_preview": exc.stderr[:500] if exc.stderr else "",
            },
        )
        return False
    except _subprocess.TimeoutExpired:
        emit_structured_log(
            component="pack-refresh",
            message="Failed to refresh diagnostic pack latest mirror: timeout",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
                "failed_stage": "script_timeout",
                "error_summary": "build script timed out after 120 seconds",
            },
        )
        return False
    except OSError as exc:
        emit_structured_log(
            component="pack-refresh",
            message="Failed to refresh diagnostic pack latest mirror",
            run_id=run_id,
            run_label="",
            severity="WARNING",
            metadata={
                "run_id": run_id,
                "runs_root": str(runs_dir),
                "health_root": str(health_root),
                "refresh_root": str(build_script.parent),
                "script_path_attempted": str(build_script),
                "failed_stage": "os_error",
                "error_summary": str(exc),
            },
        )
        return False


def _invalidate_runs_list_cache() -> None:
    """Invalidate the in-memory runs list cache.

    Called after mutations (batch execution, single execution, etc.) to ensure
    that subsequent /api/runs requests reflect the new state.

    This is necessary because the runs list is cached by directory mtime,
    but mutations may update files that don't change the mtime of the
    cached directories (e.g., writing new execution artifacts).
    """
    with _runs_list_cache_lock:
        _runs_list_cache.clear()
    emit_structured_log(
        component="ui-runs-list",
        message="Runs list cache invalidated",
        run_id="",
        run_label="",
        severity="DEBUG",
        metadata={
            "action": "cache_invalidation",
            "reason": "mutation_aftermath",
        },
    )


def _get_field_with_fallback(entry: dict[str, object], field: str) -> object | None:
    """Get field with fallback to alternate field names.

    This mirrors the behavior in server_read_support.py for consistency.
    """
    if field in entry:
        return entry.get(field)
    # Try alternate spellings
    alternates = {
        "timestamp": "createdAt",
        "candidateId": "candidate_id",
        "commandFamily": "command_family",
    }
    alt_field = alternates.get(field, field)
    if alt_field in entry:
        return entry.get(alt_field)
    return None


def _persist_batch_execution_history_to_ui_index(runs_dir: Path, run_id: str) -> None:
    """Update ui-index.json with execution history entries from batch execution.

    This mirrors the behavior of single next-check execution, which also updates
    the UI read model directly. Without this, batch executions would not appear
    in the Execution History section until the next health loop.

    Uses the same entry-building logic as _build_execution_history to ensure
    consistent field handling (candidateId, provenance fields, etc.).

    Args:
        runs_dir: Path to the runs directory
        run_id: The run ID to update
    """
    from .server_read_support import _build_execution_history

    health_root = runs_dir / "health"
    ui_index_path = health_root / "ui-index.json"

    # Load existing ui-index.json
    try:
        index_data = json.loads(ui_index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning(
            "Failed to read ui-index.json for batch execution history update",
            extra={"run_id": run_id},
        )
        return

    run_entry = index_data.get("run") or {}
    existing_history = list(run_entry.get("next_check_execution_history") or [])

    # Build complete history from current artifacts using the same logic
    # as _build_execution_history for consistency
    external_dir = health_root / "external-analysis"
    if not external_dir.exists():
        return

    # Use _build_execution_history to get properly-shaped entries with all fields
    fresh_history, _ = _build_execution_history(external_dir, run_id)

    if not fresh_history:
        return

    # Track existing entries by (candidateIndex, timestamp) to avoid duplicates
    existing_keys: set[tuple[int | None, str]] = set()
    for entry in existing_history:
        idx = entry.get("candidateIndex")
        if isinstance(idx, int):
            idx_key: int | None = idx
        else:
            idx_key = None
        ts_val: str = cast(str, _get_field_with_fallback(entry, "timestamp") or "")
        existing_keys.add((idx_key, ts_val))

    # Merge: add entries not already present
    merged_history = list(existing_history)
    new_count = 0
    for entry in fresh_history:
        idx = entry.get("candidateIndex")
        if isinstance(idx, int):
            fresh_idx_key: int | None = idx
        else:
            fresh_idx_key = None
        fresh_ts: str = cast(str, entry.get("timestamp") or "")
        key = (fresh_idx_key, fresh_ts)
        if key not in existing_keys:
            merged_history.append(entry)
            new_count += 1
            existing_keys.add(key)

    # Sort by timestamp descending (most recent first), consistent with _build_execution_history
    merged_history.sort(key=lambda x: cast(str, x.get("timestamp") or ""), reverse=True)

    # Limit to 5 most recent, consistent with _build_execution_history
    merged_history = merged_history[:5]

    if new_count > 0:
        run_entry["next_check_execution_history"] = merged_history
        index_data["run"] = run_entry

        try:
            ui_index_path.write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug(
                "Persisted batch execution history to ui-index.json",
                extra={"run_id": run_id, "new_entries": new_count},
            )
        except (OSError, TypeError, ValueError) as exc:
            logger.warning(
                "Failed to persist batch execution history to ui-index.json",
                extra={"run_id": run_id, "error": str(exc)},
            )


# Re-export cache access for external use (e.g., server.py runs list handler)
def get_runs_list_cache() -> dict[str, tuple[dict[str, Any], float]]:
    """Return the runs list cache dictionary."""
    return _runs_list_cache


def get_runs_list_cache_lock() -> Lock:
    """Return the runs list cache lock."""
    return _runs_list_cache_lock
