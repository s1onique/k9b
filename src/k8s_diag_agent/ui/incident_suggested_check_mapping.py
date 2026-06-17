"""Pure discovery module for next-check-to-incident mapping classification.

This module provides classification functions for determining whether a
next-check candidate can be deterministically linked to an Incident record.

Design constraints:
- Pure functions only
- No file IO
- No store mutation
- No API population
- No LLM calls
- No Kubernetes calls

Scope:
- Classification only (discovery, not implementation)
- Does not populate suggested_checks
- Does not implement execution, promotion, or remediation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "MappingConfidence",
    "MappingDecision",
    "classify_next_check_mapping_candidate",
    "explain_next_check_mapping_candidate",
]


# =============================================================================
# Type Definitions
# =============================================================================


MappingConfidence = Literal["safe", "conditionally_safe", "ambiguous", "unsafe"]


@dataclass(frozen=True)
class MappingDecision:
    """Decision result for a next-check-to-incident mapping candidate."""

    confidence: MappingConfidence
    reason: str
    required_fields: tuple[str, ...]
    matched_incident_id: str | None

    def is_safe(self) -> bool:
        """Return True if mapping is safe to use."""
        return self.confidence == "safe"

    def is_usable(self) -> bool:
        """Return True if mapping has any usable confidence level."""
        return self.confidence in ("safe", "conditionally_safe")

    def requires_fields(self, *fields: str) -> bool:
        """Check if all specified fields are available."""
        return all(f in self.required_fields for f in fields)


# =============================================================================
# Classification Logic
# =============================================================================


def classify_next_check_mapping_candidate(
    next_check_candidate: dict,
    incidents: list[dict],
) -> MappingDecision:
    """Classify the mapping confidence for a next-check candidate to incidents.

    This function evaluates possible mapping keys and returns a classification
    based on field availability and uniqueness guarantees.

    Args:
        next_check_candidate: Dict with next-check candidate fields
        incidents: List of incident dicts to match against

    Returns:
        MappingDecision with confidence level and reasoning

    Classification rules:
    - safe: Direct incident_id match with no ambiguity
    - conditionally_safe: run_id + source_candidate_id match with uniqueness
    - ambiguous: Entity-only match or bundle-only match with multiple candidates
    - unsafe: Text similarity or missing required fields
    """
    # Strategy 1: Direct incident_id match
    if _has_direct_incident_id_match(next_check_candidate, incidents):
        incident_id = next_check_candidate.get("incident_id") or next_check_candidate.get(
            "incidentId"
        )
        return MappingDecision(
            confidence="safe",
            reason="Direct incident_id match found",
            required_fields=("incident_id",),
            matched_incident_id=incident_id,
        )

    # Strategy 2: run_id + candidateId match
    run_id_match_result = _count_run_and_candidate_id_matches(
        next_check_candidate, incidents
    )
    if run_id_match_result is not None:
        run_id = _get_run_id_from_candidate(next_check_candidate)
        candidate_id = next_check_candidate.get("candidateId") or next_check_candidate.get(
            "candidate_id"
        )
        if run_id_match_result == 0:
            # No match - fall through
            pass
        elif run_id_match_result == 1:
            # Unique match - conditionally safe
            return MappingDecision(
                confidence="conditionally_safe",
                reason=f"Unique match on run_id={run_id} + candidate_id={candidate_id}",
                required_fields=("run_id", "candidateId"),
                matched_incident_id=_find_incident_by_run_and_candidate(
                    next_check_candidate, incidents
                ),
            )
        else:
            # Multiple matches - ambiguous
            return MappingDecision(
                confidence="ambiguous",
                reason=f"Multiple incidents match run_id={run_id} + candidate_id={candidate_id}",
                required_fields=("run_id", "candidateId"),
                matched_incident_id=None,
            )

    # Strategy 3: Entity identity match (namespace + kind + name + class)
    # Only proceed if we have complete entity identity (all 4 fields)
    entity_match_result = _has_complete_entity_identity_match(next_check_candidate, incidents)
    if entity_match_result is not None:
        matching_ids, is_complete = entity_match_result
        if not is_complete:
            # Partial entity identity - ambiguous, not conditionally safe
            return MappingDecision(
                confidence="ambiguous",
                reason="Partial entity identity match (requires namespace + kind + name + class)",
                required_fields=("namespace", "objectKind", "objectName", "candidateClass"),
                matched_incident_id=None,
            )
        elif len(matching_ids) == 1:
            # Complete entity identity with unique match - conditionally safe
            return MappingDecision(
                confidence="conditionally_safe",
                reason="Unique entity identity match (namespace/kind/name/class)",
                required_fields=("namespace", "objectKind", "objectName", "candidateClass"),
                matched_incident_id=matching_ids[0],
            )
        else:
            # Multiple matches - ambiguous
            return MappingDecision(
                confidence="ambiguous",
                reason=f"Entity identity matches {len(matching_ids)} incidents",
                required_fields=("namespace", "objectKind", "objectName", "candidateClass"),
                matched_incident_id=None,
            )

    # Strategy 4: Bundle-only match
    if _has_bundle_match(next_check_candidate, incidents):
        return MappingDecision(
            confidence="ambiguous",
            reason="Match only via bundle_id - bundle may contain multiple incidents",
            required_fields=("latest_snapshot_bundle_id",),
            matched_incident_id=None,
        )

    # Strategy 5: Text-only or description match
    if _has_text_match_only(next_check_candidate):
        return MappingDecision(
            confidence="unsafe",
            reason="Text similarity match is not deterministic",
            required_fields=(),
            matched_incident_id=None,
        )

    # Strategy 6: Missing required fields
    return MappingDecision(
        confidence="unsafe",
        reason="Insufficient fields for deterministic mapping",
        required_fields=("incident_id",),
        matched_incident_id=None,
    )


def explain_next_check_mapping_candidate(
    next_check_candidate: dict,
    incidents: list[dict],
) -> str:
    """Return a human-readable explanation of the mapping decision.

    Args:
        next_check_candidate: Dict with next-check candidate fields
        incidents: List of incident dicts to match against

    Returns:
        String explanation suitable for docs or debugging
    """
    decision = classify_next_check_mapping_candidate(next_check_candidate, incidents)

    lines = [
        f"Mapping confidence: {decision.confidence}",
        f"Reason: {decision.reason}",
    ]

    if decision.required_fields:
        lines.append(f"Required fields: {', '.join(decision.required_fields)}")

    if decision.matched_incident_id:
        lines.append(f"Matched incident_id: {decision.matched_incident_id}")
    else:
        lines.append("Matched incident_id: None")

    return "\n".join(lines)


# =============================================================================
# Internal Classification Helpers
# =============================================================================


def _has_direct_incident_id_match(
    candidate: dict, incidents: list[dict]
) -> bool:
    """Check if candidate has a direct incident_id field."""
    incident_id = candidate.get("incident_id") or candidate.get("incidentId")
    if not incident_id:
        return False
    return any(i.get("incident_id") == incident_id for i in incidents)


def _count_run_and_candidate_id_matches(
    candidate: dict, incidents: list[dict]
) -> int | None:
    """Count incidents matching run_id + candidateId.

    Returns the count of matching incidents, or None if run_id or candidate_id
    are not available in the candidate.
    """
    run_id = _get_run_id_from_candidate(candidate)
    candidate_id = candidate.get("candidateId") or candidate.get("candidate_id")

    if not run_id or not candidate_id:
        return None

    # Count matching incidents
    count = sum(
        1
        for i in incidents
        if _incident_has_signal_run_id(i, run_id)
        and i.get("source_candidate_id") == candidate_id
    )

    return count


def _get_run_id_from_candidate(candidate: dict) -> str | None:
    """Extract run_id from candidate (from filename or explicit field)."""
    # Explicit field
    if candidate.get("run_id") or candidate.get("runId"):
        return str(candidate.get("run_id") or candidate.get("runId"))

    # From artifact path: runs/health/external-analysis/{run_id}-next-check-*.json
    artifact_path = candidate.get("artifactPath") or candidate.get("artifact_path")
    if artifact_path and "-next-check" in artifact_path:
        # Extract run_id from filename prefix
        filename = artifact_path.split("/")[-1]
        for suffix in [
            "-next-check-plan",
            "-next-check-execution",
            "-next-check-approval",
            "-next-check-promotion",
        ]:
            if suffix in filename:
                parts = filename.split(suffix)
                return str(parts[0]) if parts else None
    return None


def _incident_has_signal_run_id(incident: dict, run_id: str) -> bool:
    """Check if incident has a signal with matching run_id."""
    signals = incident.get("signals", [])
    return any(s.get("run_id") == run_id for s in signals)


def _find_incident_by_run_and_candidate(
    candidate: dict, incidents: list[dict]
) -> str | None:
    """Find incident by run_id + candidate_id match."""
    run_id = _get_run_id_from_candidate(candidate)
    candidate_id = candidate.get("candidateId") or candidate.get("candidate_id")

    if not run_id or not candidate_id:
        return None

    for incident in incidents:
        if _incident_has_signal_run_id(incident, run_id) and incident.get(
            "source_candidate_id"
        ) == candidate_id:
            inc_id = incident.get("incident_id")
            if inc_id is not None:
                return str(inc_id)
    return None


def _has_complete_entity_identity_match(
    candidate: dict, incidents: list[dict]
) -> tuple[list[str], bool] | None:
    """Check if candidate has complete entity identity fields matching incident(s).

    Returns tuple of (matching incident_ids, is_complete) or None if no entity fields present.

    A complete entity identity requires ALL four fields:
    - namespace
    - objectKind/object_kind
    - objectName/object_name
    - candidateClass/candidate_class

    If only partial entity identity is present, is_complete is False and caller
    should classify as ambiguous, never conditionally_safe.
    """
    # Extract entity identity from candidate
    namespace = candidate.get("namespace")
    object_kind = candidate.get("objectKind") or candidate.get("object_kind")
    object_name = candidate.get("objectName") or candidate.get("object_name")
    candidate_class = candidate.get("candidateClass") or candidate.get("candidate_class")

    # Count how many entity fields are present
    present_fields = sum(1 for f in [namespace, object_kind, object_name, candidate_class] if f)

    # If no entity fields present, can't match at all
    if present_fields == 0:
        return None

    # If only partial entity identity, is_complete is False
    # Caller should classify as ambiguous, never conditionally_safe
    is_complete = present_fields == 4

    # Match against incidents
    matches: list[str] = []
    for incident in incidents:
        namespace_match = not namespace or incident.get("namespace") == namespace
        kind_match = not object_kind or incident.get("object_kind") == object_kind
        name_match = not object_name or incident.get("object_name") == object_name
        class_match = not candidate_class or incident.get("candidate_class") == candidate_class

        if namespace_match and kind_match and name_match and class_match:
            inc_id = incident.get("incident_id")
            if inc_id is not None:
                matches.append(str(inc_id))

    return (matches, is_complete) if matches else None


def _has_bundle_match(candidate: dict, incidents: list[dict]) -> bool:
    """Check if candidate matches incident only via bundle_id."""
    bundle_id = candidate.get("latest_snapshot_bundle_id") or candidate.get(
        "snapshot_bundle_id"
    )
    if not bundle_id:
        return False

    # Count incidents matching this bundle
    matching = [i for i in incidents if i.get("latest_snapshot_bundle_id") == bundle_id]

    # If bundle exists and matches incidents, consider it
    return len(matching) > 0


def _has_text_match_only(candidate: dict) -> bool:
    """Check if only text fields are available for matching."""
    text_fields = [
        "description",
        "title",
        "message",
        "sourceReason",
        "source_reason",
        "summary",
    ]
    return any(candidate.get(f) for f in text_fields) and not _has_structured_identity(
        candidate
    )


def _has_structured_identity(candidate: dict) -> bool:
    """Check if candidate has structured identity fields."""
    return any(
        [
            candidate.get("incident_id"),
            candidate.get("incidentId"),
            candidate.get("candidateId"),
            candidate.get("candidate_id"),
            candidate.get("namespace"),
            candidate.get("objectKind"),
            candidate.get("object_name"),
        ]
    )
