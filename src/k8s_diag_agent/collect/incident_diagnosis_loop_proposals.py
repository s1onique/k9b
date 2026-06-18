"""Next-check proposal extraction for incident diagnosis loop.

This module contains proposal extraction helpers.

Design constraints:
- Pure functions only
- No store mutation
- No LLM calls
- No Kubernetes calls
- No execution
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .incident_next_check_policy import DEFAULT_MAX_CHECKS_PER_PASS

# =============================================================================
# Proposal Extraction
# =============================================================================


def extract_next_check_proposals(
    diagnosis_report: Mapping[str, object],
    *,
    max_proposals: int = DEFAULT_MAX_CHECKS_PER_PASS,
) -> list[dict[str, Any]]:
    """Extract next-check proposals from diagnosis report.

    This is a conversion helper - does not make LLM calls.

    Args:
        diagnosis_report: The diagnosis report from build_incident_diagnosis()
        max_proposals: Maximum proposals to extract

    Returns:
        List of check proposal dicts
    """
    proposals: list[dict[str, Any]] = []

    # Extract from recommended_investigations
    diagnosis = diagnosis_report.get("diagnosis", {})
    investigations = diagnosis.get("recommended_investigations", [])

    for i, inv in enumerate(investigations[:max_proposals]):
        if isinstance(inv, str):
            proposals.append({
                "check_id": f"investigation_{i + 1}",
                "title": inv[:100] if len(inv) > 100 else inv,
                "rationale": inv,
                "priority": i + 1,
                "risk_level": "low",
                "read_only": True,
                "source": "llm-review",
            })
        elif isinstance(inv, dict):
            # Already a structured proposal
            proposals.append(dict(inv))

    return proposals


__all__ = [
    "extract_next_check_proposals",
]
