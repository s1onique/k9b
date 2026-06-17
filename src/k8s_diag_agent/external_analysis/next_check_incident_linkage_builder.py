"""Builder functions for incident linkage construction.

This module contains the primary public function for building linkage fields:
- build_next_check_incident_linkage()

No file IO, no LLM calls, no Kubernetes calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .next_check_incident_linkage_contracts import (
        IncidentLinkageContext,
        NextCheckCandidateLinkage,
        NextCheckPlanLinkage,
    )


# =============================================================================
# Main Enrichment Function
# =============================================================================


def build_next_check_incident_linkage(
    context: IncidentLinkageContext | None,
) -> tuple[NextCheckPlanLinkage, NextCheckCandidateLinkage] | None:
    """Build linkage fields for next-check plan and candidate.

    This is the primary public function for enriching next-check artifacts
    with incident linkage fields.

    Args:
        context: The incident linkage context. If None, returns None.

    Returns:
        Tuple of (plan_linkage, candidate_linkage) if context is provided,
        None otherwise.

    Example:
        >>> context = IncidentLinkageContext(
        ...     incident_id="default-pod-my-pod-crash-loop",
        ...     source_candidate_id="cand-001",
        ...     namespace="default",
        ...     object_kind="Pod",
        ...     object_name="my-pod",
        ...     candidate_class="crash_loop",
        ...     run_id="run-123",
        ... )
        >>> result = build_next_check_incident_linkage(context)
        >>> if result:
        ...     plan_linkage, candidate_linkage = result
        ...     print(candidate_linkage.linkage_status)  # "linked"
    """
    if context is None:
        return None

    # Import here to avoid circular imports at runtime
    from .next_check_incident_linkage_contracts import (
        NextCheckCandidateLinkage,
        NextCheckPlanLinkage,
    )

    plan_linkage = NextCheckPlanLinkage.from_context(context)
    candidate_linkage = NextCheckCandidateLinkage.from_context(context)

    return (plan_linkage, candidate_linkage)


__all__ = [
    "build_next_check_incident_linkage",
]
