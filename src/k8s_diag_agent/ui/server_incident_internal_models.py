"""Request/Response models for internal API endpoints.

Models for the scheduler-to-backend promotion API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class PromoteAlertSignalsRequest:
    """Request body for alert signal promotion."""

    candidates: list[dict[str, Any]]
    observed_at: str
    snapshot_bundle_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromoteAlertSignalsRequest:
        """Parse request from dict."""
        return cls(
            candidates=data.get("candidates", []),
            observed_at=data.get("observed_at", datetime.now(UTC).isoformat()),
            snapshot_bundle_id=data.get("snapshot_bundle_id"),
        )


@dataclass
class PromoteCandidatesRequest:
    """Request body for incident candidate promotion."""

    candidates: list[dict[str, Any]]
    observed_at: str
    snapshot_bundle_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromoteCandidatesRequest:
        """Parse request from dict."""
        return cls(
            candidates=data.get("candidates", []),
            observed_at=data.get("observed_at", datetime.now(UTC).isoformat()),
            snapshot_bundle_id=data.get("snapshot_bundle_id"),
        )


@dataclass
class PromotionResponse:
    """Response for promotion operations."""

    ok: bool = True
    scanned: int = 0
    firing: int = 0
    opened_incidents: int = 0
    updated_incidents: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON response."""
        return {
            "ok": self.ok,
            "scanned": self.scanned,
            "firing": self.firing,
            "opened_incidents": self.opened_incidents,
            "updated_incidents": self.updated_incidents,
            "skipped_duplicates": self.skipped_duplicates,
            "errors": self.errors,
            "error_messages": self.error_messages,
        }
