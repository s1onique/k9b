"""Content kind detection for projections.

This module detects content kinds from file paths and content.

Schema Version: k9b.content_index.v1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# File patterns for content kind detection
CONTENT_KIND_PATTERNS: dict[str, list[str]] = {
    "incident": [
        "**/k9b-incidents.json",
        "**/k9b-incident-detail.json",
    ],
    "evidence_link": [
        "**/incident-evidence-links.json",
    ],
    "snapshot_bundle": [
        "**/snapshot*.json",
    ],
    "review_packet": [
        "**/review-packet*.json",
    ],
    "automatic_diagnosis_review": [
        "**/automatic-diagnosis-review*.json",
        "**/auto-diagnosis-review*.json",
    ],
    "automatic_diagnosis_hypothesis_burst": [
        "**/automatic-diagnosis/*-hypothesis-burst.json",
    ],
    "automatic_diagnosis_pass": [
        "**/automatic-diagnosis/*-pass-*.json",
    ],
    "automatic_diagnosis_final_hypotheses": [
        "**/automatic-diagnosis/*-final-hypotheses.json",
    ],
    "automatic_diagnosis_summary": [
        "**/automatic-diagnosis/*-summary.json",
    ],
    "diagnosis_loop_run": [
        "**/diagnosis-loop-run*.json",
    ],
    "diagnosis_loop_pass": [
        "**/diagnosis-loop-pass*.json",
        "**/loop-pass*.json",
    ],
    "lab_result": [
        "**/lab-result.json",
    ],
    "trace_capture_summary": [
        "**/trace-summary.json",
    ],
    "perf_baseline_summary": [
        "**/backend-api-baseline-summary.json",
    ],
}


def detect_content_kind(
    file_path: Path,
    file_content: dict[str, Any] | None = None,
) -> str | None:
    """Detect content kind from file path and optionally content.

    Args:
        file_path: Path to the file.
        file_content: Optional parsed JSON content.

    Returns:
        Detected content kind or None.
    """
    path_str = str(file_path)

    # Check path patterns first
    for kind, patterns in CONTENT_KIND_PATTERNS.items():
        for pattern in patterns:
            # Simple glob matching
            if pattern.endswith(".json"):
                pattern_base = pattern.rsplit("/", 1)[0] if "/" in pattern else ""
                if pattern_base and pattern_base in path_str:
                    return kind
                elif pattern.endswith("/" + pattern.split("/")[-1]):
                    if pattern.split("/")[-1] in path_str:
                        return kind

    # Check content-based patterns
    if file_content is not None:
        # Check for schema version fields
        schema_version = file_content.get("schema_version", "")
        if "incident" in schema_version.lower():
            return "incident"
        if "lab" in schema_version.lower():
            return "lab_result"
        if "trace_capture" in schema_version.lower():
            return "trace_capture_summary"
        if "perf_baseline" in schema_version.lower():
            return "perf_baseline_summary"

        # Check for specific fields
        if "scenario" in file_content and "started_at" in file_content:
            return "lab_result"
        if "trace_count" in file_content and "span_count" in file_content:
            return "trace_capture_summary"
        if "total_traces" in file_content and "iteration_count" in file_content:
            return "perf_baseline_summary"

    return None
