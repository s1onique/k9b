"""Pure helper for enriching next-check candidates with incident linkage fields.

This module provides deterministic linkage field injection for next-check plan
artifacts. It does NOT:
- Perform file IO
- Call LLMs
- Access Kubernetes
- Make network requests
- Populate suggested_checks
- Execute checks

Design constraints:
- Pure functions only
- No file IO
- No provider/LLM calls
- No Kubernetes calls
- No store mutation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from ..collect.incident_candidates import IncidentCandidate


# =============================================================================
# Linkage Status
# =============================================================================


LinkageStatus = Literal["linked", "partial", "unlinked"]


# =============================================================================
# Linkage Context
# =============================================================================


@dataclass(frozen=True)
class IncidentLinkageContext:
    """Context for deriving incident linkage fields for next-check candidates.

    This is the input for build_next_check_incident_linkage(). It captures
    the available structured information about the incident associated with
    a run's diagnostic context.

    Attributes:
        incident_id: The incident's deterministic ID (namespace-kind-name-class).
            Available when a candidate incident record exists for this run.
        source_candidate_id: The original diagnostic candidate's stable ID.
        namespace: Kubernetes namespace of the entity.
        object_kind: Kind of the Kubernetes object (Pod, Deployment, etc.).
        object_name: Name of the Kubernetes object.
        candidate_class: Classification of the candidate (crash_loop, etc.).
        run_id: The run identifier (always available from plan artifact filename).
    """

    incident_id: str | None = None
    source_candidate_id: str | None = None
    namespace: str | None = None
    object_kind: str | None = None
    object_name: str | None = None
    candidate_class: str | None = None
    run_id: str | None = None

    @classmethod
    def from_incident_candidate(
        cls,
        candidate: IncidentCandidate,
        run_id: str | None = None,
    ) -> IncidentLinkageContext:
        """Create linkage context from an IncidentCandidate.

        This is the primary way to construct linkage context when an incident
        candidate exists for the run.

        Args:
            candidate: The IncidentCandidate to derive linkage from.
            run_id: Optional run identifier.

        Returns:
            IncidentLinkageContext with fields derived from the candidate.
        """
        # Import here to avoid circular imports at module level
        from ..collect.incident_lifecycle import incident_id_from_candidate

        return cls(
            incident_id=incident_id_from_candidate(candidate),
            source_candidate_id=candidate.candidate_id,
            namespace=candidate.namespace,
            object_kind=candidate.object_kind.value,
            object_name=candidate.object_name,
            candidate_class=candidate.candidate_class.value,
            run_id=run_id,
        )

    @classmethod
    def from_selection_context(
        cls,
        selection_label: str | None,
        selection_context: str | None,
        run_id: str | None = None,
    ) -> IncidentLinkageContext:
        """Create partial linkage context from review selection context.

        This captures cluster/namespace/entity context from review enrichment
        selections when full incident context is not available.

        Args:
            selection_label: The cluster label from the selection.
            selection_context: Additional context (namespace, object reference, etc.).
            run_id: The run identifier.

        Returns:
            IncidentLinkageContext with available structured fields.
        """
        # Parse namespace from context if present (e.g., "namespace=default, pod=my-pod")
        namespace: str | None = None
        object_kind: str | None = None
        object_name: str | None = None

        if selection_context:
            parts = selection_context.split(",")
            for part in parts:
                part = part.strip()
                if part.startswith("namespace="):
                    namespace = part.split("=", 1)[1].strip()
                elif part.startswith("pod=") or part.startswith("deployment="):
                    if "=" in part:
                        key, val = part.split("=", 1)
                        object_name = val.strip()
                        if key == "pod":
                            object_kind = "Pod"
                        elif key == "deployment":
                            object_kind = "Deployment"

        return cls(
            incident_id=None,
            source_candidate_id=None,
            namespace=namespace,
            object_kind=object_kind,
            object_name=object_name,
            candidate_class=None,
            run_id=run_id,
        )

    def determine_linkage_status(self) -> LinkageStatus:
        """Determine the linkage status based on available fields.

        Returns:
            - "linked": incident_id is present and sufficient for deterministic mapping
            - "partial": incident_id missing but enough structured fields for fallback
            - "unlinked": insufficient structured fields for any mapping
        """
        if self.incident_id is not None:
            return "linked"

        # Check for partial linkage: run_id + source_candidate_id, or complete entity identity
        has_run_id = self.run_id is not None
        has_source_candidate_id = self.source_candidate_id is not None
        has_entity_identity = all([
            self.namespace is not None,
            self.object_kind is not None,
            self.object_name is not None,
            self.candidate_class is not None,
        ])

        if (has_run_id and has_source_candidate_id) or has_entity_identity:
            return "partial"

        return "unlinked"

    def get_linkage_reason(self) -> str:
        """Get human-readable reason for the linkage status."""
        status = self.determine_linkage_status()
        if status == "linked":
            return f"Direct incident_id match: {self.incident_id}"
        elif status == "partial":
            parts = []
            if self.run_id and self.source_candidate_id:
                parts.append(f"run_id={self.run_id}")
            if all([self.namespace, self.object_kind, self.object_name, self.candidate_class]):
                parts.append("entity identity")
            return f"Partial linkage: {' + '.join(parts)}"
        else:
            return "No incident context available for linkage"


# =============================================================================
# Candidate Linkage Fields
# =============================================================================


@dataclass(frozen=True)
class NextCheckCandidateLinkage:
    """Linkage fields for a single next-check candidate."""

    incident_id: str | None
    source_candidate_id: str | None
    namespace: str | None
    object_kind: str | None
    object_name: str | None
    candidate_class: str | None
    linkage_status: LinkageStatus
    linkage_reason: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "incident_id": self.incident_id,
            "source_candidate_id": self.source_candidate_id,
            "namespace": self.namespace,
            "objectKind": self.object_kind,
            "objectName": self.object_name,
            "candidateClass": self.candidate_class,
            "linkage_status": self.linkage_status,
            "linkage_reason": self.linkage_reason,
        }

    @classmethod
    def from_context(
        cls,
        context: IncidentLinkageContext,
    ) -> NextCheckCandidateLinkage:
        """Build linkage fields from context.

        Args:
            context: The incident linkage context.

        Returns:
            NextCheckCandidateLinkage with fields copied from context.
        """
        return cls(
            incident_id=context.incident_id,
            source_candidate_id=context.source_candidate_id,
            namespace=context.namespace,
            object_kind=context.object_kind,
            object_name=context.object_name,
            candidate_class=context.candidate_class,
            linkage_status=context.determine_linkage_status(),
            linkage_reason=context.get_linkage_reason(),
        )


# =============================================================================
# Plan-Level Linkage Fields
# =============================================================================


LINKAGE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class NextCheckPlanLinkage:
    """Plan-level linkage fields."""

    linkage_schema_version: int = LINKAGE_SCHEMA_VERSION
    run_id: str | None = None
    linkage_status: LinkageStatus = "unlinked"
    linkage_reason: str = "No incident context available"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "linkage_schema_version": self.linkage_schema_version,
            "run_id": self.run_id,
            "linkage_status": self.linkage_status,
            "linkage_reason": self.linkage_reason,
        }

    @classmethod
    def from_context(
        cls,
        context: IncidentLinkageContext,
    ) -> NextCheckPlanLinkage:
        """Build plan-level linkage from context.

        Args:
            context: The incident linkage context.

        Returns:
            NextCheckPlanLinkage with aggregated linkage status.
        """
        linkage_status = context.determine_linkage_status()
        if linkage_status == "linked":
            reason = f"Plan linked to incident: {context.incident_id}"
        elif linkage_status == "partial":
            reason = f"Plan has partial incident context (run_id={context.run_id})"
        else:
            reason = "No incident context available for plan linkage"

        return cls(
            linkage_schema_version=LINKAGE_SCHEMA_VERSION,
            run_id=context.run_id,
            linkage_status=linkage_status,
            linkage_reason=reason,
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

    plan_linkage = NextCheckPlanLinkage.from_context(context)
    candidate_linkage = NextCheckCandidateLinkage.from_context(context)

    return (plan_linkage, candidate_linkage)


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
    "LinkageStatus",
    "IncidentLinkageContext",
    "NextCheckCandidateLinkage",
    "NextCheckPlanLinkage",
    "LINKAGE_SCHEMA_VERSION",
    "build_next_check_incident_linkage",
    "enrich_next_check_candidate_dict",
    "enrich_next_check_plan_dict",
]