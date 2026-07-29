"""Strict validated wire result for the backend promotion path.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01-PHASE-2A.

This module defines the strict wire authority for the backend
promotion path. It is the only authority through which a payload
may reach ``PromotionHttpSucceeded`` or ``PromotionRejected``.

Fail-closed rules:

* Required fields are explicit. Missing fields raise
  ``PromotionHttpWireValidationError``.
* No ``str(value)``, no ``payload.get(name, default)`` for required
  fields, no silent filtering of non-string entries.
* Counters reconcile: ``firing <= scanned``,
  ``opened_incidents == len(opened_incident_ids)``,
  ``updated_incidents == len(updated_incident_ids)``,
  ``canonical_incident_ids == unique(opened + updated)``.
* Records validate per-instance; ``PromotionWireRecord`` and
  ``PromotionHttpWireResult`` both enforce invariants in
  ``__post_init__``.
* ``canonical_incident_id`` is required for every record outcome
  except a typed ``unchanged`` outcome (still required here; the
  empty string is rejected).
* Source candidate IDs are unique across records.
* ``ok=True`` requires ``errors=0`` and empty ``error_messages``.
* ``ok=False`` requires ``errors>0`` and non-empty
  ``error_messages``.
* ``promotion_scan_scope`` MUST equal the closed internal-API
  vocabulary literal.
* ``incident_access_mode`` MUST equal the closed
  ``backend`` / ``local`` vocabulary literal.
* Records MUST cover every requested signal ID exactly once for
  authoritative success; this is verified by
  :class:`BoundPromotionHttpWireResult`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PromotionWireRecordOutcome(StrEnum):
    """Closed vocabulary for ``PromotionRecord.promotion_outcome``."""

    OPENED = "opened"
    UPDATED = "updated"
    OBSERVATION_REFRESHED = "observation_refreshed"
    UNCHANGED = "unchanged"


class PromotionHttpWireValidationError(ValueError):
    """Raised when the wire payload fails strict validation."""


class PromotionWireScanScope(StrEnum):
    """Closed vocabulary for ``promotion_scan_scope``."""

    INTERNAL_API_ALERT_SIGNALS_SCOPED = "internal_api_alert_signals:scoped"


class PromotionWireIncidentAccessMode(StrEnum):
    """Closed vocabulary for ``incident_access_mode``."""

    BACKEND = "backend"
    LOCAL = "local"


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
    """Return the required field or raise validation error.

    Required fields MUST be present. There is no default for
    required fields; an absent field is an invalid payload.
    """
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
    """Require a tuple/list of non-empty strings."""
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
    """Validated per-candidate promotion record.

    Every field is enforced by ``__post_init__``; direct
    construction with invalid values raises
    :class:`PromotionHttpWireValidationError`.
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


