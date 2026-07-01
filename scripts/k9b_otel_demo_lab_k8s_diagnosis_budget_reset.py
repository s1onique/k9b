"""Budget reset helpers for OTel demo lab P4c phase.

This module provides budget isolation for the deterministic live-lab incident ID
`otel-demo-deployment-shipping-deployment_unavailable`.

The automatic diagnosis loop budget is tracked by counting existing review packets
in the external-analysis directory with the pattern:
    auto-{incident_id}-*-diagnosis-review-packet.json

Additionally, loop pass artifacts and other diagnosis-loop state may affect
backend eligibility checks. This module clears ONLY known budget-affecting
artifacts for the incident to ensure complete budget reset without touching
unrelated files.

When max_passes_per_incident is reached, the incident becomes ineligible.
For deterministic live-lab scenarios with repeated attempts, we need to reset
the budget by removing matching diagnosis-loop files.

This is safe because:
- It only removes files matching the target incident ID
- It only removes files matching known budget-affecting suffixes
- It does NOT touch:
  - Snapshots: auto-{incident_id}-snapshot.json
  - Unrelated incidents
  - Provider config
  - Other auto-generated artifacts not in the budget-resettable allowlist

Budget-resettable suffixes:
- -diagnosis-review-packet.json
- -diagnosis-loop-pass.json
- -read-only-check-result.json
- -next-check-budget.json

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

# Suffixes for budget-affecting artifacts that can be safely reset
# These are the ONLY artifacts that contribute to backend budget checks
BUDGET_RESETTABLE_SUFFIXES = (
    "-diagnosis-review-packet.json",
    "-diagnosis-loop-pass.json",
    "-read-only-check-result.json",
    "-next-check-budget.json",
)

# Pattern for automatic diagnosis loop review packets
# Format: auto-{incident_id}-{timestamp}-{uuid}-diagnosis-review-packet.json
DIAGNOSIS_REVIEW_PACKET_PREFIX = "auto-"
DIAGNOSIS_REVIEW_PACKET_SUFFIX = "-diagnosis-review-packet.json"

# Pattern for loop pass artifacts (written by runtime orchestrator)
# Format: {run_id}-diagnosis-loop-pass.json where run_id contains incident_id
LOOP_PASS_SUFFIX = "-diagnosis-loop-pass.json"


def _matches_diagnosis_artifact(name: str, incident_id: str) -> bool:
    """Check if a filename matches any budget-affecting artifact pattern for the incident.

    This matches ONLY known budget-affecting suffixes:
    1. Review packets: auto-{incident_id}-*-diagnosis-review-packet.json
    2. Loop pass artifacts: auto-{incident_id}-*-diagnosis-loop-pass.json
    3. Read-only check results: auto-{incident_id}-*-read-only-check-result.json
    4. Next-check budgets: auto-{incident_id}-*-next-check-budget.json

    This does NOT match:
    - Snapshots: auto-{incident_id}-snapshot.json
    - Other auto-generated artifacts not in BUDGET_RESETTABLE_SUFFIXES

    Args:
        name: The filename to check
        incident_id: The incident ID to match

    Returns:
        True if the filename matches any budget-affecting artifact pattern
    """
    if not name.startswith(f"auto-{incident_id}-"):
        return False
    return name.endswith(BUDGET_RESETTABLE_SUFFIXES)


def reset_diagnosis_loop_budget(
    external_analysis_dir: Path,
    incident_id: str,
) -> int:
    """Reset the automatic diagnosis loop budget for a specific incident.

    This removes only known budget-affecting automatic diagnosis-loop artifacts
    for the incident, including review packets, loop pass artifacts, read-only
    check results, and next-check budget artifacts.

    It intentionally preserves snapshots and other non-budget auto-generated files.

    This is used for deterministic live-lab scenarios where the same incident
    ID is reused across multiple lab attempts.

    Note: The backend eligibility check currently uses only review packet count
    as the budget gate. Loop pass artifacts, read-only check results, and
    next-check budgets are cleared for defensive completeness in case the
    backend adds additional budget sources in the future.

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

    removed_count = 0
    removed_files: list[str] = []
    removed_types: dict[str, int] = {
        "review_packets": 0,
        "loop_passes": 0,
        "other_budget_artifacts": 0,
    }

    try:
        # Use rglob to find artifacts in nested paths (e.g., health/external-analysis/phase4-diagnosis/)
        # This ensures we match the backend's artifact discovery pattern
        for path in external_analysis_dir.rglob("*"):  # noqa: PTH207
            if not path.is_file():
                continue

            name = path.name

            # Check if file matches any diagnosis-loop artifact pattern for this incident
            if not _matches_diagnosis_artifact(name, incident_id):
                continue

            # Categorize for logging
            if name.endswith(DIAGNOSIS_REVIEW_PACKET_SUFFIX):
                removed_types["review_packets"] += 1
            elif name.endswith(LOOP_PASS_SUFFIX):
                removed_types["loop_passes"] += 1
            else:
                removed_types["other_budget_artifacts"] += 1

            try:
                path.unlink()
                removed_count += 1
                removed_files.append(str(path.relative_to(external_analysis_dir)))
                _logger.debug("Removed diagnosis artifact: %s", path)
            except OSError as e:
                _logger.warning(
                    "Failed to remove diagnosis artifact %s: %s",
                    path,
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
            "Reset diagnosis loop budget for incident_id=%s: removed %d files (%s)",
            incident_id,
            removed_count,
            removed_types,
        )
        log(
            f"  Budget reset: removed {removed_count} diagnosis artifact(s) for {incident_id}: "
            f"{removed_types['review_packets']} review packets, "
            f"{removed_types['loop_passes']} loop passes, "
            f"{removed_types['other_budget_artifacts']} other budget artifacts"
        )
    else:
        _logger.debug(
            "No diagnosis artifacts found for incident_id=%s (budget is clean)",
            incident_id,
        )
        log(f"  Budget reset: no diagnosis artifacts found for {incident_id} (already clean)")

    return removed_count


