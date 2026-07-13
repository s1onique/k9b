"""Typed ``PromotionBatch`` value handed between dispatcher and accumulator.

R3 contract: ``promote_alert_signals_for_accumulator`` MUST return a
``PromotionBatch`` that preserves every field of the underlying
``IncidentPromotionResult`` alongside typed ``PromotionRecord``
values and source/cluster provenance. The batch is the only
legitimate handoff between the dispatcher and
``RunPromotionAccumulator``; legacy duck-typed dicts are no longer
accepted.

The accumulator MUST NOT infer ``promotion_mode`` from whether
records are empty. It MUST consume the mode verbatim from the
batch. ``incident_access_mode`` is also propagated verbatim.

Handoff contract (SEAM01):
- ``PromotionBatch`` is a transport envelope that MUST NOT own ID projections.
- The only legitimate access to ``actionable_incident_ids`` is via
  ``batch.promotion_result.actionable_incident_ids``.
- ``propagate_promotion_result_to_run()`` is the canonical handoff function
  that must be used for all promotion-to-diagnosis propagation.

Suggested by: ACT-K9B-AUTO-DIAGNOSIS-BACKEND-INCIDENT-IDENTITY01-R3
Suggested by: ACT-K9B-HULK-PROMOTION-DIAGNOSIS-HANDOFF-SEAM01
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .incident_identity_hardening import PromotionRecord

if TYPE_CHECKING:
    from .incident_promotion_dispatch import IncidentPromotionResult


@dataclass(frozen=True)
class PromotionBatch:
    """Typed promotion-batch value handed between dispatcher and accumulator.

    The batch preserves every field of the underlying
    ``IncidentPromotionResult`` alongside typed ``PromotionRecord``
    values and source/cluster provenance. Downstream callers (notably
    ``RunPromotionAccumulator`` and automatic-diagnosis) consume the
    batch via ``promotion_result``; legacy duck-typed dicts are no
    longer accepted.

    SEAM01 contract: ``PromotionBatch`` MUST NOT expose ``actionable_incident_ids``
    or ``canonical_incident_ids()`` as projections. The only allowed access is
    ``batch.promotion_result.actionable_incident_ids``. Use
    ``propagate_promotion_result_to_run()`` for canonical handoff.
    """

    promotion_result: IncidentPromotionResult
    promotion_records: tuple[PromotionRecord, ...]
    source_kind: str = "alertmanager"
    cluster_context: str | None = None
    snapshot_bundle_id: str | None = None

    @property
    def promotion_mode(self) -> str:
        """Promote the inner ``promotion_mode`` for ergonomic access."""
        return self.promotion_result.promotion_mode

    @property
    def incident_access_mode(self) -> str:
        """Promote the inner ``incident_access_mode`` for ergonomic access."""
        return self.promotion_result.incident_access_mode

    @property
    def ok(self) -> bool:
        """Return True only when the dispatcher reported success."""
        return self.promotion_result.ok

    @property
    def errors(self) -> int:
        """Return the dispatcher-reported error count."""
        return self.promotion_result.errors

    @property
    def error_messages(self) -> tuple[str, ...]:
        """Return the dispatcher-reported error messages."""
        return self.promotion_result.error_messages

    @property
    def scanned(self) -> int:
        """Return the dispatcher-reported scanned count."""
        return self.promotion_result.scanned

    @property
    def firing(self) -> int:
        """Return the dispatcher-reported firing count."""
        return self.promotion_result.firing

    @property
    def opened_incidents(self) -> int:
        """Return the dispatcher-reported opened count."""
        return self.promotion_result.opened_incidents

    @property
    def updated_incidents(self) -> int:
        """Return the dispatcher-reported updated count."""
        return self.promotion_result.updated_incidents

    @property
    def skipped_duplicates(self) -> int:
        """Return the dispatcher-reported skipped-duplicate count."""
        return self.promotion_result.skipped_duplicates

    @property
    def promotion_scan_scope(self) -> str:
        """Return the dispatcher-reported scan scope."""
        return self.promotion_result.promotion_scan_scope

    @property
    def unique_candidate_count(self) -> int:
        """Return the unique candidate count from the dispatcher."""
        return self.promotion_result.unique_candidate_count

    @property
    def opened_incident_ids(self) -> tuple[str, ...]:
        """Return the opened canonical incident IDs from the dispatcher."""
        return self.promotion_result.opened_incident_ids

    @property
    def updated_incident_ids(self) -> tuple[str, ...]:
        """Return the updated canonical incident IDs from the dispatcher."""
        return self.promotion_result.updated_incident_ids


__all__ = ["PromotionBatch"]