@dataclass(frozen=True, slots=True)
class PromotionHttpWireResult:
    """Strict validated backend promotion wire result.

    Both direct construction and :meth:`from_payload` enforce the
    same invariants. ``PromotionHttpWireValidationError`` is the
    only constructor failure mode.
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
        for entry in self.promotion_records:
            if not isinstance(entry, PromotionWireRecord):
                raise PromotionHttpWireValidationError(
                    "promotion_records entries MUST be PromotionWireRecord"
                )
        # Counter consistency.
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
        unique_canonical = sorted(
            set(self.opened_incident_ids) | set(self.updated_incident_ids)
        )
        if sorted(self.canonical_incident_ids) != unique_canonical:
            raise PromotionHttpWireValidationError(
                "canonical_incident_ids MUST equal the unique union of "
                "opened + updated IDs"
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
        for entry in self.error_messages:
            if not isinstance(entry, str) or not entry:
                raise PromotionHttpWireValidationError(
                    "error_messages entries MUST be non-empty strings"
                )
        # Record-level consistency.
        source_ids: set[str] = set()
        canonical_ids: set[str] = set()
        for record in self.promotion_records:
            if record.source_candidate_id in source_ids:
                raise PromotionHttpWireValidationError(
                    "source_candidate_id MUST be unique across records"
                )
            source_ids.add(record.source_candidate_id)
            if record.canonical_incident_id in canonical_ids:
                raise PromotionHttpWireValidationError(
                    "canonical_incident_id MUST be unique across records"
                )
            canonical_ids.add(record.canonical_incident_id)
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
        """Validate and construct a wire result from a raw mapping.

        Required fields MUST be present. Non-string entries in ID
        collections raise. Records are validated per-instance.
        """
        if not isinstance(payload, Mapping):
            raise PromotionHttpWireValidationError(
                f"payload MUST be a Mapping; got {type(payload).__name__}"
            )

        # Required-field check FIRST (before any coercion attempt).
        missing = [
            name for name in _REQUIRED_WIRE_FIELDS if name not in payload
        ]
        if missing:
            raise PromotionHttpWireValidationError(
                f"missing required fields: {missing!r}"
            )

        ok = _require_strict_bool(
            _require_field(payload, "ok"), "ok"
        )
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
            _require_field(payload, "skipped_duplicates"), "skipped_duplicates"
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
        for entry in raw_messages:
            if not isinstance(entry, str) or not entry:
                raise PromotionHttpWireValidationError(
                    "error_messages entries MUST be non-empty strings"
                )
            error_messages.append(entry)

        raw_records = _require_field(payload, "promotion_records")
        if not isinstance(raw_records, (list, tuple)):
            raise PromotionHttpWireValidationError(
                "promotion_records MUST be a list or tuple"
            )
        records: list[PromotionWireRecord] = []
        for entry in raw_records:
            if not isinstance(entry, Mapping):
                raise PromotionHttpWireValidationError(
                    "promotion_records entries MUST be mappings"
                )
            if "source_candidate_id" not in entry:
                raise PromotionHttpWireValidationError(
                    "promotion_records entries MUST declare "
                    "source_candidate_id"
                )
            if "canonical_incident_id" not in entry:
                raise PromotionHttpWireValidationError(
                    "promotion_records entries MUST declare "
                    "canonical_incident_id"
                )
            if "promotion_outcome" not in entry:
                raise PromotionHttpWireValidationError(
                    "promotion_records entries MUST declare "
                    "promotion_outcome"
                )
            try:
                outcome = PromotionWireRecordOutcome(
                    entry["promotion_outcome"]
                )
            except ValueError as exc:
                raise PromotionHttpWireValidationError(
                    f"unknown promotion_outcome: "
                    f"{entry['promotion_outcome']!r}"
                ) from exc
            records.append(
                PromotionWireRecord(
                    source_candidate_id=entry["source_candidate_id"],
                    canonical_incident_id=entry["canonical_incident_id"],
                    promotion_outcome=outcome,
                )
            )

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
            promotion_records=tuple(records),
            unique_candidate_count=unique_candidate_count,
            promotion_scan_scope=scope,
            incident_access_mode=access_mode,
        )


@dataclass(frozen=True, slots=True)
class BoundPromotionHttpWireResult:
    """A :class:`PromotionHttpWireResult` bound to the request that
    produced it.

    The binding proves:

    * every requested signal appears in exactly one record;
    * no unrequested source signal appears;
    * records categorise all requested signals (so successful zero
      still records every signal as ``unchanged`` or similar).
    """

    result: PromotionHttpWireResult
    requested_signal_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.result, PromotionHttpWireResult):
            raise PromotionHttpWireValidationError(
                "BoundPromotionHttpWireResult.result MUST be a "
                "PromotionHttpWireResult"
            )
        if not isinstance(self.requested_signal_ids, tuple):
            raise PromotionHttpWireValidationError(
                "requested_signal_ids MUST be a tuple"
            )
        for signal_id in self.requested_signal_ids:
            if not isinstance(signal_id, str) or not signal_id:
                raise PromotionHttpWireValidationError(
                    "requested_signal_ids MUST contain non-empty strings"
                )

    @property
    def requested_signal_count(self) -> int:
        """Number of distinct requested signal IDs."""
        return len(self.requested_signal_ids)

    def categorised_source_ids(self) -> tuple[str, ...]:
        """Source candidate IDs from every record, in input order."""
        return tuple(
            record.source_candidate_id for record in self.result.promotion_records
        )

    def validate_request_binding(self) -> None:
        """Raise if the records do not cover the request exactly once.

        A successful result MUST categorise every requested signal
        exactly once. Records MUST NOT include unrequested signals.
        """
        requested = list(self.requested_signal_ids)
        if len(set(requested)) != len(requested):
            raise PromotionHttpWireValidationError(
                "requested_signal_ids MUST be unique"
            )
        categorised = list(self.categorised_source_ids())
        if sorted(categorised) != sorted(requested):
            raise PromotionHttpWireValidationError(
                "promotion_records MUST cover exactly the requested "
                "signal IDs"
            )
        if len(set(categorised)) != len(categorised):
            raise PromotionHttpWireValidationError(
                "promotion_records MUST NOT contain duplicate source IDs"
            )


__all__ = [
    "BoundPromotionHttpWireResult",
    "PromotionHttpWireResult",
    "PromotionHttpWireValidationError",
    "PromotionWireIncidentAccessMode",
    "PromotionWireRecord",
    "PromotionWireRecordOutcome",
    "PromotionWireScanScope",
]