def get_budget_status(
    external_analysis_dir: Path,
    incident_id: str,
) -> dict:
    """Get the current diagnosis loop budget status for an incident.

    Returns comprehensive status including all artifact types that affect
    backend eligibility checks.

    Args:
        external_analysis_dir: Path to the external-analysis directory
        incident_id: The incident ID to check

    Returns:
        Dict with comprehensive budget status info including all artifact types
    """
    if not external_analysis_dir.exists():
        return {
            "incident_id": incident_id,
            "budget_clean": True,
            "review_packet_count": 0,
            "loop_pass_count": 0,
            "other_auto_count": 0,
            "other_budget_artifact_count": 0,
            "total_auto_artifact_count": 0,
            "budget_exhausted": False,
            "artifacts": {
                "review_packets": [],
                "loop_passes": [],
                "other_auto": [],
                "other_budget_artifacts": [],
            },
        }

    review_packets: list[str] = []
    loop_passes: list[str] = []
    other_auto: list[str] = []

    try:
        # Use rglob to find artifacts in nested paths (e.g., health/external-analysis/phase4-diagnosis/)
        # This ensures we match the backend's artifact discovery pattern
        for path in external_analysis_dir.rglob("*"):  # noqa: PTH207
            if not path.is_file():
                continue
            name = path.name

            # Check if matches any diagnosis-loop artifact pattern
            if not _matches_diagnosis_artifact(name, incident_id):
                continue

            relative_path = str(path.relative_to(external_analysis_dir))

            # Categorize
            if name.endswith(DIAGNOSIS_REVIEW_PACKET_SUFFIX):
                review_packets.append(relative_path)
            elif name.endswith(LOOP_PASS_SUFFIX):
                loop_passes.append(relative_path)
            else:
                other_auto.append(relative_path)
    except OSError:
        pass

    total_count = len(review_packets) + len(loop_passes) + len(other_auto)

    return {
        "incident_id": incident_id,
        "budget_clean": total_count == 0,
        "review_packet_count": len(review_packets),
        "loop_pass_count": len(loop_passes),
        "other_auto_count": len(other_auto),  # Alias for backwards compatibility
        "other_budget_artifact_count": len(other_auto),
        "total_auto_artifact_count": total_count,
        "budget_exhausted": total_count > 0,
        "artifacts": {
            "review_packets": review_packets,
            "loop_passes": loop_passes,
            "other_auto": other_auto,  # Alias for backwards compatibility
            "other_budget_artifacts": other_auto,
        },
    }


__all__ = [
    "reset_diagnosis_loop_budget",
    "get_budget_status",
]
