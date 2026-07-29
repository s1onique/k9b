"""Strict wire payload decoding for the **legacy** snake_case dialect.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B-CORRECTION01.
ACT-K9B-HULK-PROMOTION-SCOPED-WIRE-DIALECT-CONVERGENCE01.

DIALECT OWNERSHIP -- LEGACY/ADMIN
----------------------------------

This module decodes the legacy snake_case
``/api/internal/incidents/promote-candidates`` ``PromotionResponse``
dialect. The active scoped endpoint
``/api/internal/incidents/promote-alert-signals`` returns the
canonical camelCase ``IncidentPromotionResult`` contract declared
in :mod:`k8s_diag_agent.incident_alert_promotion_contract`. The
scoped response MUST be parsed by
:meth:`IncidentPromotionResult.from_wire_dict`. Routing a scoped
camelCase payload through ``PromotionHttpWireResult.from_payload``
will fail closed because the legacy snake_case keys are missing
from the response, turning every legitimate scoped response into a
synthetic failure. Do not wire this decoder into the scoped path.

The decode module owns the only legal path from a raw
``Mapping[str, Any]`` to a validated
:class:`PromotionHttpWireResult` (or :class:`PromotionWireRecord`).
It enforces:

* Required fields are explicit. Missing fields raise
  :class:`PromotionHttpWireValidationError`.
* ``ok`` MUST be a strict ``bool`` (truthy non-bools raise).
* Numerical fields MUST be non-negative ``int`` (``bool`` and
  ``float`` raise).
* ID collection fields MUST be tuples of non-empty strings.
  Direct construction parity is enforced via
  :func:`validate_identifier_tuple` from
  :mod:`promotion_http_wire_semantics`.
* Record outcomes MUST be ``PromotionWireRecordOutcome`` literals.
* Result-level invariants (canonical stable order, opened/updated
  bijection, source-ID uniqueness, ok/error consistency) are
  enforced via :func:`validate_result_invariants`.
* Enum-decoding boundaries catch both ``TypeError`` and
  ``ValueError`` so malformed wire values converge on
  :class:`PromotionHttpWireValidationError`.

Counter rules (preserved from the binding contract):

* ``firing`` <= ``scanned``.
* ``opened_incidents`` == ``len(opened_incident_ids)``.
* ``updated_incidents`` == ``len(updated_incident_ids)``.
* ``ok=True`` requires ``errors=0`` and empty ``error_messages``.

Canonical rules:

* ``canonical_incident_ids`` is the stable first-occurrence
  unique sequence of record canonical IDs (order authoritative).
* ``opened_incident_ids`` and ``updated_incident_ids`` are
  derived stable unique sequences from records with matching
  outcomes (bijective reconciliation).
* Source candidate IDs are unique across records.
* Canonical incident IDs MAY repeat across records (many-to-one
  production case).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .promotion_http_wire_semantics import (
    catch_enum_decode,
    decode_identifier_tuple,
    validate_identifier_tuple,
    validate_result_invariants,
)
from .promotion_http_wire_types import (
    PromotionHttpWireValidationError,
    PromotionWireIncidentAccessMode,
    PromotionWireRecordOutcome,
    PromotionWireScanScope,
)

_REQUIRED_WIRE_FIELDS: tuple[str, ...] = (
    "ok",
    "scanned",
    "firing",
    "opened_incidents",
    "updated_incidents",
    "skipped_duplicates",
    "errors",
    "error_messages",
    "opened_incident_ids",
    "updated_incident_ids",
    "canonical_incident_ids",
    "promotion_records",
    "unique_candidate_count",
    "promotion_scan_scope",
    "incident_access_mode",
)


def _require_field(
    payload: Mapping[str, Any],
    name: str,
) -> Any:
    """Return the required field or raise validation error."""
    if name not in payload:
        raise PromotionHttpWireValidationError(
            f"missing required field: {name!r}"
        )
    return payload[name]


def _require_strict_bool(value: Any, field_name: str) -> bool:
    """Require a strict ``bool`` (truthy non-bools raise)."""
    if not isinstance(value, bool):
        raise PromotionHttpWireValidationError(
            f"{field_name!r} MUST be a strict bool; got "
            f"{type(value).__name__}"
        )
    return value


def _require_non_negative_int(value: Any, field_name: str) -> int:
    """Require a non-negative ``int`` (``bool`` and ``float`` raise)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PromotionHttpWireValidationError(
            f"{field_name!r} MUST be a non-negative int; got "
            f"{type(value).__name__}={value!r}"
        )
    return value


