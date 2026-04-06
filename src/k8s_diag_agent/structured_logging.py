"""Shared helper for writing structured observability events."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from .security import sanitize_log_entry

DEFAULT_HEALTH_LOG = Path("runs") / "health" / "health.log"


def _current_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_structured_log(
    component: str,
    message: str,
    run_label: str,
    *,
    severity: str = "INFO",
    run_id: str | None = None,
    log_path: Path | None = None,
    writer: TextIO | None = None,
    metadata: Mapping[str, Any] | None = None,
    **extra_metadata: Any,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "timestamp": _current_timestamp(),
        "component": component,
        "severity": severity.upper(),
        "message": message,
        "run_label": run_label,
    }
    if run_id:
        entry["run_id"] = run_id
    if metadata:
        entry.update(metadata)
    if extra_metadata:
        entry.update(extra_metadata)
    sanitized = sanitize_log_entry(entry)
    line = json.dumps(sanitized, separators=(",", ":"), ensure_ascii=False)
    if writer is not None:
        writer.write(line + "\n")
        writer.flush()
        return sanitized
    target = log_path or DEFAULT_HEALTH_LOG
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return sanitized


__all__ = ["emit_structured_log", "DEFAULT_HEALTH_LOG"]
