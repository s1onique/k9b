"""Strict wire payload decoding.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2B.

The decode module owns the only legal path from a raw
``Mapping[str, Any]`` to a validated ``PromotionHttpWireResult``
(or ``PromotionWireRecord``). It enforces:

* Required fields are explicit. Missing fields raise
  ``PromotionHttpWireValidationError``.
* ``ok`` MUST be a strict ``bool`` (truthy non-bools raise).
* Numerical fields MUST be non-negative ints (``bool`` and ``float``
  raise).
* ID collections MUST be tuples of non-empty strings.
* Record outcomes MUST be ``PromotionWireRecordOutcome`` literals.
* Counter consistency (``firing <= scanned``,
  ``opened_incidents == len(opened_incident_ids)``,
  ``updated_incidents == len(updated_incident_ids)``,
  ``canonical_incident_ids == unique(records.canonical_incident_id)``).
* ``ok=True`` requires ``errors=0`` and empty ``error_messages``.
* ``ok=False`` requires ``errors>0`` and non-empty
  ``error_messages``.
* Source candidate IDs are unique across records.
* Canonical incident IDs MAY repeat across records (multiple alert
  signals may legitimately reference the same incident).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

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


def _require_string_list(
    value: Any, field_name: str
) -> tuple[str, ...]:
    """Require a list/tuple of non-empty strings."""
    if not isinstance(value, (list, tuple)):
        raise PromotionHttpWireValidationError(
            f"{field_name!r} MUST be a list or tuple"
        )
    ids: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not entry:
            raise PromotionHttpWireValidationError(
                f"{field_name!r} entries MUST be non-empty strings"
            )
        ids.append(entry)
    return tuple(ids)


@dataclass(frozen=True, slots=True)
class PromotionWireRecord:
    """Validated per-candidate promotion record."""

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


def _validate_record(
    *,
    source_candidate_id: Any,
    canonical_incident_id: Any,
    promotion_outcome: Any,
) -> PromotionWireRecord:
    """Validate a record's three fields and return a PromotionWireRecord.

    Used by direct construction (so non-dataclass callers get the
    same validation) and by the payload decoder.
    """
    return PromotionWireRecord(
        source_candidate_id=source_candidate_id,
        canonical_incident_id=canonical_incident_id,
        promotion_outcome=promotion_outcome,
    )


def _validate_record_entry(entry: Any) -> PromotionWireRecord:
    """Validate a record entry from a raw payload."""
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
    try:
        outcome = PromotionWireRecordOutcome(entry["promotion_outcome"])
    except ValueError as exc:
        raise PromotionHttpWireValidationError(
            f"unknown promotion_outcome: {entry['promotion_outcome']!r}"
        ) from exc
    return _validate_record(
        source_candidate_id=entry["source_candidate_id"],
        canonical_incident_id=entry["canonical_incident_id"],
        promotion_outcome=outcome,
    )


@dataclass(frozen=True, slots=True)
class PromotionHttpWireResult:
    """Strict validated backend promotion wire result.

    Construction via :meth:`from_payload` is the only path through
    which a payload may reach ``PromotionHttpSucceeded``. Direct
    construction is supported but the same invariants are enforced.
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
        _require_strict_bool(self.ok, "ok")
        for field_name in (
            "scanned",
            "firing",
            "opened_incidents",
            "updated_incidents",
            "skipped_duplicates",
            "errors",
            "unique_candidate_count",
        ):
            value = getattr(self, field_name)
            _require_non_negative_int(value, field_name)
        for field_name in (
            "error_messages",
            "opened_incident_ids",
            "updated_incident_ids",
            "canonical_incident_ids",
            "promotion_records",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise PromotionHttpWireValidationError(
                    f"{field_name!r} MUST be a tuple"
                )
        for record in self.promotion_records:
            if not isinstance(record, PromotionWireRecord):
                raise PromotionHttpWireValidationError(
                    "promotion_records entries MUST be PromotionWireRecord"
                )
        if self.firing > self.scanned:
            raise PromotionHttpWireValidationError(
                "firing MUST NOT exceed scanned"
            )
        if self.opened_incidents != len(self.opened_incident_ids):
            raise PromotionHttpWireValidationError(
                "opened_incidents MUST equal len(opened_incident_ids)"
            )
        if self.updated_incidents != len(self.updated_incident_ids):
            raise PromotionHttpWireValidationError(
                "updated_incidents MUST equal len(updated_incident_ids)"
            )
        unique_from_records = sorted(
            {record.canonical_incident_id for record in self.promotion_records}
        )
        if sorted(self.canonical_incident_ids) != unique_from_records:
            raise PromotionHttpWireValidationError(
                "canonical_incident_ids MUST equal the unique "
                "canonical_incident_ids from promotion_records"
            )
        opened_set = set(self.opened_incident_ids)
        updated_set = set(self.updated_incident_ids)
        for record in self.promotion_records:
            if (
                record.promotion_outcome is PromotionWireRecordOutcome.OPENED
                and record.canonical_incident_id not in opened_set
            ):
                raise PromotionHttpWireValidationError(
                    "opened record canonical_incident_id MUST appear in "
                    "opened_incident_ids"
                )
            if (
                record.promotion_outcome is PromotionWireRecordOutcome.UPDATED
                and record.canonical_incident_id not in updated_set
            ):
                raise PromotionHttpWireValidationError(
                    "updated record canonical_incident_id MUST appear in "
                    "updated_incident_ids"
                )
        if self.ok and self.errors != 0:
            raise PromotionHttpWireValidationError(
                "ok=True requires errors=0"
            )
        if not self.ok and self.errors == 0:
            raise PromotionHttpWireValidationError(
                "ok=False requires errors>0"
            )
        if self.errors == 0 and self.error_messages:
            raise PromotionHttpWireValidationError(
                "errors=0 requires empty error_messages"
            )
        if self.errors > 0 and not self.error_messages:
            raise PromotionHttpWireValidationError(
                "errors>0 requires non-empty error_messages"
            )
        for message in self.error_messages:
            if not isinstance(message, str) or not message:
                raise PromotionHttpWireValidationError(
                    "error_messages entries MUST be non-empty strings"
                )
        # Source IDs MUST be unique; canonical IDs may legitimately
        # repeat across records when multiple alerts map to one
        # incident.
        source_ids: set[str] = set()
        for record in self.promotion_records:
            if record.source_candidate_id in source_ids:
                raise PromotionHttpWireValidationError(
                    "source_candidate_id MUST be unique across records"
                )
            source_ids.add(record.source_candidate_id)
        if not isinstance(self.promotion_scan_scope, PromotionWireScanScope):
            raise PromotionHttpWireValidationError(
                "promotion_scan_scope MUST be a PromotionWireScanScope"
            )
        if not isinstance(
            self.incident_access_mode, PromotionWireIncidentAccessMode
        ):
            raise PromotionHttpWireValidationError(
                "incident_access_mode MUST be a PromotionWireIncidentAccessMode"
            )

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any]
    ) -> PromotionHttpWireResult:
        """Validate and construct a wire result from a raw mapping."""
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

        opened_ids = _require_string_list(
            _require_field(payload, "opened_incident_ids"),
            "opened_incident_ids",
        )
        updated_ids = _require_string_list(
            _require_field(payload, "updated_incident_ids"),
            "updated_incident_ids",
        )
        canonical_ids = _require_string_list(
            _require_field(payload, "canonical_incident_ids"),
            "canonical_incident_ids",
        )

        raw_messages = _require_field(payload, "error_messages")
        if not isinstance(raw_messages, (list, tuple)):
            raise PromotionHttpWireValidationError(
                "error_messages MUST be a list or tuple"
            )
        error_messages: list[str] = []
        for message in raw_messages:
            if not isinstance(message, str) or not message:
                raise PromotionHttpWireValidationError(
                    "error_messages entries MUST be non-empty strings"
                )
            error_messages.append(message)

        raw_records = _require_field(payload, "promotion_records")
        if not isinstance(raw_records, (list, tuple)):
            raise PromotionHttpWireValidationError(
                "promotion_records MUST be a list or tuple"
            )
        records = tuple(_validate_record_entry(entry) for entry in raw_records)

        try:
            scope = PromotionWireScanScope(
                _require_field(payload, "promotion_scan_scope")
            )
        except ValueError as exc:
            raise PromotionHttpWireValidationError(
                f"invalid promotion_scan_scope: "
                f"{_require_field(payload, 'promotion_scan_scope')!r}"
            ) from exc

        try:
            access_mode = PromotionWireIncidentAccessMode(
                _require_field(payload, "incident_access_mode")
            )
        except ValueError as exc:
            raise PromotionHttpWireValidationError(
                f"invalid incident_access_mode: "
                f"{_require_field(payload, 'incident_access_mode')!r}"
            ) from exc

        return cls(
            ok=ok,
            scanned=scanned,
            firing=firing,
            opened_incidents=opened_incidents,
            updated_incidents=updated_incidents,
            skipped_duplicates=skipped_duplicates,
            errors=errors,
            error_messages=tuple(error_messages),
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
    "PromotionHttpWireValidationError",
    "PromotionWireRecord",
    "_REQUIRED_WIRE_FIELDS",
]
