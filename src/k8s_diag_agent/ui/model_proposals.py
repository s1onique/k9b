"""Proposal view models and builders extracted from model.py.

This module contains proposal-related UI model types extracted from model.py
to enable focused modularization while preserving behavior and import compatibility.

Symbols extracted:
- ProposalView: proposal dataclass
- ProposalStatusSummary: proposal status aggregation dataclass
- _build_proposal_view: builder for ProposalView from Mapping
- _build_proposal_status_summary: builder for ProposalStatusSummary from Mapping
- _build_lifecycle_history: helper for proposal lifecycle tuple construction
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_optional_str,
    _coerce_str,
)


@dataclass(frozen=True)
class ProposalView:
    """View model for a single proposal."""

    proposal_id: str
    target: str
    status: str
    confidence: str
    rationale: str
    expected_benefit: str
    source_run_id: str
    latest_note: str | None
    artifact_path: str | None
    review_path: str | None
    lifecycle_history: tuple[tuple[str, str, str | None], ...]
    artifact_id: str | None = None  # Immutable artifact identity (UUIDv7); None for legacy


@dataclass(frozen=True)
class ProposalStatusSummary:
    """View model for aggregated proposal status counts."""

    status_counts: tuple[tuple[str, int], ...]


def _build_proposal_view(proposal: Mapping[str, object]) -> ProposalView:
    """Build a ProposalView from raw proposal data.

    Args:
        proposal: Raw proposal data mapping

    Returns:
        ProposalView constructed from the raw data
    """
    history = proposal.get("lifecycle_history") or []
    latest_entry = history[-1] if isinstance(history, Sequence) and history else None
    note = _coerce_str(latest_entry.get("note")) if latest_entry and isinstance(latest_entry, Mapping) and latest_entry.get("note") else None
    if note == "-":
        note = None
    lifecycle_history = _build_lifecycle_history(history)
    return ProposalView(
        proposal_id=_coerce_str(proposal.get("proposal_id")),
        target=_coerce_str(proposal.get("target")),
        status=_coerce_str(proposal.get("status")),
        confidence=_coerce_str(proposal.get("confidence")),
        rationale=_coerce_str(proposal.get("rationale")),
        expected_benefit=_coerce_str(proposal.get("expected_benefit")),
        source_run_id=_coerce_str(proposal.get("source_run_id")),
        latest_note=note,
        artifact_path=_coerce_optional_str(proposal.get("artifact_path")),
        review_path=_coerce_optional_str(proposal.get("review_artifact")),
        lifecycle_history=lifecycle_history,
        artifact_id=_coerce_optional_str(proposal.get("artifact_id")),
    )


def _build_proposal_status_summary(raw: object | None) -> ProposalStatusSummary:
    """Build a ProposalStatusSummary from raw proposal status summary data.

    Args:
        raw: Raw proposal status summary data or None

    Returns:
        ProposalStatusSummary with aggregated status counts
    """
    if not isinstance(raw, Mapping):
        return ProposalStatusSummary(status_counts=())
    counts_raw = raw.get("status_counts") or ()
    status_counts = tuple(
        (_coerce_str(entry.get("status")), _coerce_int(entry.get("count")))
        for entry in counts_raw
        if isinstance(entry, Mapping)
    )
    return ProposalStatusSummary(status_counts=status_counts)


def _build_lifecycle_history(raw: object | None) -> tuple[tuple[str, str, str | None], ...]:
    """Build a tuple of (status, timestamp, note) tuples from raw lifecycle history data.

    Args:
        raw: Raw lifecycle history data (list/dict or None)

    Returns:
        Tuple of (status, timestamp, note) tuples. Empty tuple if input is not a Sequence.
    """
    entries: list[tuple[str, str, str | None]] = []
    if not isinstance(raw, Sequence):
        return ()
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        status = _coerce_str(entry.get("status"))
        timestamp = _coerce_str(entry.get("timestamp"))
        note = _coerce_optional_str(entry.get("note"))
        if note == "-":
            note = None
        entries.append((status, timestamp, note))
    return tuple(entries)
