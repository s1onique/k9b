"""Artifact writing for run_trace_capture module.

This module contains:
- Trace ID writing
- Backend API trace writing
- Trace summary writing
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trace_summary import TraceSummary


def write_trace_ids(trace_ids: list[str], artifact_dir: Path) -> Path:
    """Write trace IDs to file.

    Args:
        trace_ids: List of trace ID strings
        artifact_dir: Directory to write to

    Returns:
        Path to written file
    """
    trace_ids_path = artifact_dir / "trace-ids.txt"
    content = "\n".join(trace_ids)
    trace_ids_path.write_text(content)
    return trace_ids_path


def write_backend_api_traces(
    exercise_results: list[dict[str, Any]],
    artifact_dir: Path,
) -> Path:
    """Write API exercise results to file.

    Args:
        exercise_results: List of API exercise results
        artifact_dir: Directory to write to

    Returns:
        Path to written file
    """
    output_path = artifact_dir / "backend-api-traces.json"
    # Sanitize results - remove any raw content
    sanitized: list[dict[str, Any]] = []
    for result in exercise_results:
        sanitized_result: dict[str, Any] = {
            "endpoint": result.get("endpoint", ""),
            "method": result.get("method", ""),
            "status_code": result.get("status_code"),
            "success": result.get("success", False),
        }
        if "error" in result:
            sanitized_result["error"] = result["error"]
        sanitized.append(sanitized_result)

    output_path.write_text(json.dumps(sanitized, indent=2))
    return output_path


def write_trace_summary(
    summary: TraceSummary,
    artifact_dir: Path,
) -> Path:
    """Write trace summary to file.

    Args:
        summary: Trace summary to write
        artifact_dir: Directory to write to

    Returns:
        Path to written file
    """
    summary_path = artifact_dir / "trace-summary.json"
    summary_path.write_text(json.dumps(summary.to_dict(), indent=2))
    return summary_path
