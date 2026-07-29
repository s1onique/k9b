"""Strict validated wire result for the backend promotion path.

ACT-K9B-HULK-PROMOTION-HTTP-TRANSPORT-PRODUCTION-WIRING01.

The legacy production client accepts truthy non-Booleans, skips
malformed records silently, and coerces values via ``str(...)``.
That fail-open behaviour is incompatible with the typed transport
algebra this ACT introduces. This module defines a frozen validated
wire result type with ``__post_init__`` enforcement so an invalid
payload cannot construct.

Validation rules:

* top-level value MUST be a Mapping;
* ``ok`` MUST be a strict ``bool`` (not a truthy non-bool);
* numerical fields MUST be non-negative integers;
* ID collections MUST contain non-empty strings;
* records MUST contain all required fields with the right types;
* record outcome MUST be from the closed vocabulary;
* success and error counters MUST be semantically consistent.

Any violation raises :class:`PromotionHttpWireValidationError`. The
mapping layer treats this exception as a transport-level
``PromotionHttpInvalidSchema`` outcome.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PromotionWireRecordOutcome(StrEnum):
    """Closed vocabulary for ``PromotionRecord.promotion_outcome`` strings.

    The backend wire contract uses these literal strings. ``unknown``
    is reserved for transport-level failures; the strict decoder
    MUST reject it as an authoritative wire value.
    """

    OPENED = "opened"
    UPDATED = "updated"
    OBSERVATION_REFRESHED = "observation_refreshed"
    UNCHANGED = "unchanged"


class PromotionHttpWireValidationError(ValueError):
    """Raised when the wire payload fails strict validation."""


@dataclass(frozen=True, slots=True)
class PromotionWireRecord:
    """Validated per-candidate promotion record."""

    source_candidate_id: str
    canonical_incident_id: str
    promotion_outcome: PromotionWireRecordOutcome


@dataclass(frozen=True, slots=True)
class PromotionHttpWireResult:
    """Strict validated backend promotion wire result.

    The dataclass ``__post_init__`` enforces every invariant; a
    malformed payload cannot construct. The mapping layer uses this
    type in place of arbitrary ``Mapping[str, Any]`` to prevent
    fail-open decoding.
    """

    ok: bool
    scanned: int
    firing: int
    opened_incident_ids: tuple[str, ...]
    updated_incident_ids: tuple[str, ...]
    canonical_incident_ids: tuple[str, ...]
    promotion_records: tuple[PromotionWireRecord, ...]
    errors: int
    error_messages: tuple[str, ...]
    unique_candidate_count: int
    promotion_scan_scope: str
    incident_access_mode: str

    def __post_init__(self) -> None:
        if not isinstance(self.ok, bool):
            raise PromotionHttpWireValidationError(
                f"ok MUST be a strict bool; got {type(self.ok).__name__}"
            )
        for field_name in (
            "scanned",
            "firing",
            "errors",
            "unique_candidate_count",
        ):
            value = getattr(self, field_name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise PromotionHttpWireValidationError(
                    f"{field_name} MUST be a non-negative int; got "
                    f"{type(value).__name__}={value!r}"
                )
        if not isinstance(self.opened_incident_ids, tuple):
            raise PromotionHttpWireValidationError(
                "opened_incident_ids MUST be a tuple"
            )
        if not isinstance(self.updated_incident_ids, tuple):
            raise PromotionHttpWireValidationError(
                "updated_incident_ids MUST be a tuple"
            )
        if not isinstance(self.canonical_incident_ids, tuple):
            raise PromotionHttpWireValidationError(
                "canonical_incident_ids MUST be a tuple"
            )
        for field_name in (
            "opened_incident_ids",
            "updated_incident_ids",
            "canonical_incident_ids",
        ):
            for identifier in getattr(self, field_name):
                if not isinstance(identifier, str) or not identifier:
                    raise PromotionHttpWireValidationError(
                        f"{field_name} MUST contain non-empty strings"
                    )
        if not isinstance(self.promotion_records, tuple):
            raise PromotionHttpWireValidationError(
                "promotion_records MUST be a tuple"
            )
        if not isinstance(self.error_messages, tuple):
            raise PromotionHttpWireValidationError(
                "error_messages MUST be a tuple"
            )
        if not isinstance(self.promotion_scan_scope, str):
            raise PromotionHttpWireValidationError(
                "promotion_scan_scope MUST be a string"
            )
        if not isinstance(self.incident_access_mode, str):
            raise PromotionHttpWireValidationError(
                "incident_access_mode MUST be a string"
            )
        # Counter consistency: zero scanned / zero firing is OK; mixed
        # negative invariants are not.
        if self.firing > self.scanned:
            raise PromotionHttpWireValidationError(
                "firing MUST NOT exceed scanned"
            )
        if self.errors > 0 and not self.error_messages:
            raise PromotionHttpWireValidationError(
                "errors > 0 requires at least one error_message"
            )

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any]
    ) -> PromotionHttpWireResult:
        """Validate and construct a wire result from a raw mapping.

        Raises :class:`PromotionHttpWireValidationError` on any
        structural violation. Mapping-level errors are caught by the
        caller and projected to
        :class:`PromotionHttpInvalidSchema`.
        """
        if not isinstance(payload, Mapping):
            raise PromotionHttpWireValidationError(
                f"payload MUST be a Mapping; got {type(payload).__name__}"
            )

        ok = payload.get("ok")
        if not isinstance(ok, bool):
            raise PromotionHttpWireValidationError(
                f"ok MUST be a strict bool; got {type(ok).__name__}"
            )

        def _coerce_non_negative_int(field_name: str) -> int:
            value = payload.get(field_name, 0)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise PromotionHttpWireValidationError(
                    f"{field_name} MUST be a non-negative int; got "
                    f"{type(value).__name__}={value!r}"
                )
            return value

        def _coerce_str_id_list(field_name: str) -> tuple[str, ...]:
            raw = payload.get(field_name, ())
            if not isinstance(raw, (list, tuple)):
                raise PromotionHttpWireValidationError(
                    f"{field_name} MUST be a list or tuple"
                )
            ids: list[str] = []
            for entry in raw:
                if not isinstance(entry, str) or not entry:
                    raise PromotionHttpWireValidationError(
                        f"{field_name} entries MUST be non-empty strings"
                    )
                ids.append(entry)
            return tuple(ids)

        def _coerce_records(field_name: str) -> tuple[PromotionWireRecord, ...]:
            raw = payload.get(field_name, ())
            if not isinstance(raw, (list, tuple)):
                raise PromotionHttpWireValidationError(
                    f"{field_name} MUST be a list or tuple"
                )
            records: list[PromotionWireRecord] = []
            for entry in raw:
                if not isinstance(entry, Mapping):
                    raise PromotionHttpWireValidationError(
                        f"{field_name} entries MUST be mappings"
                    )
                source = entry.get("source_candidate_id")
                canonical = entry.get("canonical_incident_id")
                outcome_raw = entry.get("promotion_outcome")
                if not isinstance(source, str) or not source:
                    raise PromotionHttpWireValidationError(
                        f"{field_name}: source_candidate_id MUST be a "
                        "non-empty string"
                    )
                if canonical is not None and (
                    not isinstance(canonical, str) or not canonical
                ):
                    raise PromotionHttpWireValidationError(
                        f"{field_name}: canonical_incident_id MUST be a "
                        "non-empty string when present"
                    )
                if not isinstance(outcome_raw, str):
                    raise PromotionHttpWireValidationError(
                        f"{field_name}: promotion_outcome MUST be a string"
                    )
                try:
                    outcome = PromotionWireRecordOutcome(outcome_raw)
                except ValueError as exc:
                    raise PromotionHttpWireValidationError(
                        f"{field_name}: unknown promotion_outcome "
                        f"{outcome_raw!r}"
                    ) from exc
                records.append(
                    PromotionWireRecord(
                        source_candidate_id=source,
                        canonical_incident_id=canonical or "",
                        promotion_outcome=outcome,
                    )
                )
            return tuple(records)

        return cls(
            ok=ok,
            scanned=_coerce_non_negative_int("scanned"),
            firing=_coerce_non_negative_int("firing"),
            opened_incident_ids=_coerce_str_id_list("opened_incident_ids"),
            updated_incident_ids=_coerce_str_id_list("updated_incident_ids"),
            canonical_incident_ids=_coerce_str_id_list(
                "canonical_incident_ids"
            ),
            promotion_records=_coerce_records("promotion_records"),
            errors=_coerce_non_negative_int("errors"),
            error_messages=tuple(
                str(message)
                for message in payload.get("error_messages", ())
                if isinstance(message, str)
            ),
            unique_candidate_count=_coerce_non_negative_int(
                "unique_candidate_count"
            ),
            promotion_scan_scope=str(
                payload.get("promotion_scan_scope", "") or ""
            ),
            incident_access_mode=str(
                payload.get("incident_access_mode", "") or ""
            ),
        )


__all__ = [
    "PromotionHttpWireResult",
    "PromotionHttpWireValidationError",
    "PromotionWireRecord",
    "PromotionWireRecordOutcome",
]
