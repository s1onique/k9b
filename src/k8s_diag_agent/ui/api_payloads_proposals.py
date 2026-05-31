"""TypedDict payload definitions for proposal and lifecycle contracts.

This module contains pure data contracts (TypedDict definitions) for proposal
list and lifecycle entry responses.

Ownership:
    - All TypedDict payload classes defined here represent API response contracts.
    - JSON key names, optional vs required fields, and field types are frozen.
    - Serialization logic lives in api.py and related modules.

Extraction rationale:
    - Proposal/lifecycle contracts are used primarily by the proposals view.
    - Extracting them establishes the proposal contract boundary.
    - Keeping proposal contracts in a dedicated module makes it easier to
      audit proposal API contracts without filtering through unrelated payloads.
    - RatingCount and StatusCount are co-located here because all current
      consumers are proposal/lifecycle payloads.
"""

from __future__ import annotations

from typing import TypedDict

from .api_payloads_primitives import ArtifactLink

__all__ = [
    "ArtifactLink",
    "RatingCount",
    "StatusCount",
    "ProposalSummaryPayload",
    "LifecycleEntry",
    "ProposalEntry",
    "ProposalsPayload",
]


class RatingCount(TypedDict):
    """A rating count bucket."""

    rating: str
    count: int


class StatusCount(TypedDict):
    """A status count bucket."""

    status: str
    count: int


class ProposalSummaryPayload(TypedDict):
    """Payload for proposal summary in fleet view."""

    pending: int
    total: int
    statusCounts: list[StatusCount]


class LifecycleEntry(TypedDict):
    """A single lifecycle status entry for a proposal."""

    status: str
    timestamp: str
    note: str | None


class ProposalEntry(TypedDict):
    """Payload for a single proposal entry."""

    proposalId: str
    target: str
    status: str
    confidence: str
    rationale: str
    expectedBenefit: str
    sourceRunId: str
    latestNote: str | None
    lifecycle: list[LifecycleEntry]
    artifacts: list[ArtifactLink]
    # Immutable artifact identity (UUIDv7); None for legacy artifacts
    artifactId: str | None


class ProposalsPayload(TypedDict):
    """Payload for the proposals list response."""

    statusSummary: list[StatusCount]
    proposals: list[ProposalEntry]