@dataclass(frozen=True, slots=True)
class PromotionWireRecord:
    """Validated per-candidate promotion record.

    Direct construction enforces the same invariants as raw
    payload decoding so callers cannot bypass entry validation
    via the dataclass constructor.
    """

    source_candidate_id: str
    canonical_incident_id: str
    promotion_outcome: PromotionWireRecordOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.source_candidate_id, str) or not self.source_candidate_id:
            raise PromotionHttpWireValidationError(
                "source_candidate_id MUST be a non-empty string"
            )
        if not isinstance(self.canonical_incident_id, str) or not self.canonical_incident_id:
            raise PromotionHttpWireValidationError(
                "canonical_incident_id MUST be a non-empty string"
            )
        if not isinstance(self.promotion_outcome, PromotionWireRecordOutcome):
            raise PromotionHttpWireValidationError(
                "promotion_outcome MUST be a PromotionWireRecordOutcome"
            )


def _validate_record_entry(entry: Any) -> PromotionWireRecord:
    """Validate a record entry from a raw payload.

    All boundary malformations converge on
    :class:`PromotionHttpWireValidationError`:
    non-mapping entry, missing field, non-string IDs, empty IDs,
    or malformed ``promotion_outcome`` (TypeError / ValueError).
    """
    if not isinstance(entry, Mapping):
        raise PromotionHttpWireValidationError(
            "promotion_records entries MUST be mappings"
        )
    if "source_candidate_id" not in entry:
        raise PromotionHttpWireValidationError(
            "promotion_records entries MUST declare source_candidate_id"
        )
    if "canonical_incident_id" not in entry:
        raise PromotionHttpWireValidationError(
            "promotion_records entries MUST declare canonical_incident_id"
        )
    if "promotion_outcome" not in entry:
        raise PromotionHttpWireValidationError(
            "promotion_records entries MUST declare promotion_outcome"
        )
    source_id = entry["source_candidate_id"]
    canonical_id = entry["canonical_incident_id"]
    if not isinstance(source_id, str) or not source_id:
        raise PromotionHttpWireValidationError(
            "promotion_records entries source_candidate_id MUST be a "
            "non-empty string"
        )
    if not isinstance(canonical_id, str) or not canonical_id:
        raise PromotionHttpWireValidationError(
            "promotion_records entries canonical_incident_id MUST be a "
            "non-empty string"
        )
    outcome = catch_enum_decode(
        lambda: PromotionWireRecordOutcome(entry["promotion_outcome"]),
        field_name="promotion_outcome",
        raw_value=entry["promotion_outcome"],
    )
    return PromotionWireRecord(
        source_candidate_id=source_id,
        canonical_incident_id=canonical_id,
        promotion_outcome=outcome,
    )


def _check_basic_types(result: PromotionHttpWireResult) -> None:
    """Validate basic types for :class:`PromotionHttpWireResult`.

    Runs first inside ``__post_init__`` before the aggregate
    invariants helper. Every tuple field is validated through
    :func:`validate_identifier_tuple` so direct construction has
    the same entry-parity guarantees as raw payload decoding.
    """
    _require_strict_bool(result.ok, "ok")
    for field_name in (
        "scanned",
        "firing",
        "opened_incidents",
        "updated_incidents",
        "skipped_duplicates",
        "errors",
        "unique_candidate_count",
    ):
        value = getattr(result, field_name)
        _require_non_negative_int(value, field_name)
    for field_name in (
        "error_messages",
        "opened_incident_ids",
        "updated_incident_ids",
        "canonical_incident_ids",
    ):
        validate_identifier_tuple(
            getattr(result, field_name), field_name=field_name
        )
    if not isinstance(result.promotion_records, tuple):
        raise PromotionHttpWireValidationError(
            "promotion_records MUST be a tuple"
        )
    for record in result.promotion_records:
        if not isinstance(record, PromotionWireRecord):
            raise PromotionHttpWireValidationError(
                "promotion_records entries MUST be PromotionWireRecord"
            )
    for message in result.error_messages:
        if not isinstance(message, str) or not message:
            raise PromotionHttpWireValidationError(
                "error_messages entries MUST be non-empty strings"
            )
    if not isinstance(result.promotion_scan_scope, PromotionWireScanScope):
        raise PromotionHttpWireValidationError(
            "promotion_scan_scope MUST be a PromotionWireScanScope"
        )
    if not isinstance(
        result.incident_access_mode, PromotionWireIncidentAccessMode
    ):
        raise PromotionHttpWireValidationError(
            "incident_access_mode MUST be a PromotionWireIncidentAccessMode"
        )


