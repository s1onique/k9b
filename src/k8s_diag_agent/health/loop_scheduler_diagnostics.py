"""Diagnostic pack building and run summary logging helpers for the scheduler.

Extracted from loop_scheduler.py to reduce its size and improve LLM-friendly traversal.
Preserves behavior exactly - no timing, lock, or artifact contract changes.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..security.subprocess_helpers import _sanitize_output
from .freshness import freshness_status
from .loop_history import _env_is_truthy
from .loop_scheduler_models import DIAGNOSTIC_PACK_TIMEOUT_SECONDS
from .ui_llm_stats import _build_provider_execution
from .ui_projection.review_enrichment import _serialize_review_enrichment_policy

# =============================================================================
# Pure Helper Functions
# =============================================================================


def resolve_run_id(
    assessments: list[Any],
    triggers: list[Any],
) -> str:
    """Resolve the run ID from assessments or triggers.

    Prefers assessments over triggers, returning '<unknown>' if neither provides
    a run_id attribute.
    """
    if assessments:
        return getattr(assessments[0], 'run_id', "<unknown>")
    if triggers:
        return getattr(triggers[0], 'run_id', "<unknown>")
    return "<unknown>"


def format_last_run_timestamp(last_run_finish_time: float | None) -> str | None:
    """Format a Unix timestamp as an ISO string in UTC."""
    if last_run_finish_time is None:
        return None
    return datetime.fromtimestamp(last_run_finish_time, UTC).isoformat()


# =============================================================================
# Diagnostic Pack Helpers
# =============================================================================


def build_diagnostic_pack(
    log_fn: Callable[..., None],
    scripts_dir: Path,
    runs_dir_base: Path,
    run_id: str,
) -> None:
    """Build diagnostic pack and update UI index if configured via environment.

    Respects HEALTH_BUILD_DIAGNOSTIC_PACK environment variable.
    Runs build_diagnostic_pack.py and update_ui_index.py scripts in sequence.
    """
    env_value = os.environ.get("HEALTH_BUILD_DIAGNOSTIC_PACK")
    if not _env_is_truthy(env_value):
        return
    if not run_id or run_id == "<unknown>":
        log_fn(
            "INFO",
            "Skipping diagnostic pack generation; run_id unavailable",
            run_id=run_id,
            event="diag-pack-skipped",
        )
        return
    runs_dir = str(runs_dir_base)
    _run_diagnostic_pack_build(log_fn, scripts_dir, runs_dir, run_id)
    _run_ui_index_refresh(log_fn, scripts_dir, runs_dir, run_id)
    log_fn(
        "INFO",
        "Scheduled diagnostic pack generated",
        run_id=run_id,
        runs_dir=runs_dir,
        event="diag-pack-generated",
    )


def _run_diagnostic_pack_build(
    log_fn: Callable[..., None],
    scripts_dir: Path,
    runs_dir: str,
    run_id: str,
) -> None:
    """Execute diagnostic pack build script."""
    build_script = scripts_dir / "build_diagnostic_pack.py"
    build_cmd = [
        sys.executable,
        str(build_script),
        "--run-id",
        run_id,
        "--runs-dir",
        runs_dir,
    ]
    try:
        subprocess.run(
            build_cmd,
            check=True,
            env=os.environ,
            timeout=DIAGNOSTIC_PACK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        log_fn(
            "ERROR",
            "Scheduled diagnostic pack build timed out",
            run_id=run_id,
            severity_reason=f"build timed out after {DIAGNOSTIC_PACK_TIMEOUT_SECONDS}s",
            event="diag-pack-build-timeout",
        )
        return
    except (subprocess.CalledProcessError, OSError) as exc:
        error_str = _sanitize_subprocess_error(exc)
        log_fn(
            "ERROR",
            "Scheduled diagnostic pack build failed",
            run_id=run_id,
            severity_reason=error_str,
            event="diag-pack-build-failed",
        )


def _run_ui_index_refresh(
    log_fn: Callable[..., None],
    scripts_dir: Path,
    runs_dir: str,
    run_id: str,
) -> None:
    """Execute UI index refresh script."""
    update_script = scripts_dir / "update_ui_index.py"
    update_cmd = [
        sys.executable,
        str(update_script),
        "--run-id",
        run_id,
        "--runs-dir",
        runs_dir,
    ]
    try:
        subprocess.run(
            update_cmd,
            check=True,
            env=os.environ,
            timeout=DIAGNOSTIC_PACK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        log_fn(
            "ERROR",
            "Scheduled UI index refresh timed out after diagnostic pack build",
            run_id=run_id,
            severity_reason=f"index refresh timed out after {DIAGNOSTIC_PACK_TIMEOUT_SECONDS}s",
            event="diag-pack-ui-refresh-timeout",
        )
        return
    except (subprocess.CalledProcessError, OSError) as exc:
        error_str = _sanitize_subprocess_error(exc)
        log_fn(
            "ERROR",
            "Scheduled UI index refresh failed after diagnostic pack build",
            run_id=run_id,
            severity_reason=error_str,
            event="diag-pack-ui-refresh-failed",
        )


def _sanitize_subprocess_error(exc: BaseException) -> str:
    """Sanitize subprocess error to prevent credential leakage."""
    if isinstance(exc, subprocess.CalledProcessError):
        stderr_output = exc.stderr if exc.stderr else exc.stdout
        return _sanitize_output(
            stderr_output.decode("utf-8", errors="replace")
            if isinstance(stderr_output, bytes)
            else (stderr_output or "")
        )
    return str(exc)


# =============================================================================
# Run Summary Logging
# =============================================================================


def log_run_summary(
    log_fn: Callable[..., None],
    assessments: list[Any],
    triggers: list[Any],
    drilldowns: list[Any],
    external_analysis: list[Any],
    settings: Any,
    last_run_finish_time: float | None = None,
    freshness_age_seconds: float | None = None,
    expected_interval_seconds: int | None = None,
) -> None:
    """Log a summary of a completed health run.

    Emits a structured INFO event with health counts, provider execution details,
    and freshness status if interval information is available.
    """
    run_id = resolve_run_id(assessments, triggers)
    healthy_count = sum(
        1 for artifact in assessments
        if getattr(getattr(artifact, 'health_rating', None), 'value', None) == "healthy"
    )
    degraded_count = len(assessments) - healthy_count
    review_config = _serialize_review_enrichment_policy(settings.review_enrichment)
    provider_execution = _build_provider_execution(
        settings,
        external_analysis,
        drilldowns,
        review_config,
    )
    metadata: dict[str, object] = {
        "run_id": run_id,
        "assessment_count": len(assessments),
        "healthy_count": healthy_count,
        "degraded_count": degraded_count,
        "trigger_count": len(triggers),
        "drilldown_count": len(drilldowns),
        "external_analysis_count": len(external_analysis),
        "provider_execution": provider_execution,
        "event": "run-summary",
    }
    last_run_ts = format_last_run_timestamp(last_run_finish_time)
    if last_run_ts is not None:
        metadata["last_successful_run_timestamp"] = last_run_ts
    if expected_interval_seconds is not None:
        metadata["expected_interval_seconds"] = expected_interval_seconds
        if freshness_age_seconds is not None:
            age_value = int(max(0.0, freshness_age_seconds))
            metadata["freshness_age_seconds"] = age_value
            status = freshness_status(age_value, expected_interval_seconds)
            if status:
                metadata["freshness_status"] = status
    log_fn(
        "INFO",
        "Health run summary",
        **metadata,
    )
