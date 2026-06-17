"""Enrichment functions for dict-based linkage field injection.

This module provides deterministic linkage field injection for next-check plan
artifacts:
- enrich_next_check_candidate_dict()
- enrich_next_check_plan_dict()
- _candidate_has_explicit_structured_match() (private helper)

No file IO, no LLM calls, no Kubernetes calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .next_check_incident_linkage_contracts import (
        NextCheckCandidateLinkage,
        NextCheckPlanLinkage,
    )


# =============================================================================
# Candidate Matching Logic
# =============================================================================


def _candidate_has_explicit_structured_match(
    candidate_dict: dict[str, Any],
    linkage: NextCheckCandidateLinkage,
) -> bool:
    """Check if a candidate has explicit structured match with incident context.

    This is a STRICT check using ONLY explicit structured identity matching.
    No text/description/command-family matching is used. Provider-supplied
    incident_id is NOT trusted as a match source.

    A candidate is considered explicitly linked when:
    1. candidate.candidateId matches linkage.source_candidate_id, OR
    2. candidate has ALL FOUR structured fields present AND they exactly match linkage:
       - namespace is present and matches
       - objectKind is present and matches
       - objectName is present and matches
       - candidateClass is present and matches

    NOT trusted as match sources:
    - candidate.incident_id (provider-supplied, may be forged)

    Args:
        candidate_dict: The candidate dict to check.
        linkage: The linkage fields derived from incident context.

    Returns:
        True only if there's an explicit structured match.
    """
    # Check 1: candidate.candidateId matches linkage.source_candidate_id
    # This is a deterministic link from the same diagnostic run
    candidate_id = candidate_dict.get("candidateId") or candidate_dict.get("candidate_id")
    if candidate_id and linkage.source_candidate_id:
        if candidate_id == linkage.source_candidate_id:
            return True

    # Check 2: All four structured identity fields must be PRESENT and EXACTLY match
    # First, check that all candidate fields are present (not None)
    cand_namespace = candidate_dict.get("namespace")
    cand_object_kind = candidate_dict.get("objectKind") or candidate_dict.get("object_kind")
    cand_object_name = candidate_dict.get("objectName") or candidate_dict.get("object_name")
    cand_candidate_class = candidate_dict.get("candidateClass") or candidate_dict.get("candidate_class")

    # All four candidate fields must be present
    if not all([cand_namespace, cand_object_kind, cand_object_name, cand_candidate_class]):
        return False

    # All four linkage fields must be present
    if not all([linkage.namespace, linkage.object_kind, linkage.object_name, linkage.candidate_class]):
        return False

    # Then check exact match
    if (cand_namespace == linkage.namespace and
        cand_object_kind == linkage.object_kind and
        cand_object_name == linkage.object_name and
        cand_candidate_class == linkage.candidate_class):
        return True

    return False


# =============================================================================
# Candidate Dict Enrichment
# =============================================================================


def enrich_next_check_candidate_dict(
    candidate_dict: dict[str, Any],
    linkage: NextCheckCandidateLinkage,
) -> dict[str, Any]:
    """Enrich a candidate dict with linkage fields.

    This function injects linkage fields into an existing candidate dict.
    It is STRICT about per-candidate incident_id - it only stamps it when
    there's an EXPLICIT STRUCTURED MATCH between the candidate and the
    incident context.

    INVARIANT: candidate.linkage_status == "linked" iff candidate.incident_id is present

    Rules:
    - linked: candidate has explicit structured match AND linkage.incident_id is available.
      incident_id IS set.
    - partial: candidate has explicit structured match but linkage.incident_id is None,
      OR candidate has partial incident context but no explicit match.
      incident_id is NOT set.
    - unlinked: no incident context or candidate relationship.
      incident_id is NOT set.

    Args:
        candidate_dict: The candidate dict to enrich.
        linkage: The linkage fields to inject.

    Returns:
        New dict with linkage fields added. Original dict is unchanged.
    """
    # Create a copy to avoid mutation
    enriched = dict(candidate_dict)

    # Check for explicit structured match
    has_explicit_match = _candidate_has_explicit_structured_match(candidate_dict, linkage)

    if has_explicit_match and linkage.incident_id is not None:
        # Candidate explicitly matches AND we have incident_id - stamp as linked
        enriched["incident_id"] = linkage.incident_id
        enriched["namespace"] = linkage.namespace
        enriched["objectKind"] = linkage.object_kind
        enriched["objectName"] = linkage.object_name
        enriched["candidateClass"] = linkage.candidate_class
        enriched["source_candidate_id"] = linkage.source_candidate_id
        enriched["linkage_status"] = "linked"
        enriched["linkage_reason"] = linkage.linkage_reason
    elif has_explicit_match:
        # Explicit match but no incident_id available - partial only
        enriched.pop("incident_id", None)
        enriched["linkage_status"] = "partial"
        enriched["linkage_reason"] = "explicit candidate match but incident_id is unavailable"
    else:
        # No explicit match
        enriched.pop("incident_id", None)

        if linkage.linkage_status == "linked":
            # Incident has context but candidate doesn't match explicitly
            enriched["linkage_status"] = "partial"
            enriched["linkage_reason"] = "incident context available but no explicit candidate match"
        else:
            # Use the linkage status as-is (partial or unlinked)
            enriched["linkage_status"] = linkage.linkage_status
            enriched["linkage_reason"] = linkage.linkage_reason

    return enriched


# =============================================================================
# Plan Dict Enrichment
# =============================================================================


def enrich_next_check_plan_dict(
    plan_dict: dict[str, Any],
    plan_linkage: NextCheckPlanLinkage,
) -> dict[str, Any]:
    """Enrich a plan dict with plan-level linkage fields.

    Args:
        plan_dict: The plan dict to enrich.
        plan_linkage: The plan-level linkage fields to inject.

    Returns:
        New dict with plan-level linkage fields added.
    """
    # Create a copy to avoid mutation
    enriched = dict(plan_dict)

    # Inject plan-level linkage fields
    plan_linkage_dict = plan_linkage.to_dict()
    for key, value in plan_linkage_dict.items():
        enriched[key] = value

    return enriched


__all__ = [
    "enrich_next_check_candidate_dict",
    "enrich_next_check_plan_dict",
]
