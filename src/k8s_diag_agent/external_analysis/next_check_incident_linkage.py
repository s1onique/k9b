"""Compatibility facade for incident linkage fields.

This module re-exports all public symbols from the focused modules:
- next_check_incident_linkage_contracts (types/contracts)
- next_check_incident_linkage_builder (construction)
- next_check_incident_linkage_enrichment (dict enrichment)

All existing imports from this module continue to work unchanged.
"""

from __future__ import annotations

from .next_check_incident_linkage_builder import build_next_check_incident_linkage

# Re-export all public symbols from focused modules
from .next_check_incident_linkage_contracts import (
    LINKAGE_SCHEMA_VERSION,
    IncidentLinkageContext,
    LinkageStatus,
    NextCheckCandidateLinkage,
    NextCheckPlanLinkage,
)
from .next_check_incident_linkage_enrichment import (
    enrich_next_check_candidate_dict,
    enrich_next_check_plan_dict,
)

__all__ = [
    # From contracts
    "LinkageStatus",
    "IncidentLinkageContext",
    "NextCheckCandidateLinkage",
    "NextCheckPlanLinkage",
    "LINKAGE_SCHEMA_VERSION",
    # From builder
    "build_next_check_incident_linkage",
    # From enrichment
    "enrich_next_check_candidate_dict",
    "enrich_next_check_plan_dict",
]
