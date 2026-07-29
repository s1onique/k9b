"""Cycle-free ``IncidentPromotionResult`` contract.

ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01.

The dispatcher module
(:mod:`k8s_diag_agent.collect.incident_promotion_dispatch`) imports
the typed accumulator host
(:class:`k8s_diag_agent.collect.RunPromotionAccumulator`) so
the split atomic recorder modules cannot import the dispatcher
without closing an import cycle. This module owns the
canonical :class:`IncidentPromotionResult` value object used by
the scoped atomic recorder, the validator, the projection,
and the compatibility wrappers.

The dispatcher module re-exports
:class:`IncidentPromotionResult` for backward compatibility;
new callers should import directly from this cycle-free
module so the typed boundary between the active scoped
recorder and the dispatcher is statically enforced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# Strings that participate in compatibility/accounting checks
# only and MUST agree with :mod:`incident_promotion_dispatch_constants`.
SCAN_SCOPE_INTERNAL_API_ALERT_SIGNALS_SCOPED: Literal[
    "internal_api_alert_signals:scoped"
] = "internal_api_alert_signals:scoped"

RECONCILIATION_REQUIRED_ACCESS_MODE: Literal[
    "reconciliation_required"
] = "reconciliation_required"

PROMOTION_MODE_LOCAL: Literal["local"] = "local"
PROMOTION_MODE_BACKEND_API: Literal["backend-api"] = "backend-api"
INCIDENT_ACCESS_MODE_LOCAL: Literal["local"] = "local"
INCIDENT_ACCESS_MODE_BACKEND: Literal["backend"] = "backend"


@dataclass(frozen=True)
class IncidentPromotionResult:
    """Bounded aggregate result of one promotion attempt.

    The result exposes per-canonical-incident ``opened_incident_ids`` /
    ``updated_incident_ids`` plus a per-candidate ``promotion_records``
    mapping so that downstream callers (notably automatic diagnosis) can
    consume canonical ``incident_id`` values directly without
    re-deriving them from candidate attributes.

    ACT-K9B-HULK-PROMOTION-SCOPED-RECORDING-AUTHORITY-AND-EVIDENCE-CLOSURE01:
    the active scoped recorder and validator use this frozen dataclass
    as the typed return surface of the batch envelope
    (:attr:`PromotionBatch.promotion_result`). The split atomic
    recorder modules NEVER type the result as ``object`` /
    ``Any``; the contract module is the single canonical boundary.
    """

    ok: bool = True
    scanned: int = 0
    firing: int = 0
    opened_incidents: int = 0
    updated_incidents: int = 0
    skipped_duplicates: int = 0
    errors: int = 0
    error_messages: tuple[str, ...] = field(default_factory=tuple)
    promotion_mode: Literal["local", "backend-api"] = "local"
    opened_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    updated_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    observation_refreshed_incident_ids: tuple[str, ...] = field(
        default_factory=tuple
    )
    unchanged_incident_ids: tuple[str, ...] = field(default_factory=tuple)
    promotion_records: tuple[dict[str, str | None], ...] = field(
        default_factory=tuple
    )
    unique_candidate_count: int = 0
    promotion_scan_scope: str = ""
    incident_access_mode: str = "local"

    def to_dict(self) -> dict[str, object]:
        """Convert to a JSON-friendly dict for logging / response."""
        return {
            "ok": self.ok,
            "scanned": self.scanned,
            "firing": self.firing,
            "opened_incidents": self.opened_incidents,
            "updated_incidents": self.updated_incidents,
            "skipped_duplicates": self.skipped_duplicates,
            "errors": self.errors,
            "error_messages": list(self.error_messages),
            "promotion_mode": self.promotion_mode,
            "opened_incident_ids": list(self.opened_incident_ids),
            "updated_incident_ids": list(self.updated_incident_ids),
            "promotion_records": [dict(r) for r in self.promotion_records],
            "unique_candidate_count": self.unique_candidate_count,
            "promotion_scan_scope": self.promotion_scan_scope,
            "incident_access_mode": self.incident_access_mode,
        }

    @property
    def actionable_incident_ids(self) -> tuple[str, ...]:
        """Stable first-occurrence union of opened + materially-changed.

        Defined as the stable first-occurrence union of
        opened_incident_ids and updated_incident_ids. Excludes
        unchanged and observation-refreshed incidents.
        """
        seen: set[str] = set()
        result: list[str] = []
        for id_ in (*self.opened_incident_ids, *self.updated_incident_ids):
            if id_ not in seen:
                seen.add(id_)
                result.append(id_)
        return tuple(result)

    # Deprecated: use actionable_incident_ids instead.
    def canonical_incident_ids(self) -> tuple[str, ...]:
        """Return opened + updated canonical incident IDs as one tuple.

        .. deprecated::
            Use :attr:`actionable_incident_ids` instead.
        """
        return self.actionable_incident_ids


__all__ = [
    "INCIDENT_ACCESS_MODE_BACKEND",
    "INCIDENT_ACCESS_MODE_LOCAL",
    "IncidentPromotionResult",
    "PROMOTION_MODE_BACKEND_API",
    "PROMOTION_MODE_LOCAL",
    "RECONCILIATION_REQUIRED_ACCESS_MODE",
    "SCAN_SCOPE_INTERNAL_API_ALERT_SIGNALS_SCOPED",
]