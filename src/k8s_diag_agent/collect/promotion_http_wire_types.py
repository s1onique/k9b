"""Enums and immutable dataclasses for the strict wire result.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B.

This module hosts the closed vocabulary and the immutable wire
record / result types. Validation rules and decoding live in
:mod:`promotion_http_wire_decode`. Request binding lives in
:mod:`promotion_http_wire_binding`.

The split exists to keep each production file below the 500-line
LLM-friendly ceiling.

Wire contract choices (verified against the backend serializer):

* ``canonical_incident_id`` is REQUIRED and non-empty for every
  record regardless of ``promotion_outcome``. Multiple source
  signals MAY legitimately reference the same canonical incident
  (the 1-inserted / 28-identity-matched production case). The
  uniqueness rule applies to ``source_candidate_id`` only, never
  to ``canonical_incident_id``.
* ``canonical_incident_ids`` is the stable unique sequence of every
  record's canonical ID -- both opened/updated and
  observation_refreshed/unchanged.
* ``opened_incident_ids`` and ``updated_incident_ids`` are subsets
  of ``canonical_incident_ids``.
* ``opened_incidents`` and ``updated_incidents`` are the count of
  the corresponding ID list (not a separate ``len(...)`` redundant
  value).
* ``unique_candidate_count`` equals the number of distinct
  ``source_candidate_id`` values across the records.
* ``scanned`` equals the number of distinct requested signal IDs.
* ``firing`` <= ``scanned``.
* ``skipped_duplicates`` reflects identity-matched observation
  records (not currently represented as a dedicated record outcome
  variant; the field is preserved for diagnostic correlation).
* ``promotion_scan_scope`` is the closed
  ``internal_api_alert_signals:scoped`` literal.
* ``incident_access_mode`` is the closed ``backend`` / ``local``
  literal.
"""

from __future__ import annotations

from enum import StrEnum


class PromotionWireRecordOutcome(StrEnum):
    """Closed vocabulary for ``PromotionRecord.promotion_outcome``.

    The backend wire contract uses these literal strings. ``unknown``
    is reserved for transport-level failures; the strict decoder
    MUST reject it as an authoritative wire value.
    """

    OPENED = "opened"
    UPDATED = "updated"
    OBSERVATION_REFRESHED = "observation_refreshed"
    UNCHANGED = "unchanged"


class PromotionWireScanScope(StrEnum):
    """Closed vocabulary for ``promotion_scan_scope``."""

    INTERNAL_API_ALERT_SIGNALS_SCOPED = "internal_api_alert_signals:scoped"


class PromotionWireIncidentAccessMode(StrEnum):
    """Closed vocabulary for ``incident_access_mode``."""

    BACKEND = "backend"
    LOCAL = "local"


class PromotionHttpWireValidationError(ValueError):
    """Raised when the wire payload fails strict validation."""


__all__ = [
    "PromotionHttpWireValidationError",
    "PromotionWireIncidentAccessMode",
    "PromotionWireRecordOutcome",
    "PromotionWireScanScope",
]
