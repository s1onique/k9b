"""Execution provenance helpers for next-check candidates.

Extracted from next_check_planner_candidates.py to reduce file size.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .result_digest import ExecutionResultDigest

if TYPE_CHECKING:
    pass


def find_execution_result_for_candidate(
    candidate_text: str,
    execution_context: tuple[ExecutionResultDigest, ...],
) -> ExecutionResultDigest | None:
    """Find execution result that relates to the candidate.
    
    Attaches provenance only when there is meaningful overlap:
    - description overlap, or
    - signal overlap
    
    Cluster-only match is not sufficient for provenance attachment.
    
    Args:
        candidate_text: The candidate description text
        execution_context: Current execution context digests
    
    Returns:
        ExecutionResultDigest if a related execution was found, else None
    """
    if not execution_context:
        return None
    
    # Normalize candidate text for comparison
    candidate_lower = candidate_text.lower()
    
    for digest in execution_context:
        # Check description overlap (most reliable provenance signal)
        if digest.candidate_description:
            desc_lower = digest.candidate_description.lower()
            if candidate_lower in desc_lower or desc_lower in candidate_lower:
                return digest
        
        # Check signal overlap (second reliable signal)
        if digest.signals:
            for signal in digest.signals:
                if signal.lower() in candidate_lower:
                    return digest
    
    return None


def build_execution_provenance(
    execution_digest: ExecutionResultDigest,
) -> dict[str, Any]:
    """Build execution provenance dict from execution digest.
    
    Args:
        execution_digest: The execution result digest to convert
    
    Returns:
        Dictionary with execution provenance for candidate
    """
    return {
        "priorArtifact": execution_digest.artifact_path,
        "priorCandidateId": execution_digest.candidate_id,
        "priorCandidateDescription": execution_digest.candidate_description,
        "priorStatus": execution_digest.status,
        "priorUsefulnessClass": execution_digest.usefulness_class,
        "priorSummary": execution_digest.summary,
        "priorSignals": list(execution_digest.signals),
    }