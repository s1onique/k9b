"""Pure helper module for extracting suggested checks from next-check plan artifacts.

This module provides read-only extraction logic for populating
IncidentDetailPayload.suggested_checks from next-check plan artifacts.

Design constraints:
- Pure functions only
- No file IO (accepts pre-loaded plan payloads)
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution, promotion, or remediation

SAFE extraction rule:
Only candidates where linkage_status="linked" AND incident_id matches current incident.

Scope:
- Extract from plan artifact payload (pre-loaded by caller)
- Map candidate fields to IncidentSuggestedCheckPayload
- Preserve old artifact compatibility (no linkage fields → no suggestions)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api_payloads_incident_reads import IncidentSuggestedCheckPayload

__all__ = [
    "build_suggested_checks_from_next_check_plan_payload",
    "build_suggested_check_from_linked_candidate",
]


# =============================================================================
# Pure Extraction Helpers
# =============================================================================


def build_suggested_check_from_linked_candidate(
    incident_id: str,
    candidate: Mapping[str, object] | object,
    artifact_id: str | None = None,
    run_id: str | None = None,
) -> IncidentSuggestedCheckPayload | None:
    """Build a single suggested check from a linked candidate.

    This function implements the SAFE filter:
    - linkage_status must be "linked"
    - incident_id must be present and match the current incident_id

    Args:
        incident_id: The incident ID to match against
        candidate: Mapping with candidate fields (from plan payload)
        artifact_id: Optional artifact ID for provenance
        run_id: Optional run ID for provenance

    Returns:
        IncidentSuggestedCheckPayload if candidate is safely linked, None otherwise

    The following mappings are used:
    - check_id: candidate["candidateId"] or deterministic fallback
    - title: candidate["title"] or first line of description or "Suggested check"
    - rationale: candidate["rationale"] or candidate["description"] or linkage_reason or default
    - source: "next-check-plan"
    - risk_level: candidate["riskLevel"] or candidate["risk_level"] or None
    - status: "suggested"
    - artifact_id: artifact_id parameter or None
    - run_id: run_id parameter or None
    """
    # Guard: must be a Mapping
    if not isinstance(candidate, Mapping):
        return None

    # Apply SAFE filter: linkage_status must be "linked"
    linkage_status = candidate.get("linkage_status")
    if linkage_status != "linked":
        return None

    # Apply SAFE filter: incident_id must be present
    candidate_incident_id = candidate.get("incident_id")
    if not candidate_incident_id:
        return None

    # Apply SAFE filter: incident_id must match
    if candidate_incident_id != incident_id:
        return None

    # Build check_id: prefer candidateId, fallback to deterministic index-based ID
    check_id = _safe_get_str(candidate, "candidateId") or _safe_get_str(
        candidate, "candidate_id"
    )
    if not check_id:
        # Deterministic fallback: use source_candidate_id or "unknown"
        check_id = _safe_get_str(candidate, "source_candidate_id") or "unknown-check"

    # Build title: title > description first line > default
    title = _safe_get_str(candidate, "title")
    if not title:
        description = _safe_get_str(candidate, "description")
        if description:
            title = description.split("\n")[0].strip() or "Suggested check"
        else:
            title = "Suggested check"

    # Build rationale: rationale > description > linkage_reason > default
    rationale = _safe_get_str(candidate, "rationale")
    if not rationale:
        rationale = _safe_get_str(candidate, "description")
    if not rationale:
        rationale = _safe_get_str(candidate, "linkage_reason")
    if not rationale:
        rationale = "Linked by incident_id"

    # Build risk_level: riskLevel or risk_level
    risk_level: str | None = None
    risk_val = candidate.get("riskLevel") or candidate.get("risk_level")
    if isinstance(risk_val, str) and risk_val:
        risk_level = risk_val

    result: IncidentSuggestedCheckPayload = {
        "check_id": check_id,
        "title": title,
        "rationale": rationale,
        "source": "next-check-plan",
        "risk_level": risk_level,
        "status": "suggested",
        "artifact_id": artifact_id,
        "run_id": run_id,
    }

    return result


def build_suggested_checks_from_next_check_plan_payload(
    incident_id: str,
    plan_payload: Mapping[str, object],
) -> list[IncidentSuggestedCheckPayload]:
    """Extract suggested checks from a next-check plan payload.

    This function iterates over candidates in the plan payload and extracts
    only those where linkage_status="linked" and incident_id matches.

    Args:
        incident_id: The incident ID to match against
        plan_payload: Mapping with plan-level and candidates fields

    Returns:
        List of IncidentSuggestedCheckPayload for safely linked candidates

    Compatibility:
    - Plan payloads without candidates key: returns empty list
    - Candidates without linkage fields: ignored (no linkage_status="linked")
    - Candidates with linkage_status != "linked": ignored
    - Candidates with non-matching incident_id: ignored
    - Malformed candidates: safely skipped (no crash)

    This function does NOT mutate the input payload.
    """
    suggested_checks: list[IncidentSuggestedCheckPayload] = []

    # Get plan-level fields for provenance
    artifact_id: str | None = None
    run_id: str | None = None

    # Extract from plan-level if available
    plan_run_id = plan_payload.get("run_id")
    if isinstance(plan_run_id, str):
        run_id = plan_run_id

    # Get candidates list
    candidates = plan_payload.get("candidates")
    if not isinstance(candidates, list):
        return suggested_checks

    # Process each candidate
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            # Skip non-mapping entries (malformed candidate)
            continue

        # Build suggested check from linked candidate
        check = build_suggested_check_from_linked_candidate(
            incident_id=incident_id,
            candidate=candidate,
            artifact_id=artifact_id,
            run_id=run_id,
        )
        if check is not None:
            suggested_checks.append(check)

    return suggested_checks


# =============================================================================
# Internal Safe Helpers
# =============================================================================


def _safe_get_str(mapping: Mapping[str, object], key: str) -> str | None:
    """Safely get a string value from a mapping.

    Returns None if key is missing or value is not a non-empty string.
    Does not mutate the input mapping.
    """
    value = mapping.get(key)
    if isinstance(value, str) and value:
        return value
    return None