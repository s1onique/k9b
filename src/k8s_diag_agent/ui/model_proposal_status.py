"""Proposal status summary model extracted from model.py.

This module contains ProposalStatusSummary and its builder extracted from model.py
to enable focused modularization while preserving behavior and import compatibility.

Symbols extracted:
- ProposalStatusSummary: dataclass for aggregated proposal status counts
- _build_proposal_status_summary: builder for ProposalStatusSummary from Mapping
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .model_primitives import (
    _coerce_int,
    _coerce_str,
)


@dataclass(frozen=True)
class ProposalStatusSummary:
    """View model for aggregated proposal status counts."""

    status_counts: tuple[tuple[str, int], ...]


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
