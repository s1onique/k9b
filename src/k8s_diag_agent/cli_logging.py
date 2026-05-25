"""Shared CLI logging utilities extracted from cli_handlers.py.

This module contains shared logging helpers and configuration used by CLI handlers.
Extracted to avoid duplication and ensure consistent logging behavior across modules.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .structured_logging import emit_structured_log

# Module-level log path (for backward compatibility)
CLI_LOG_PATH: Path | None = None


def _cli_run_label(command: str, identifier: str | None = None) -> str:
    label = command
    if identifier:
        label = f"{label}-{identifier}"
    return label


def _log_cli_event(
    component: str,
    run_label: str,
    message: str,
    *,
    severity: str = "INFO",
    run_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    **extra_metadata: Any,
) -> dict[str, Any]:
    return emit_structured_log(
        component=component,
        message=message,
        run_label=run_label,
        severity=severity,
        run_id=run_id,
        log_path=CLI_LOG_PATH,
        metadata=dict(metadata) if metadata else None,
        **extra_metadata,
    )


# Re-export for backward compatibility
__all__ = [
    "CLI_LOG_PATH",
    "_cli_run_label",
    "_log_cli_event",
]
