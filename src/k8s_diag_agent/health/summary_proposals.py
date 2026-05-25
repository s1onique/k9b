"""Proposal aggregation helpers for health summary building."""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .adaptation import HealthProposal
from .proposal_lifecycle_events import derive_current_proposal_status

logger = logging.getLogger(__name__)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Skipped malformed artifact: %s", path.name, exc_info=True)
        return {}
    if isinstance(raw, dict):
        return raw
    return {}


def load_all_proposals(proposals_dir: Path) -> list[HealthProposal]:
    """Load all proposals from the proposals directory.

    Args:
        proposals_dir: Directory containing proposal JSON files.

    Returns:
        List of HealthProposal objects.
    """
    proposals: list[HealthProposal] = []
    if not proposals_dir.is_dir():
        return proposals
    for path in sorted(proposals_dir.glob("*.json")):
        data = _load_json(path)
        if not data:
            continue
        try:
            proposals.append(HealthProposal.from_dict(data))
        except ValueError:
            continue
    return proposals


def collect_proposals_for_run(
    proposals: Iterable[HealthProposal],
    transitions_dir: Path | None,
    run_id: str,
) -> list[dict[str, Any]]:
    """Collect proposal summaries for a specific run.

    Args:
        proposals: Iterable of HealthProposal objects.
        transitions_dir: Directory containing transition event artifacts.
        run_id: The run identifier to filter proposals.

    Returns:
        List of proposal summary dicts with keys: proposal_id, target, rationale,
        confidence, source_run_id, lifecycle_status.
    """
    summaries: list[dict[str, Any]] = []
    for proposal in proposals:
        if proposal.source_run_id != run_id:
            continue
        # Use event-aware derivation for current status
        current_status = derive_current_proposal_status(proposal.to_dict(), transitions_dir)
        lifecycle_status = current_status.value
        summaries.append({
            "proposal_id": proposal.proposal_id,
            "target": proposal.target,
            "rationale": proposal.rationale,
            "confidence": proposal.confidence.value,
            "source_run_id": proposal.source_run_id,
            "lifecycle_status": lifecycle_status,
        })
    return summaries
