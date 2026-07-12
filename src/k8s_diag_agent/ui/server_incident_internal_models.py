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
    """Response for promotion operations.

    The response exposes per-canonical-incident ``opened_incident_ids`` /
    ``updated_incident_ids`` plus a per-candidate ``promotion_records``
    list so that the scheduler can feed the backend-owned canonical
    ``incident_id`` values directly into automatic diagnosis. The
    ``source_candidate_id`` field is correlation metadata only and MUST
    NOT be used as the ``incident_id`` for downstream lookup.

    Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01
    """

    ok: bool = True
    scanned: int = 0
    firing: int = 0
    opened_incidents: int = 0
    updated_incidents: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    error_messages: list[str] = field(default_factory=list)
    # Canonical identity propagation
    opened_incident_ids: list[str] = field(default_factory=list)
    updated_incident_ids: list[str] = field(default_factory=list)
    promotion_records: list[dict[str, str | None]] = field(default_factory=list)
    unique_candidate_count: int = 0
    promotion_scan_scope: str = ""
    incident_access_mode: str = "backend"

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
            "error_messages": list(self.error_messages),
            "opened_incident_ids": list(self.opened_incident_ids),
            "updated_incident_ids": list(self.updated_incident_ids),
            "promotion_records": [dict(r) for r in self.promotion_records],
            "unique_candidate_count": self.unique_candidate_count,
            "promotion_scan_scope": self.promotion_scan_scope,
            "incident_access_mode": self.incident_access_mode,
        }

    @classmethod
    def from_promotion_result(
        cls,
        result: object,
        *,
        opened_ids: list[str],
        updated_ids: list[str],
        promotion_records: list[dict[str, str | None]],
        unique_candidate_count: int,
        promotion_scan_scope: str,
    ) -> PromotionResponse:
        """Build a PromotionResponse from a promotion result object.

        Accepts a duck-typed result to avoid an import cycle with
        ``incident_alert_promotion``. Only attribute names matching the
        existing aggregates are read.
        """
        return cls(
            ok=True,
            scanned=int(getattr(result, "scanned_signal_count", 0)),
            firing=int(getattr(result, "firing_signal_count", 0)),
            opened_incidents=int(getattr(result, "opened_incident_count", 0)),
            updated_incidents=int(getattr(result, "updated_incident_count", 0)),
            skipped_duplicates=int(getattr(result, "skipped_duplicate_count", 0)),
            errors=0,
            error_messages=[],
            opened_incident_ids=list(opened_ids),
            updated_incident_ids=list(updated_ids),
            promotion_records=[dict(r) for r in promotion_records],
            unique_candidate_count=unique_candidate_count,
            promotion_scan_scope=promotion_scan_scope,
        )
