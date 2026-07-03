"""Scheduling evidence extraction helpers for LLM diagnosis.

Responsibility: Build scheduling evidence for prompts using durable structured
extraction that survives evidence boundary crossings.

This module depends only on simple stdlib types and existing contract modules.
It does NOT import incident_llm_diagnosis to avoid circular imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .incident_scheduling_root_cause import extract_scheduling_root_cause


def build_scheduling_evidence_for_prompt(
    incident: Mapping[str, object],
    events: list[object],
) -> dict[str, Any] | None:
    """Build scheduling evidence for the prompt using extract_scheduling_root_cause.

    This uses the durable structured evidence extraction that survives evidence
    boundary crossings in the diagnosis loop.

    Args:
        incident: Incident data from case file
        events: Events list from case file

    Returns:
        Scheduling evidence dict or None
    """
    # Build a minimal case file dict for extract_scheduling_root_cause
    # The function needs: incident + case_file (with events)
    case_file_for_extraction: dict[str, Any] = {
        "events": events,
    }

    try:
        # Pass incident dict (we have it as a Mapping, extract_scheduling_root_cause handles dict/object)
        scheduling_evidence = extract_scheduling_root_cause(
            incident=dict(incident),
            case_file=case_file_for_extraction,
        )

        if scheduling_evidence.root_cause_summary:
            return scheduling_evidence.to_dict()
    except Exception:
        # Fallback: don't let extraction failures break the prompt
        pass

    return None