@dataclass(frozen=True, slots=True)
class PromotionHttpWireResult:
    """Strict validated backend promotion wire result.

    Construction via :meth:`from_payload` is the only path through
    which a payload may reach :class:`BoundPromotionHttpWireResult`.
    Direct construction is supported but the same invariants are
    enforced by ``__post_init__``.
    """

    ok: bool
    scanned: int
    firing: int
    opened_incidents: int
    updated_incidents: int
    skipped_duplicates: int
    errors: int
    error_messages: tuple[str, ...]
    opened_incident_ids: tuple[str, ...]
    updated_incident_ids: tuple[str, ...]
    canonical_incident_ids: tuple[str, ...]
    promotion_records: tuple[PromotionWireRecord, ...]
    unique_candidate_count: int
    promotion_scan_scope: PromotionWireScanScope
    incident_access_mode: PromotionWireIncidentAccessMode

    def __post_init__(self) -> None:
        _check_basic_types(self)
        validate_result_invariants(self)

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any]
    ) -> PromotionHttpWireResult:
        """Validate and construct a wire result from a raw mapping.

        Every boundary deformation converges on
        :class:`PromotionHttpWireValidationError` -- missing
        fields, wrong types, malformed enum values, and every
        higher-level aggregate invariant.
        """
        if not isinstance(payload, Mapping):
            raise PromotionHttpWireValidationError(
                f"payload MUST be a Mapping; got {type(payload).__name__}"
            )
        missing = [
            name for name in _REQUIRED_WIRE_FIELDS if name not in payload
        ]
        if missing:
            raise PromotionHttpWireValidationError(
                f"missing required fields: {missing!r}"
            )

        ok = _require_strict_bool(_require_field(payload, "ok"), "ok")
        scanned = _require_non_negative_int(
            _require_field(payload, "scanned"), "scanned"
        )
        firing = _require_non_negative_int(
            _require_field(payload, "firing"), "firing"
        )
        opened_incidents = _require_non_negative_int(
            _require_field(payload, "opened_incidents"), "opened_incidents"
        )
        updated_incidents = _require_non_negative_int(
            _require_field(payload, "updated_incidents"), "updated_incidents"
        )
        skipped_duplicates = _require_non_negative_int(
            _require_field(payload, "skipped_duplicates"),
            "skipped_duplicates",
        )
        errors = _require_non_negative_int(
            _require_field(payload, "errors"), "errors"
        )
        unique_candidate_count = _require_non_negative_int(
            _require_field(payload, "unique_candidate_count"),
            "unique_candidate_count",
        )

        opened_ids = decode_identifier_tuple(
            _require_field(payload, "opened_incident_ids"),
            field_name="opened_incident_ids",
        )
        updated_ids = decode_identifier_tuple(
            _require_field(payload, "updated_incident_ids"),
            field_name="updated_incident_ids",
        )
        canonical_ids = decode_identifier_tuple(
            _require_field(payload, "canonical_incident_ids"),
            field_name="canonical_incident_ids",
        )
        error_messages = decode_identifier_tuple(
            _require_field(payload, "error_messages"),
            field_name="error_messages",
        )

        raw_records = _require_field(payload, "promotion_records")
        if not isinstance(raw_records, (list, tuple)):
            raise PromotionHttpWireValidationError(
                "promotion_records MUST be a list or tuple"
            )
        records = tuple(_validate_record_entry(entry) for entry in raw_records)

        scope = catch_enum_decode(
            lambda: PromotionWireScanScope(
                _require_field(payload, "promotion_scan_scope")
            ),
            field_name="promotion_scan_scope",
            raw_value=_require_field(payload, "promotion_scan_scope"),
        )
        access_mode = catch_enum_decode(
            lambda: PromotionWireIncidentAccessMode(
                _require_field(payload, "incident_access_mode")
            ),
            field_name="incident_access_mode",
            raw_value=_require_field(payload, "incident_access_mode"),
        )

        return cls(
            ok=ok,
            scanned=scanned,
            firing=firing,
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            skipped_duplicates=skipped_duplicates,
            errors=errors,
            error_messages=error_messages,
            opened_incident_ids=opened_ids,
            updated_incident_ids=updated_ids,
            canonical_incident_ids=canonical_ids,
            promotion_records=records,
            unique_candidate_count=unique_candidate_count,
            promotion_scan_scope=scope,
            incident_access_mode=access_mode,
        )


__all__ = [
    "PromotionHttpWireResult",
    "PromotionWireRecord",
    "_REQUIRED_WIRE_FIELDS",
]
