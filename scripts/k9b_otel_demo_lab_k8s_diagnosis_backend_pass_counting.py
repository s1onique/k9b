"""Helpers for counting observable diagnosis-loop passes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


def extract_pass_run_ids(loop_summary: dict[str, Any]) -> list[str]:
    """Extract pass run IDs from loop summary, supporting both field naming conventions.

    This helper handles the split-brain state where:
    - automatic_diagnosis_loop_summary uses pass_run_ids
    - loop_summary (live lab payload) may use diagnosis_loop_pass_run_ids

    Args:
        loop_summary: The loop summary dict from incident detail

    Returns:
        List of pass run IDs (empty if not found or invalid)
    """
    # Support both field naming conventions
    for key in ("pass_run_ids", "diagnosis_loop_pass_run_ids"):
        value = loop_summary.get(key)
        if isinstance(value, (list, tuple)) and value:
            # Filter to valid non-empty strings
            return [item for item in value if isinstance(item, str) and item]
    return []


def count_observable_targeted_diagnosis_passes(detail: dict[str, Any]) -> int:
    """Count observable targeted diagnosis passes from incident detail.

    Counting order (most preferred first):
    1. Explicit loop_summary.pass_count when present and an integer
    2. Length of loop_summary.diagnosis_loop_pass_run_ids or pass_run_ids when present
    3. 1 pass when automatic_diagnosis_review is available with a diagnosis-loop
       review-packet artifact and a run_id
    4. 0 otherwise

    This function handles the split-brain state where:
    - automatic_diagnosis_review is available (has review-packet artifact)
    - loop_summary may be null or missing pass info

    Also tolerates both field naming conventions:
    - automatic_diagnosis_loop_summary (newer API)
    - loop_summary (live lab payload)

    Args:
        detail: Incident detail dict from backend API

    Returns:
        Number of observable passes (0 or more)
    """
    # 1. Check loop_summary for explicit pass_count
    # Support both field naming conventions
    loop_summary = detail.get("automatic_diagnosis_loop_summary")
    if not isinstance(loop_summary, dict):
        loop_summary = detail.get("loop_summary")
    if isinstance(loop_summary, dict):
        pass_count = loop_summary.get("pass_count")
        if isinstance(pass_count, int) and pass_count > 0:
            return pass_count

        # 2. Check pass_run_ids in loop_summary (support both field names)
        pass_run_ids = extract_pass_run_ids(loop_summary)
        if pass_run_ids:
            return len(pass_run_ids)

    # 3. Check for diagnosis-loop review-packet in automatic_diagnosis_review
    review = detail.get("automatic_diagnosis_review")
    if isinstance(review, dict):
        available = review.get("available")
        if available is True:
            artifact_type = review.get("artifact_type")
            if artifact_type == "diagnosis-loop-review-packet":
                run_id = review.get("run_id")
                if isinstance(run_id, str) and run_id:
                    return 1

    # 4. Fallback: no observable passes
    return 0


__all__ = [
    "count_observable_targeted_diagnosis_passes",
    "extract_pass_run_ids",
]
