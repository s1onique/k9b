"""Contract/Type definitions for incident linkage fields.

This module contains pure data-shape definitions:
- LINKAGE_SCHEMA_VERSION
- IncidentLinkageContext
- NextCheckCandidateLinkage
- NextCheckPlanLinkage
- LinkageStatus type alias

No business logic, no file IO, no LLM calls.
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


__all__ = [
    "LinkageStatus",
    "IncidentLinkageContext",
    "NextCheckCandidateLinkage",
    "NextCheckPlanLinkage",
    "LINKAGE_SCHEMA_VERSION",
]
