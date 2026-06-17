"""Review packet state model for incident management.

This module contains:
- ReviewPacketStatus: enum for packet generation states
- ReviewPacketState: state that cannot drift (replaces available + id pattern)

Design notes:
- Replaces the old pattern of: review_packet_available: bool + review_packet_id: str | None
- The old pattern could produce: review_packet_available=True + review_packet_id=None (DRIFT!)
- This model makes state explicit and prevents drift
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ReviewPacketStatus(StrEnum):
    """Status of the review packet."""

    NOT_GENERATED = "not_generated"
    GENERATING = "generating"
    AVAILABLE = "available"
    FAILED = "failed"


@dataclass(frozen=True)
class ReviewPacketState:
    """Review packet state that cannot drift.

    Replaces the old pattern of:
        review_packet_available: bool
        review_packet_id: str | None

    The old pattern could produce:
        review_packet_available=True
        review_packet_id=None  # Drift!

    This model makes state explicit and prevents drift.

    Invariants enforced by __post_init__:
    - GENERATING and AVAILABLE require non-empty id
    """

    status: ReviewPacketStatus
    id: str | None = None
    generated_at: datetime | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        """Validate invariants: GENERATING/AVAILABLE require non-empty id."""
        if self.status in {ReviewPacketStatus.GENERATING, ReviewPacketStatus.AVAILABLE}:
            if not self.id:
                raise ValueError(f"{self.status.value} requires non-empty id")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status.value,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.generated_at is not None:
            result["generated_at"] = self.generated_at.isoformat()
        if self.error_message is not None:
            result["error_message"] = self.error_message
        return result

    @classmethod
    def not_generated(cls) -> ReviewPacketState:
        """Create a not_generated state."""
        return cls(status=ReviewPacketStatus.NOT_GENERATED)

    @classmethod
    def generating(cls, id: str) -> ReviewPacketState:
        """Create a generating state with artifact ID."""
        return cls(status=ReviewPacketStatus.GENERATING, id=id)

    @classmethod
    def available(cls, id: str, generated_at: datetime | None = None) -> ReviewPacketState:
        """Create an available state with artifact ID and optional generation time."""
        return cls(
            status=ReviewPacketStatus.AVAILABLE,
            id=id,
            generated_at=generated_at or datetime.now(UTC),
        )

    @classmethod
    def failed(cls, error_message: str | None = None) -> ReviewPacketState:
        """Create a failed state with optional error message."""
        return cls(status=ReviewPacketStatus.FAILED, error_message=error_message)


__all__ = [
    "ReviewPacketState",
    "ReviewPacketStatus",
]
