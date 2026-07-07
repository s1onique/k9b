"""Alertmanager source promotion review packet - pre-promotion safety check.

This module provides the promotion review packet that is shown to the operator
BEFORE they confirm a "Promote" action. This prevents the bad UX where a user
can promote two aliases independently and accidentally create duplicated polling/tracking.

Schema version: k9b.alertmanager_source.promotion_review.v1

Design rationale:
- Promotion is an irreversible action that makes a source authoritative
- The review packet shows what WILL be created and which aliases will be affected
- This prevents duplicate tracking and provides an audit trail
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..identity.artifact import new_artifact_id

# Schema version for the promotion review packet format
SCHEMA_VERSION = "k9b.alertmanager_source.promotion_review.v1"


@dataclass(frozen=True)
class TrackedSourceSpec:
    """Specification for the tracked source that will be created by promotion."""
    endpoint_url: str
    identity_hash: str | None  # SHA256 of identity fields
    cluster: str | None
    namespace: str | None
    name: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_url": self.endpoint_url,
            "identity_hash": self.identity_hash,
            "cluster": self.cluster,
            "namespace": self.namespace,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrackedSourceSpec:
        return cls(
            endpoint_url=str(data.get("endpoint_url", "")),
            identity_hash=data.get("identity_hash"),
            cluster=data.get("cluster"),
            namespace=data.get("namespace"),
            name=data.get("name"),
        )


@dataclass(frozen=True)
class AliasSourceSpec:
    """Specification for an alias source that will be affected by promotion."""
    source_id: str
    reason: str  # Human-readable reason why this is an alias

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AliasSourceSpec:
        return cls(
            source_id=str(data.get("source_id", "")),
            reason=str(data.get("reason", "")),
        )


@dataclass(frozen=True)
class PromotionRisk:
    """A potential risk or consideration for the promotion action."""
    risk_id: str  # e.g., "duplicate_tracking", "alias_conflict"
    severity: str  # "info", "warning", "error"
    description: str
    mitigation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "severity": self.severity,
            "description": self.description,
            "mitigation": self.mitigation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromotionRisk:
        return cls(
            risk_id=str(data.get("risk_id", "")),
            severity=str(data.get("severity", "info")),
            description=str(data.get("description", "")),
            mitigation=data.get("mitigation"),
        )


@dataclass(frozen=True)
class AlertmanagerSourcePromotionReview:
    """Pre-promotion review packet for an Alertmanager source.
    
    This packet is shown to the operator BEFORE they confirm a "Promote" action.
    It provides:
    - What WILL be created (the tracked source)
    - Which aliases will be affected
    - Any risks or considerations
    - The redaction policy applied
    
    This prevents:
    - Accidental duplicate tracking when promoting two aliases
    - Unintended mutation of tracked sources
    - Loss of audit trail for promotion decisions
    """
    # Fields without defaults must come first
    source_id: str
    promotable: bool
    # Fields with defaults follow
    schema_version: str = SCHEMA_VERSION
    artifact_id: str = field(default_factory=new_artifact_id)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    will_create: TrackedSourceSpec | None = None  # None if not promotable
    aliases: tuple[AliasSourceSpec, ...] = field(default_factory=tuple)
    risks: tuple[PromotionRisk, ...] = field(default_factory=tuple)
    redactions: dict[str, str] = field(default_factory=lambda: {
        "alertmanager_config": "sha256_only",
        "annotations": "secret_like_values_redacted",
        "tokens": "redacted",
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_id": self.artifact_id,
            "generated_at": self.generated_at.isoformat(),
            "source_id": self.source_id,
            "promotable": self.promotable,
            "will_create": self.will_create.to_dict() if self.will_create else None,
            "aliases": [a.to_dict() for a in self.aliases],
            "risks": [r.to_dict() for r in self.risks],
            "redactions": dict(self.redactions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlertmanagerSourcePromotionReview:
        generated_at = data.get("generated_at")
        if isinstance(generated_at, str):
            try:
                if generated_at.endswith("Z"):
                    generated_at = f"{generated_at[:-1]}+00:00"
                generated_at = datetime.fromisoformat(generated_at)
            except ValueError:
                generated_at = datetime.now(UTC)
        elif generated_at is None:
            generated_at = datetime.now(UTC)

        will_create = None
        if data.get("will_create") and isinstance(data["will_create"], dict):
            will_create = TrackedSourceSpec.from_dict(data["will_create"])

        return cls(
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            artifact_id=str(data.get("artifact_id", "")),
            generated_at=generated_at,
            source_id=str(data.get("source_id", "")),
            promotable=bool(data.get("promotable", False)),
            will_create=will_create,
            aliases=tuple(AliasSourceSpec.from_dict(a) for a in data.get("aliases", []) if isinstance(a, dict)),
            risks=tuple(PromotionRisk.from_dict(r) for r in data.get("risks", []) if isinstance(r, dict)),
            redactions=dict(data.get("redactions", {
                "alertmanager_config": "sha256_only",
                "annotations": "secret_like_values_redacted",
                "tokens": "redacted",
            })),
        )


__all__ = [
    "SCHEMA_VERSION",
    "TrackedSourceSpec",
    "AliasSourceSpec",
    "PromotionRisk",
    "AlertmanagerSourcePromotionReview",
]
