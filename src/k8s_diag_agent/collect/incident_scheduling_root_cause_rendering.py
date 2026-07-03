"""Rendering helpers for scheduling root-cause diagnosis.

This module contains pure text/render helpers for generating human-readable
messages and summaries from scheduling evidence.

Keep this module side-effect-free. It is imported by incident_scheduling_root_cause.py.

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

# =============================================================================
# Root-cause summary building
# =============================================================================


def _build_root_cause_summary(
    workload_kind: str,
    workload_name: str,
    namespace: str,
    selector_key: str | None,
    selector_value: str | None,
    failed_scheduling: bool,
    unschedulable: bool,
    scheduler_message: str | None,
) -> str:
    """Build a human-readable root-cause summary.

    The summary MUST contain these terms for P4c validation:
    - shipping (workload name)
    - nodeSelector
    - k9b.dev/otel-lab-node
    - FailedScheduling (if applicable)
    - Unschedulable (if applicable)

    Args:
        workload_kind: Kind of workload
        workload_name: Name of workload
        namespace: Namespace
        selector_key: nodeSelector key
        selector_value: nodeSelector value
        failed_scheduling: Whether FailedScheduling was observed
        unschedulable: Whether pods are unschedulable
        scheduler_message: Raw scheduler message

    Returns:
        Human-readable root-cause summary
    """
    parts: list[str] = []

    # Core identity
    parts.append(f"{workload_kind}/{workload_name}")

    # Scheduling failure indicator
    if failed_scheduling:
        parts.append("FailedScheduling")
    if unschedulable:
        parts.append("Unschedulable")

    # nodeSelector evidence
    if selector_key and selector_value:
        parts.append(f"nodeSelector {selector_key}={selector_value}")
        parts.append("no matching node")

    # Fallback for generic scheduling evidence
    if not selector_key and (failed_scheduling or unschedulable):
        parts.append("scheduling failure")

    return " ".join(parts)


__all__ = [
    "_build_root_cause_summary",
]
