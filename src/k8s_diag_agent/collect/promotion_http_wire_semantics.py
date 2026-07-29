"""Result-level invariant validation for the **legacy** snake_case wire result.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B-CORRECTION01.
ACT-K9B-HULK-PROMOTION-SCOPED-WIRE-DIALECT-CONVERGENCE01.

DIALECT OWNERSHIP -- LEGACY/ADMIN
----------------------------------

This module owns the invariant helpers and result validators for
the legacy snake_case ``/api/internal/incidents/promote-candidates``
``PromotionResponse`` dialect. The active scoped endpoint
``/api/internal/incidents/promote-alert-signals`` returns the
canonical camelCase ``IncidentPromotionResult`` contract declared
in :mod:`k8s_diag_agent.incident_alert_promotion_contract`. The
scoped response is decoded by
:meth:`IncidentPromotionResult.from_wire_dict` and validated by
:class:`k8s_diag_agent.incident_alert_promotion_binding.BoundScopedPromotionResult`;
do not route it through the legacy helpers below.

This module owns:

* Reusable identifier-tuple validator (used by raw decoding,
  :class:`PromotionHttpWireResult` construction, and request
  binding).
* Stable first-occurrence unique-sequence helper.
* High-level result invariants: opened/updated bijection,
  canonical aggregate stable order, record-outcome consistency,
  source-ID uniqueness, ok/error consistency.
* Enum-decoding boundary helper that converges all malformed
  values on :class:`PromotionHttpWireValidationError`.

The split exists to keep
:mod:`promotion_http_wire_decode` focused on raw field parsing
and within the LLM-friendly size ceiling.

Wire contract choices (authoritative):

* ``canonical_incident_ids`` is the **stable first-occurrence
  unique** sequence of ``promotion_records[*].canonical_incident_id``.
  Set equality is insufficient; order is authoritative.
* ``opened_incident_ids`` is the stable first-occurrence unique
  sequence of ``canonical_incident_id`` for records with
  ``promotion_outcome=OPENED``.
* ``updated_incident_ids`` is the stable first-occurrence unique
  sequence of ``canonical_incident_id`` for records with
  ``promotion_outcome=UPDATED``.
* ``opened_incident_ids`` and ``updated_incident_ids`` are
  disjoint (an atomic promotion request cannot both open and
  update the same canonical incident).
* ``OBSERVATION_REFRESHED`` and ``UNCHANGED`` records contribute
  to ``canonical_incident_ids`` but NOT to ``opened_incident_ids``
  or ``updated_incident_ids``.
* Multiple source records MAY legitimately reference the same
  canonical incident (the 1-inserted / 28-identity-matched
  production case). The uniqueness rule applies to
  ``source_candidate_id`` only, never to ``canonical_incident_id``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from .promotion_http_wire_types import (
    PromotionHttpWireValidationError,
    PromotionWireRecordOutcome,
)

if TYPE_CHECKING:
    from .promotion_http_wire_decode import (
        PromotionHttpWireResult,
        PromotionWireRecord,
    )


def validate_identifier_tuple(
    value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """Validate that ``value`` is a tuple of non-empty strings.

    Returns ``value`` unchanged on success. Direct construction
    paths MUST pass a tuple; raw payload decoding converts via
    :func:`tuple` before delegating here.

    Raises:
        PromotionHttpWireValidationError: when ``value`` is not a
            tuple, or any entry is not a non-empty string.
    """
    if not isinstance(value, tuple):
        raise PromotionHttpWireValidationError(
            f"{field_name!r} MUST be a tuple of non-empty strings; "
            f"got {type(value).__name__}"
        )
    for entry in value:
        if not isinstance(entry, str) or not entry:
            raise PromotionHttpWireValidationError(
                f"{field_name!r} entries MUST be non-empty strings"
            )
    return value


def decode_identifier_tuple(
    value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """Decode an identifier tuple from a raw payload value.

    Accepts ``list`` or ``tuple`` (raw payload lists are
    converted via :func:`tuple` to preserve type parity with
    direct construction). Validates each entry is a non-empty
    string and returns a tuple.
    """
    if not isinstance(value, (list, tuple)):
        raise PromotionHttpWireValidationError(
            f"{field_name!r} MUST be a list or tuple of non-empty "
            f"strings; got {type(value).__name__}"
        )
    return validate_identifier_tuple(
        tuple(value), field_name=field_name
    )


def stable_unique(values: Iterable[str]) -> tuple[str, ...]:
    """Return the first-occurrence unique sequence of strings.

    Order is preserved from the input iterable. Duplicates after
    the first occurrence are dropped.
    """
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def record_opened_canonical_ids(
    records: tuple[PromotionWireRecord, ...],
) -> tuple[str, ...]:
    """Stable first-occurrence unique canonical IDs of OPENED records."""
    return stable_unique(
        record.canonical_incident_id
        for record in records
        if record.promotion_outcome is PromotionWireRecordOutcome.OPENED
    )


def record_updated_canonical_ids(
    records: tuple[PromotionWireRecord, ...],
) -> tuple[str, ...]:
    """Stable first-occurrence unique canonical IDs of UPDATED records."""
    return stable_unique(
        record.canonical_incident_id
        for record in records
        if record.promotion_outcome is PromotionWireRecordOutcome.UPDATED
    )


def catch_enum_decode(
    call: Any,
    *,
    field_name: str,
    raw_value: Any,
) -> Any:
    """Run a callable and convert ``TypeError``/``ValueError``.

    Used at every enum-decoding boundary so that malformed wire
    values converge on :class:`PromotionHttpWireValidationError`
    rather than leaking ``TypeError`` (non-string arguments to
    ``StrEnum(...)``), ``ValueError`` (unknown string), or any
    other internal exception.
    """
    try:
        return call()
    except (TypeError, ValueError) as exc:
        raise PromotionHttpWireValidationError(
            f"invalid {field_name}: {raw_value!r}"
        ) from exc


def validate_result_invariants(result: PromotionHttpWireResult) -> None:
    """Validate every result-level invariant for the wire result.

    Called from :meth:`PromotionHttpWireResult.__post_init__` after
    basic type validation has passed. The full invariant surface:

    * Counter consistency (``firing <= scanned``,
      ``opened_incidents == len(opened_incident_ids)``,
      ``updated_incidents == len(updated_incident_ids)``).
    * ``canonical_incident_ids`` is the stable first-occurrence
      unique sequence of record canonical IDs (order authoritative).
    * Bidirectional opened/updated reconciliation: every record's
      ``promotion_outcome`` matches the corresponding ID list, and
      every ID in the lists has at least one matching record.
    * ``opened_incident_ids`` and ``updated_incident_ids`` are
      disjoint.
    * Source candidate IDs are unique across records.
    * ``ok=True`` requires ``errors=0`` and empty
      ``error_messages``; ``ok=False`` requires ``errors>0`` and
      non-empty ``error_messages``.
    """
    # Counter consistency -------------------------------------------------
    if result.firing > result.scanned:
        raise PromotionHttpWireValidationError(
            "firing MUST NOT exceed scanned"
        )
    if result.opened_incidents != len(result.opened_incident_ids):
        raise PromotionHttpWireValidationError(
            "opened_incidents MUST equal len(opened_incident_ids)"
        )
    if result.updated_incidents != len(result.updated_incident_ids):
        raise PromotionHttpWireValidationError(
            "updated_incidents MUST equal len(updated_incident_ids)"
        )

    # Canonical aggregate stable order -----------------------------------
    unique_from_records = stable_unique(
        record.canonical_incident_id for record in result.promotion_records
    )
    if result.canonical_incident_ids != unique_from_records:
        raise PromotionHttpWireValidationError(
            "canonical_incident_ids MUST equal the stable first-"
            "occurrence unique sequence of record canonical_incident_id"
        )

    # Bidirectional opened/updated reconciliation ------------------------
    opened_set = set(result.opened_incident_ids)
    updated_set = set(result.updated_incident_ids)
    if opened_set & updated_set:
        raise PromotionHttpWireValidationError(
            "opened_incident_ids and updated_incident_ids MUST be disjoint"
        )
    opened_from_records = record_opened_canonical_ids(result.promotion_records)
    if result.opened_incident_ids != opened_from_records:
        raise PromotionHttpWireValidationError(
            "opened_incident_ids MUST equal the stable first-occurrence "
            "unique sequence of canonical_incident_id for records with "
            "promotion_outcome=OPENED"
        )
    updated_from_records = record_updated_canonical_ids(
        result.promotion_records
    )
    if result.updated_incident_ids != updated_from_records:
        raise PromotionHttpWireValidationError(
            "updated_incident_ids MUST equal the stable first-occurrence "
            "unique sequence of canonical_incident_id for records with "
            "promotion_outcome=UPDATED"
        )

    # Source IDs MUST be unique; canonical IDs may legitimately repeat.
    source_ids: set[str] = set()
    for record in result.promotion_records:
        if record.source_candidate_id in source_ids:
            raise PromotionHttpWireValidationError(
                "source_candidate_id MUST be unique across records"
            )
        source_ids.add(record.source_candidate_id)

    # Ok/error consistency ----------------------------------------------
    if result.ok and result.errors != 0:
        raise PromotionHttpWireValidationError(
            "ok=True requires errors=0"
        )
    if not result.ok and result.errors == 0:
        raise PromotionHttpWireValidationError(
            "ok=False requires errors>0"
        )
    if result.errors == 0 and result.error_messages:
        raise PromotionHttpWireValidationError(
            "errors=0 requires empty error_messages"
        )
    if result.errors > 0 and not result.error_messages:
        raise PromotionHttpWireValidationError(
            "errors>0 requires non-empty error_messages"
        )


__all__ = [
    "catch_enum_decode",
    "decode_identifier_tuple",
    "record_opened_canonical_ids",
    "record_updated_canonical_ids",
    "stable_unique",
    "validate_identifier_tuple",
    "validate_result_invariants",
]
