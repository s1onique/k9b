"""Budget reset helpers for OTel demo lab P4c phase.

This module provides budget isolation for the deterministic live-lab incident ID
`otel-demo-deployment-shipping-deployment_unavailable`.

The automatic diagnosis loop budget is tracked by counting existing review packets
in the external-analysis directory with the pattern:
    auto-{incident_id}-*-diagnosis-review-packet.json

When max_passes_per_incident is reached, the incident becomes ineligible.
For deterministic live-lab scenarios with repeated attempts, we need to reset
the budget by removing only the matching review packet files.

This is safe because:
- It only removes files matching the target incident ID
- It only removes files matching the diagnosis review packet pattern
- It does NOT touch:
  - Snapshots
  - Unrelated incidents
  - Provider config
  - Loop state artifacts (runs/health/)
  - All external-analysis content

Usage:
    from scripts.k9b_otel_demo_lab_k8s_diagnosis_budget_reset import reset_diagnosis_loop_budget
    
    # Before P4c runs targeted diagnosis
    removed = reset_diagnosis_loop_budget(
        external_analysis_dir=Path("/path/to/external-analysis"),
        incident_id="otel-demo-deployment-shipping-deployment_unavailable",
    )
    print(f"Removed {removed} budget artifacts")
"""

from __future__ import annotations

import logging
from pathlib import Path

from scripts.k9b_lab_common_helpers import log

_logger = logging.getLogger(__name__)

# Pattern for automatic diagnosis loop review packets
# Format: auto-{incident_id}-{timestamp}-{uuid}-diagnosis-review-packet.json
DIAGNOSIS_REVIEW_PACKET_PREFIX = "auto-"
DIAGNOSIS_REVIEW_PACKET_SUFFIX = "-diagnosis-review-packet.json"


def reset_diagnosis_loop_budget(
    external_analysis_dir: Path,
    incident_id: str,
) -> int:
    """Reset the automatic diagnosis loop budget for a specific incident.

    This removes all automatic diagnosis review packets for the incident,
    effectively resetting the budget so the incident can be processed again.

    This is used for deterministic live-lab scenarios where the same incident
    ID is reused across multiple lab attempts.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        incident_id: The incident ID whose budget to reset

    Returns:
        Number of files removed
    """
    if not external_analysis_dir.exists():
        _logger.debug(
            "External analysis dir does not exist, nothing to reset for incident_id=%s",
            incident_id,
        )
        return 0

    # Build pattern for matching review packets
    # Pattern: auto-{incident_id}-*-diagnosis-review-packet.json
    prefix = f"{DIAGNOSIS_REVIEW_PACKET_PREFIX}{incident_id}-"
    suffix = DIAGNOSIS_REVIEW_PACKET_SUFFIX

    removed_count = 0
    removed_files: list[str] = []

    try:
        for path in external_analysis_dir.iterdir():
            if not path.is_file():
                continue

            # Check if file matches the review packet pattern for this incident
            name = path.name
            if name.startswith(prefix) and name.endswith(suffix):
                try:
                    path.unlink()
                    removed_count += 1
                    removed_files.append(name)
                    _logger.debug("Removed budget artifact: %s", name)
                except OSError as e:
                    _logger.warning(
                        "Failed to remove budget artifact %s: %s",
                        name,
                        e,
                    )
    except OSError as e:
        _logger.warning(
            "Failed to scan external-analysis dir for budget reset: %s",
            e,
        )
        return 0

    if removed_count > 0:
        _logger.info(
            "Reset diagnosis loop budget for incident_id=%s: removed %d files",
            incident_id,
            removed_count,
        )
        log(
            f"  Budget reset: removed {removed_count} diagnosis review packet(s) "
            f"for {incident_id}"
        )
    else:
        _logger.debug(
            "No budget artifacts found for incident_id=%s (budget is clean)",
            incident_id,
        )

    return removed_count


def get_budget_status(
    external_analysis_dir: Path,
    incident_id: str,
) -> dict:
    """Get the current diagnosis loop budget status for an incident.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        incident_id: The incident ID to check

    Returns:
        Dict with budget status info
    """
    if not external_analysis_dir.exists():
        return {
            "incident_id": incident_id,
            "budget_clean": True,
            "review_packet_count": 0,
            "budget_exhausted": False,
        }

    prefix = f"{DIAGNOSIS_REVIEW_PACKET_PREFIX}{incident_id}-"
    suffix = DIAGNOSIS_REVIEW_PACKET_SUFFIX

    review_packets: list[str] = []

    try:
        for path in external_analysis_dir.iterdir():
            if not path.is_file():
                continue
            name = path.name
            if name.startswith(prefix) and name.endswith(suffix):
                review_packets.append(name)
    except OSError:
        pass

    return {
        "incident_id": incident_id,
        "budget_clean": len(review_packets) == 0,
        "review_packet_count": len(review_packets),
        "review_packets": review_packets,
        "budget_exhausted": len(review_packets) > 0,
    }


__all__ = [
    "reset_diagnosis_loop_budget",
    "get_budget_status",
]
